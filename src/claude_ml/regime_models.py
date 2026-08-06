"""
Regime-Specific Expert Models - Specialized models for different market conditions.

Instead of one universal model, this system maintains multiple expert models:
- Trend Expert (performs well in trending markets)
- Range Expert (excels in sideways/choppy markets)
- Breakout Expert (specialized in volatility expansions)

A meta-learner dynamically routes to the appropriate expert based on current regime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ExpertModel:
    """A specialized model for a specific market regime."""
    name: str
    regime_type: str  # 'trend', 'range', 'breakout'
    win_rate: float = 0.5
    total_trades: int = 0
    avg_pnl: float = 0.0
    profit_factor: float = 1.0
    last_performance_update: str = ""


@dataclass(slots=True)
class RegimeClassification:
    """Current market regime determination."""
    primary_regime: str  # 'trend', 'range', 'breakout'
    confidence: float  # 0-1 confidence in classification
    trend_strength: float = 0.0
    range_width: float = 0.0
    volatility_percentile: float = 0.0


class RegimeDetector:
    """Detects current market regime using multiple indicators."""

    @staticmethod
    def classify(df: pd.DataFrame) -> RegimeClassification:
        """
        Classify current market regime.

        Uses:
        - ADX for trend strength
        - Bollinger Band width for volatility
        - Price position in range
        - Historical volatility percentile

        Returns:
            RegimeClassification with primary regime and confidence
        """
        if df.empty or len(df) < 50:
            return RegimeClassification(
                primary_regime="unknown",
                confidence=0.0,
            )

        close = df['close']
        high = df['high']
        low = df['low']

        # Calculate ADX for trend strength
        adx = RegimeDetector._calculate_adx(high, low, close, period=14)
        current_adx = float(adx.iloc[-1]) if not adx.empty else 20.0

        # Calculate Bollinger Band width for volatility
        bb_width = RegimeDetector._calculate_bb_width(close, period=20)
        current_bb_width = float(bb_width.iloc[-1]) if not bb_width.empty else 0.02

        # Calculate price position in recent range
        recent_high = high.tail(50).max()
        recent_low = low.tail(50).min()
        range_width = float(recent_high - recent_low)
        current_price = float(close.iloc[-1])

        if range_width > 0:
            price_position = (current_price - recent_low) / range_width
        else:
            price_position = 0.5

        # Determine regime based on ADX and BB width
        if current_adx > 25:
            # Strong trend
            primary_regime = "trend"
            confidence = min((current_adx - 20) / 30.0, 1.0)
        elif current_bb_width < 0.015:  # Low volatility = compression
            primary_regime = "breakout"
            confidence = min((0.02 - current_bb_width) / 0.01, 1.0)
        else:
            # Sideways/choppy
            primary_regime = "range"
            confidence = max(1.0 - current_adx / 40.0, 0.3)

        return RegimeClassification(
            primary_regime=primary_regime,
            confidence=round(float(confidence), 3),
            trend_strength=current_adx / 50.0 if current_adx < 50 else 1.0,
            range_width=range_width,
            volatility_percentile=current_bb_width * 100,
        )

    @staticmethod
    def _calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate ADX (Average Directional Index)."""
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        adx = dx.rolling(period).mean()

        return adx

    @staticmethod
    def _calculate_bb_width(close: pd.Series, period: int = 20) -> pd.Series:
        """Calculate Bollinger Band width as % of price."""
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        width = (upper - lower) / sma
        return width


class ExpertRouter:
    """Routes decisions to appropriate expert model based on regime."""

    def __init__(self):
        self.experts: Dict[str, ExpertModel] = {
            "trend": ExpertModel(name="Trend Expert", regime_type="trend"),
            "range": ExpertModel(name="Range Expert", regime_type="range"),
            "breakout": ExpertModel(name="Breakout Expert", regime_type="breakout"),
        }
        self.detector = RegimeDetector()
        self.current_regime: Optional[RegimeClassification] = None

    def get_current_regime(self, df: pd.DataFrame) -> RegimeClassification:
        """Get current market regime classification."""
        self.current_regime = self.detector.classify(df)
        return self.current_regime

    def get_active_expert(self) -> ExpertModel:
        """Get the expert model for current regime."""
        if self.current_regime is None:
            logger.warning("No regime classification yet, using trend expert")
            return self.experts["trend"]

        regime = self.current_regime.primary_regime
        if regime not in self.experts:
            logger.warning(f"Unknown regime '{regime}', defaulting to trend expert")
            return self.experts["trend"]

        return self.experts[regime]

    def update_expert_performance(self, regime: str, pnl: float) -> None:
        """Update performance metrics for an expert after a trade."""
        if regime in self.experts:
            expert = self.experts[regime]
            expert.total_trades += 1

            # Update win rate
            if pnl > 0:
                expert.win_rate = (expert.win_rate * (expert.total_trades - 1) + 1) / expert.total_trades
            else:
                expert.win_rate = (expert.win_rate * (expert.total_trades - 1)) / expert.total_trades

            # Update avg PnL (exponential moving average)
            alpha = 0.3
            expert.avg_pnl = (1 - alpha) * expert.avg_pnl + alpha * pnl

            # Update profit factor
            if pnl > 0:
                expert.profit_factor = max(expert.profit_factor * 0.95 + 0.05, 2.0)
            else:
                expert.profit_factor = max(expert.profit_factor * 0.95, 0.5)

            expert.last_performance_update = datetime.now(timezone.utc).isoformat()

    def get_expert_summary(self) -> Dict[str, Any]:
        """Get summary of all expert models."""
        return {
            regime: {
                "win_rate": expert.win_rate,
                "total_trades": expert.total_trades,
                "avg_pnl": expert.avg_pnl,
                "profit_factor": expert.profit_factor,
            }
            for regime, expert in self.experts.items()
        }
