"""
Context-Aware Multi-Model Ensemble - Adaptive decision making based on market context.

Key improvements over original:
1. Market context analysis before signal evaluation
2. Adaptive thresholds based on regime and market state
3. Balanced long/short evaluation with contextual bias
4. Dynamic position sizing based on conviction level
5. Explainable reasoning with market structure awareness

Decision framework:
- Analyze market context (trend, volatility, liquidity, structure)
- Evaluate signals with adaptive thresholds
- Determine side based on contextual evidence, not just scores
- Size positions based on conviction (context quality * signal strength)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import math

import pandas as pd

from .models.early_signal import EarlySignalModel, EarlySignalResult
from .models.confirmation import ConfirmationModel, ConfirmationResult
from .models.momentum import MomentumModel, MomentumResult
from .cross_market import get_cross_market_features

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MarketContext:
    """Comprehensive market state analysis."""
    # Trend analysis
    higher_tf_trend: str  # 'bullish', 'bearish', 'neutral'
    trend_strength: float  # 0-1 composite strength
    trend_quality: str  # 'impulsive', 'corrective', 'developing'

    # Volatility analysis
    vol_percentile: float  # Current vol vs historical (0-100)
    vol_regime: str  # 'low', 'normal', 'high', 'extreme'
    vol_trend: str  # 'expanding', 'contracting', 'stable'

    # Market structure
    structure_type: str  # 'HH_HL' (uptrend), 'LH_LL' (downtrend), 'range'
    structure_strength: float  # How clear is the structure
    key_level_proximity: str  # 'at_support', 'at_resistance', 'in_no_mans_land'

    # Liquidity analysis
    liquidity_condition: str  # 'thick', 'normal', 'thin'
    liquidity_trend: str  # 'improving', 'deteriorating', 'stable'

    # Momentum context
    momentum_alignment: dict  # {5m: direction, 15m: direction, 1h: direction}
    momentum_confluence: bool  # Are multiple timeframes aligned?

    # Buyer/Seller pressure
    dominant_side: str  # 'buyers', 'sellers', 'balanced'
    pressure_strength: float  # 0-1

    # Cross-market context (NEW)
    dxy_trend: Optional[str] = None  # 'rising', 'falling', 'neutral'
    dxy_change_pct: Optional[float] = None
    eth_btc_ratio: Optional[float] = None
    eth_leading: Optional[bool] = None
    spx_correlation: Optional[float] = None
    risk_on_off_signal: Optional[str] = None  # 'risk_on', 'risk_off', 'neutral'
    cross_market_data_quality: float = 0.0  # 0-1 quality of cross-market data

    # Computed metrics
    overall_clarity: float = 0.5  # 0-1 how clear is the market picture
    directional_bias: str = "neutral"  # 'long_preferred', 'short_preferred', 'neutral'
    required_confidence: float = 0.70  # Minimum confidence to enter based on context


@dataclass(slots=True)
class EnsembleDecision:
    """Final decision from ensemble with context awareness."""
    action: str  # 'enter_full', 'enter_reduced', 'enter_small', 'stage_1', 'stage_2', 'wait', 'skip'
    side: str  # 'long' or 'short'
    confidence: float  # 0-100
    score: float  # Combined score
    early_result: Optional[EarlySignalResult] = None
    confirmation_result: Optional[ConfirmationResult] = None
    momentum_result: Optional[MomentumResult] = None
    position_size_pct: float = 1.0  # Multiplier (1.0 = 100%)
    reasoning: List[str] = None
    market_context: Optional[MarketContext] = None  # NEW: context that led to decision
    conviction_level: str = "low"  # NEW: low/medium/high based on context + signal


class ContextAnalyzer:
    """Analyzes market context for adaptive decision making."""

    @staticmethod
    def _num(row: pd.Series, key: str, default: float) -> float:
        """Read a numeric feature, mapping None/NaN to the default.

        `x or default` does not catch NaN (NaN is truthy), so a single NaN
        feature previously propagated into bias arithmetic and silently
        disabled every comparison it appeared in.
        """
        val = row.get(key, default)
        try:
            val = float(val)
        except (TypeError, ValueError):
            return default
        if val != val:  # NaN check
            return default
        return val

    @staticmethod
    def analyze(row: pd.Series, regime_info: Optional[dict] = None) -> MarketContext:
        """
        Comprehensive market context analysis.

        This replaces simple regime detection with multi-dimensional analysis.
        """
        # Extract key metrics from features
        ema_8_vs_21 = ContextAnalyzer._num(row, "ema_8_vs_21", 0.0)
        ema_slope_8 = ContextAnalyzer._num(row, "ema_slope_8", 0.0)
        atr_pct = ContextAnalyzer._num(row, "atr_pct_14", 0.005)
        rsi = ContextAnalyzer._num(row, "rsi_14", 50.0)
        close_position = ContextAnalyzer._num(row, "bar_close_position", 0.5)
        volume_zscore = ContextAnalyzer._num(row, "vol_zscore", 0.0)
        ob_imbalance = ContextAnalyzer._num(row, "ob_imbalance_top_10", 0.0)
        trade_flow = ContextAnalyzer._num(row, "trade_flow_imbalance", 0.0)

        # Higher timeframe trend (using 60m features if available)
        tf60_rsi = ContextAnalyzer._num(row, "tf60_rsi_14", 50.0)
        tf60_ret_3 = ContextAnalyzer._num(row, "tf60_ret_3", 0.0)

        # === TREND ANALYSIS ===
        # Composite trend strength from multiple indicators
        trend_components = []
        if abs(ema_8_vs_21) > 0.002:
            trend_components.append(min(abs(ema_8_vs_21) / 0.005, 1.0))
        if abs(ema_slope_8) > 0.0005:
            trend_components.append(min(abs(ema_slope_8) / 0.001, 1.0))

        trend_strength = sum(trend_components) / len(trend_components) if trend_components else 0.2

        # Determine trend direction
        if ema_8_vs_21 > 0.003 and ema_slope_8 > 0:
            higher_tf_trend = "bullish"
        elif ema_8_vs_21 < -0.003 and ema_slope_8 < 0:
            higher_tf_trend = "bearish"
        else:
            higher_tf_trend = "neutral"

        # Trend quality (impulsive vs corrective)
        if abs(ema_8_vs_21) > 0.005 and volume_zscore > 0.5:
            trend_quality = "impulsive"
        elif abs(ema_8_vs_21) > 0.002:
            trend_quality = "corrective"
        else:
            trend_quality = "developing"

        # === VOLATILITY ANALYSIS ===
        # ATR percentile approximation (would be better with historical data)
        vol_percentile = min(max(atr_pct * 10000, 0), 100)  # Rough approximation

        if atr_pct < 0.003:
            vol_regime = "low"
        elif atr_pct < 0.008:
            vol_regime = "normal"
        elif atr_pct < 0.015:
            vol_regime = "high"
        else:
            vol_regime = "extreme"

        # Volatility trend (would need historical ATR data)
        vol_trend = "stable"  # Placeholder

        # === MARKET STRUCTURE ===
        # Using RSI and close position to infer structure
        if rsi > 60 and close_position > 0.7:
            structure_type = "HH_HL"  # Uptrend structure
            structure_strength = min((rsi - 50) / 20, 1.0) * close_position
        elif rsi < 40 and close_position < 0.3:
            structure_type = "LH_LL"  # Downtrend structure
            structure_strength = min((50 - rsi) / 20, 1.0) * (1 - close_position)
        else:
            structure_type = "range"
            structure_strength = 1.0 - abs(rsi - 50) / 25

        # Key level proximity (simplified - would be better with S/R levels)
        if close_position > 0.8:
            key_level_proximity = "at_resistance"
        elif close_position < 0.2:
            key_level_proximity = "at_support"
        else:
            key_level_proximity = "in_no_mans_land"

        # === LIQUIDITY ANALYSIS ===
        spread_bps = ContextAnalyzer._num(row, "ob_spread_bps", 5.0)

        if spread_bps < 3:
            liquidity_condition = "thick"
        elif spread_bps < 8:
            liquidity_condition = "normal"
        else:
            liquidity_condition = "thin"

        liquidity_trend = "stable"  # Placeholder

        # === MOMENTUM CONTEXT ===
        # Multi-timeframe alignment
        short_momentum = "bullish" if rsi > 55 else "bearish" if rsi < 45 else "neutral"
        medium_momentum = "bullish" if tf60_rsi > 55 else "bearish" if tf60_rsi < 45 else "neutral"

        momentum_alignment = {
            "5m": short_momentum,
            "15m": medium_momentum,
            "1h": "bullish" if tf60_ret_3 > 0 else "bearish"
        }

        # Check if timeframes align
        directions = [d for d in momentum_alignment.values() if d != "neutral"]
        momentum_confluence = len(set(directions)) == 1 and len(directions) >= 2

        # === BUYER/SELLER PRESSURE ===
        # Combine order book and trade flow
        ob_pressure = ob_imbalance
        flow_pressure = trade_flow
        pressure_score = (ob_pressure + flow_pressure) / 2

        if pressure_score > 0.05:
            dominant_side = "buyers"
        elif pressure_score < -0.05:
            dominant_side = "sellers"
        else:
            dominant_side = "balanced"

        pressure_strength = min(abs(pressure_score) * 10, 1.0)

        # === OVERALL CLARITY ===
        # How clear is the market picture?
        clarity_factors = [
            trend_strength,
            structure_strength,
            pressure_strength,
            1.0 if momentum_confluence else 0.3,
            1.0 if vol_regime in ["normal", "high"] else 0.5
        ]
        overall_clarity = sum(clarity_factors) / len(clarity_factors)

        # === DIRECTIONAL BIAS ===
        # Based on all factors, which side is preferred?
        bias_score = 0.0
        if higher_tf_trend == "bullish":
            bias_score += 0.3
        elif higher_tf_trend == "bearish":
            bias_score -= 0.3

        if structure_type == "HH_HL":
            bias_score += 0.2
        elif structure_type == "LH_LL":
            bias_score -= 0.2

        if dominant_side == "buyers":
            bias_score += 0.2
        elif dominant_side == "sellers":
            bias_score -= 0.2

        if tf60_rsi > 55:
            bias_score += 0.15
        elif tf60_rsi < 45:
            bias_score -= 0.15

        # === CROSS-MARKET ANALYSIS (NEW) ===
        # Fetch and analyze inter-market correlations
        try:
            cross_market_data = get_cross_market_features(row)

            dxy_trend = cross_market_data.get('dxy_trend')
            dxy_change_pct = cross_market_data.get('dxy_change_pct')
            eth_btc_ratio = cross_market_data.get('eth_btc_ratio')
            eth_leading = cross_market_data.get('eth_leading')
            spx_correlation = cross_market_data.get('spx_btc_correlation')
            cross_market_quality = cross_market_data.get('data_quality', 0.0)

            # Apply cross-market biases
            if dxy_trend == "falling" and dxy_change_pct and dxy_change_pct < -0.2:
                bias_score += 0.15  # DXY falling is bullish for BTC
            elif dxy_trend == "rising" and dxy_change_pct and dxy_change_pct > 0.2:
                bias_score -= 0.15  # DXY rising is bearish for BTC

            if eth_leading and eth_btc_ratio and eth_btc_ratio > 0:
                bias_score += 0.1  # ETH leading with positive momentum
            elif eth_leading and eth_btc_ratio and eth_btc_ratio < 0:
                bias_score -= 0.1  # ETH leading downward

            if spx_correlation and abs(spx_correlation) > 0.5:
                # High correlation means risk-on/off matters
                if spx_correlation > 0.5:
                    bias_score += 0.1  # Positive correlation with stocks
                else:
                    bias_score -= 0.05  # Negative correlation (rare)

        except Exception as e:
            logger.warning(f"Cross-market analysis failed: {e}")
            dxy_trend = None
            dxy_change_pct = None
            eth_btc_ratio = None
            eth_leading = None
            spx_correlation = None
            cross_market_quality = 0.0

        if bias_score > 0.15:
            directional_bias = "long_preferred"
        elif bias_score < -0.15:
            directional_bias = "short_preferred"
        else:
            directional_bias = "neutral"

        # === REQUIRED CONFIDENCE ===
        # Adaptive threshold based on context clarity, anchored to the
        # confirmation model's actual score scale (set on this instance by
        # EnsembleEngine after loading models). The old hardcoded 0.70
        # (clamped 0.60-0.90) assumed scores in the 0.7-0.9 range; with honest
        # realized-PnL labels the models top out near 0.5, so this gate alone
        # blocked every entry. Anchoring keeps the *relative* meaning
        # (clearer market -> lower bar) while following the model's scale.
        model_scale = float(getattr(self, "model_score_scale", 0.0) or 0.0)
        if model_scale > 0:
            base_confidence = model_scale
        else:
            # Fallback: pre-fix behavior
            base_confidence = 0.70

        # Adjust based on clarity (clearer markets need lower confidence)
        if overall_clarity > 0.7:
            clarity_adjustment = -0.05
        elif overall_clarity < 0.4:
            clarity_adjustment = +0.10
        else:
            clarity_adjustment = 0.0

        # Adjust based on volatility (higher vol needs higher confidence)
        if vol_regime == "high":
            vol_adjustment = +0.05
        elif vol_regime == "low":
            vol_adjustment = -0.03
        else:
            vol_adjustment = 0.0

        # Adjust based on key level proximity
        if key_level_proximity == "at_resistance" and directional_bias == "long_preferred":
            level_adjustment = +0.05  # Risky to go long at resistance
        elif key_level_proximity == "at_support" and directional_bias == "short_preferred":
            level_adjustment = +0.05  # Risky to short at support
        else:
            level_adjustment = 0.0

        required_confidence = base_confidence + clarity_adjustment + vol_adjustment + level_adjustment
        if model_scale > 0:
            # Anchor-aware clamp: never above the model's realistic ceiling
            required_confidence = max(min(required_confidence, model_scale + 0.05), 0.35)
        else:
            required_confidence = max(min(required_confidence, 0.90), 0.60)  # Clamp between 60-90%

        return MarketContext(
            higher_tf_trend=higher_tf_trend,
            trend_strength=trend_strength,
            trend_quality=trend_quality,
            vol_percentile=vol_percentile,
            vol_regime=vol_regime,
            vol_trend=vol_trend,
            structure_type=structure_type,
            structure_strength=structure_strength,
            key_level_proximity=key_level_proximity,
            liquidity_condition=liquidity_condition,
            liquidity_trend=liquidity_trend,
            momentum_alignment=momentum_alignment,
            momentum_confluence=momentum_confluence,
            dominant_side=dominant_side,
            pressure_strength=pressure_strength,
            dxy_trend=dxy_trend,
            dxy_change_pct=dxy_change_pct,
            eth_btc_ratio=eth_btc_ratio,
            eth_leading=eth_leading,
            spx_correlation=spx_correlation,
            risk_on_off_signal="risk_on" if spx_correlation and spx_correlation > 0.5 else "risk_off" if spx_correlation and spx_correlation < -0.3 else "neutral",
            cross_market_data_quality=cross_market_quality,
            overall_clarity=overall_clarity,
            directional_bias=directional_bias,
            required_confidence=required_confidence
        )


class EnsembleEngine:
    """Context-aware multi-model ensemble for adaptive decision making."""

    def __init__(
        self,
        early_model: EarlySignalModel,
        confirmation_model: ConfirmationModel,
        momentum_model: MomentumModel,
    ):
        self.early_model = early_model
        self.confirmation_model = confirmation_model
        self.momentum_model = momentum_model
        self.context_analyzer = ContextAnalyzer()
        self._update_model_scale()

    def _update_model_scale(self) -> None:
        """Anchor required_confidence to the confirmation model's real score ceiling.

        The old hardcoded 0.70 base assumed scores of 0.7-0.9; honest labels
        produce models topping out ~0.5, which made the confidence gate
        unreachable. Now follows whatever the calibrated threshold engine
        set — proxy: the confirmation threshold + small margin, bounded.
        """
        try:
            scale = max(
                self.confirmation_model.threshold_long,
                self.confirmation_model.threshold_short,
            )
            # The models' typical strong-signal ceiling sits a bit above the
            # calibrated entry threshold; clamp to a sane range.
            self.context_analyzer.model_score_scale = min(max(scale, 0.40), 0.80)
        except Exception:
            self.context_analyzer.model_score_scale = 0.0

    def evaluate(
        self,
        row: pd.Series,
        regime: Optional[str] = None,
        stage: str = "full",  # 'stage_1', 'stage_2', or 'full' (single-stage)
    ) -> Optional[EnsembleDecision]:
        """
        Evaluate ensemble decision with market context awareness.

        NEW APPROACH:
        1. Analyze market context FIRST
        2. Determine directional bias from context
        3. Run models for BOTH sides
        4. Use adaptive thresholds based on context
        5. Size position based on conviction (context * signal)
        """
        # STEP 1: Analyze market context
        context = self.context_analyzer.analyze(row)

        # STEP 2: Run models for BOTH long and short
        early_result_long = self.early_model.predict(row, side="long", regime=regime)
        early_result_short = self.early_model.predict(row, side="short", regime=regime)

        confirm_long = self.confirmation_model.predict(row, side="long", regime=regime)
        confirm_short = self.confirmation_model.predict(row, side="short", regime=regime)

        momentum_long = self.momentum_model.predict(row, side="long")
        momentum_short = self.momentum_model.predict(row, side="short")

        # STEP 3: Choose best side based on contextual evidence
        # Not just model scores, but also market structure
        long_evidence = self._calculate_evidence_score(
            early_result_long, confirm_long, momentum_long, context, side="long"
        )
        short_evidence = self._calculate_evidence_score(
            early_result_short, confirm_short, momentum_short, context, side="short"
        )

        # Apply contextual bias (if market clearly favors one direction)
        if context.directional_bias == "long_preferred":
            long_evidence *= 1.15  # Boost long signals in bullish context
        elif context.directional_bias == "short_preferred":
            short_evidence *= 1.15  # Boost short signals in bearish context

        # LOG evidence comparison for transparency
        print(f"[EVIDENCE] Long: {long_evidence:.3f} | Short: {short_evidence:.3f} | Diff: {abs(long_evidence - short_evidence):.3f}")

        # Select side with strongest evidence
        if long_evidence > short_evidence and long_evidence > 0.3:
            side = "long"
            early_result = early_result_long
            confirm_result = confirm_long
            momentum_result = momentum_long
            evidence_score = long_evidence
            print(f"[SIDE SELECTION] LONG chosen (evidence advantage: +{((long_evidence - short_evidence) * 100):.1f}%)")
        elif short_evidence > long_evidence and short_evidence > 0.3:
            side = "short"
            early_result = early_result_short
            confirm_result = confirm_short
            momentum_result = momentum_short
            evidence_score = short_evidence
            print(f"[SIDE SELECTION] SHORT chosen (evidence advantage: +{((short_evidence - long_evidence) * 100):.1f}%)")
        else:
            # No clear direction
            print(f"[SIDE SELECTION] SKIP - no clear winner (long={long_evidence:.3f}, short={short_evidence:.3f})")
            return None

        # STEP 4: Check against adaptive threshold
        required_confidence = context.required_confidence

        # LOG context analysis
        print(f"[CONTEXT] Bias: {context.directional_bias}, Clarity: {context.overall_clarity:.2f}")
        print(f"[CONTEXT] Required confidence: {required_confidence:.3f}")

        # Get actual confidence from best model
        model_confidence = max(
            confirm_result.score if confirm_result else 0,
            early_result.score if early_result else 0
        )

        print(f"[CONFIDENCE] Model: {model_confidence:.1f}% vs Required: {required_confidence*100:.1f}%")

        if model_confidence < required_confidence * 100:  # Convert to 0-100 scale
            # Signal exists but confidence too low for current context
            print(f"[SKIP] Confidence too low ({model_confidence:.1f}% < {required_confidence*100:.1f}%)")
            return None

        # STEP 5: Determine action based on model agreements
        agreements = []
        if early_result and early_result.score >= 62:
            agreements.append("early")
        if confirm_result and confirm_result.is_confirmed:
            agreements.append("confirm")
        if momentum_result and momentum_result.direction == "with_momentum":
            agreements.append("momentum")

        # Calculate base confidence
        if len(agreements) == 3:
            base_confidence = (
                (early_result.score if early_result else 0) +
                (confirm_result.score if confirm_result else 0) +
                (momentum_result.score if momentum_result else 0)
            ) / 3
            action = "enter_full"
            base_position_size = 1.0
        elif len(agreements) == 2:
            if "early" in agreements and "confirm" in agreements:
                base_confidence = ((early_result.score if early_result else 0) +
                                   (confirm_result.score if confirm_result else 0)) / 2
                action = "enter_reduced"
                base_position_size = 0.7
            elif "early" in agreements and "momentum" in agreements:
                base_confidence = ((early_result.score if early_result else 0) +
                                   (momentum_result.score if momentum_result else 0)) / 2
                action = "enter_small"
                base_position_size = 0.4
            else:
                base_confidence = ((confirm_result.score if confirm_result else 0) +
                                   (momentum_result.score if momentum_result else 0)) / 2
                action = "enter_reduced"
                base_position_size = 0.6
        elif len(agreements) == 1:
            if "early" in agreements:
                action = "wait"
                base_confidence = early_result.score if early_result else 0
                base_position_size = 0.0
            else:
                action = "skip"
                base_confidence = 0
                base_position_size = 0.0
        else:
            action = "skip"
            base_confidence = 0
            base_position_size = 0.0

        # STEP 6: Adjust position size based on conviction
        # Conviction = combination of context clarity AND signal strength
        conviction_multiplier = context.overall_clarity * (base_confidence / 100.0)
        final_position_size = base_position_size * conviction_multiplier

        # Build enhanced reasoning with context
        reasoning = []
        reasoning.append(f"Context: {context.directional_bias}, clarity={context.overall_clarity:.2f}")
        reasoning.append(f"Trend: {context.higher_tf_trend} ({context.trend_quality}), strength={context.trend_strength:.2f}")
        reasoning.append(f"Structure: {context.structure_type}, key_level={context.key_level_proximity}")

        if early_result:
            reasoning.append(f"Early: {early_result.score:.0f} (compression={early_result.compression_detected}, volume={early_result.volume_drying})")
        if confirm_result:
            reasoning.append(f"Confirm: {confirm_result.score:.0f} (calibrated={confirm_result.probability:.2%})")
        if momentum_result:
            reasoning.append(f"Momentum: {momentum_result.direction} ({momentum_result.strength})")

        reasoning.append(f"Required confidence: {required_confidence:.2f}, Model confidence: {base_confidence:.0f}")
        reasoning.append(f"Conviction: {conviction_multiplier:.2f}, Final size: {final_position_size:.2f}")

        # Determine conviction level
        if conviction_multiplier > 0.7:
            conviction_level = "high"
        elif conviction_multiplier > 0.4:
            conviction_level = "medium"
        else:
            conviction_level = "low"

        return EnsembleDecision(
            action=action,
            side=side,
            confidence=round(base_confidence, 2),
            score=round(evidence_score, 2),
            early_result=early_result,
            confirmation_result=confirm_result,
            momentum_result=momentum_result,
            position_size_pct=final_position_size,
            reasoning=reasoning,
            market_context=context,
            conviction_level=conviction_level
        )

    def _calculate_evidence_score(
        self,
        early: Optional[EarlySignalResult],
        confirm: Optional[ConfirmationResult],
        momentum: Optional[MomentumResult],
        context: MarketContext,
        side: str
    ) -> float:
        """
        Calculate composite evidence score for a given side.

        Combines model scores with contextual alignment.
        Returns 0-1 score where higher means stronger evidence.
        """
        score = 0.0
        weight_sum = 0.0

        # Early signal contribution (weight: 0.3)
        if early:
            early_normalized = early.score / 100.0
            score += early_normalized * 0.3
            weight_sum += 0.3

        # Confirmation contribution (weight: 0.5) - highest weight
        if confirm:
            confirm_normalized = confirm.score / 100.0
            score += confirm_normalized * 0.5
            weight_sum += 0.5

        # Momentum contribution (weight: 0.2)
        if momentum:
            momentum_score = 0.7 if momentum.direction == "with_momentum" else 0.3
            score += momentum_score * 0.2
            weight_sum += 0.2

        # Normalize if not all models contributed
        if weight_sum > 0:
            score = score / weight_sum

        # Apply contextual alignment bonus
        if side == "long" and context.directional_bias == "long_preferred":
            score *= 1.1
        elif side == "short" and context.directional_bias == "short_preferred":
            score *= 1.1

        # Momentum confluence bonus
        if context.momentum_confluence:
            score *= 1.05

        # === MARKET STRUCTURE AWARENESS (Phase 4) ===

        # KEY LEVEL PROXIMITY + STRUCTURE COMBINED - Avoid bad entries with smart adjustments
        if context.structure_type == "range":
            # In ranges, use mean reversion logic
            if context.key_level_proximity == "at_resistance":
                if side == "long":
                    score *= 0.60  # Strong penalty - buying at range top
                else:  # short
                    score *= 1.20  # Bonus - selling at range top (correct direction)
            elif context.key_level_proximity == "at_support":
                if side == "short":
                    score *= 0.60  # Strong penalty - selling at range bottom
                else:  # long
                    score *= 1.20  # Bonus - buying at range bottom (correct direction)
        else:
            # In trending markets, key levels still matter but less extreme
            if context.key_level_proximity == "at_resistance" and side == "long":
                score *= 0.75  # Moderate penalty for longs at resistance
            elif context.key_level_proximity == "at_support" and side == "short":
                score *= 0.75  # Moderate penalty for shorts at support

        # TREND STRUCTURE RESPECT - Don't fight clear trends
        if context.structure_type == "HH_HL":  # Uptrend
            if side == "short":
                score *= 0.85  # Penalty for counter-trend shorts in uptrend

        if context.structure_type == "LH_LL":  # Downtrend
            if side == "long":
                score *= 0.85  # Penalty for counter-trend longs in downtrend

        # HIGHER TIMEFRAME TREND ALIGNMENT - Respect the bigger picture
        if context.higher_tf_trend == "bullish" and side == "short":
            score *= 0.90  # Slight penalty for counter-trend
        elif context.higher_tf_trend == "bearish" and side == "long":
            score *= 0.90  # Slight penalty for counter-trend

        # VOLATILITY REGIME ADJUSTMENT - Be cautious in extreme vol
        if context.vol_regime == "extreme":
            score *= 0.85  # Reduce conviction in extreme volatility
        elif context.vol_regime == "low":
            if context.structure_type == "range":
                score *= 1.10  # Low vol + range = good for mean reversion

        # ATR BREAKOUT DETECTION (NEW)
        # Low ATR + developing structure = potential breakout setup
        # Low volatility often precedes strong directional moves
        if context.vol_regime == "low" and context.structure_type != "range":
            # Compressed volatility + trending structure = breakout preparation
            score *= 1.12  # Bonus for breakout setup
        elif context.vol_regime == "low" and context.trend_quality == "developing":
            # Low vol + developing trend = building momentum
            score *= 1.08

        # LIQUIDITY CHECK - Avoid trading in thin markets
        if context.liquidity_condition == "thin":
            score *= 0.90  # Reduce conviction when liquidity is poor

        return min(score, 1.0)

    def get_feature_summary(self) -> Dict[str, Any]:
        """Get summary of important features across all models."""
        return {
            "early_top_features": self.early_model.get_top_features(n=5),
            "confirmation_top_features": self.confirmation_model.get_top_features(n=5),
            "momentum_top_features": self.momentum_model.get_top_features(n=5),
        }
