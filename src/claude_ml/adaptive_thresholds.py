"""
Adaptive Threshold System - Per-symbol dynamic threshold adjustment.

Automatically calculates optimal thresholds for each symbol based on:
- Historical performance (win rate, profit factor)
- Market regime (trending, choppy, volatile)
- Volatility characteristics
- Recent momentum
- Model calibration quality

Features:
- Per-symbol thresholds (BTC, ETH, XRP have different values)
- Regime-aware adjustments (lower in trending, higher in chop)
- Performance-based tuning (adjusts based on recent results)
- Safety bounds (prevents thresholds from going too low/high)
- Smooth transitions (no sudden jumps)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd
import numpy as np


@dataclass(slots=True)
class SymbolCharacteristics:
    """Historical characteristics of a trading symbol."""
    symbol: str
    avg_win_rate: float = 0.5
    avg_profit_factor: float = 1.0
    avg_volatility: float = 0.0
    win_rate_std: float = 0.1
    best_regime: str = "trend"
    worst_regime: str = "chop"
    total_trades: int = 0


@dataclass(slots=True)
class AdaptiveThreshold:
    """Current adaptive threshold for a symbol."""
    symbol: str
    early_signal_threshold: float = 0.60
    confirmation_threshold: float = 0.75
    momentum_threshold: float = 0.55

    # Bounds
    min_early: float = 0.45
    max_early: float = 0.75
    min_confirmation: float = 0.55
    max_confirmation: float = 0.90
    min_momentum: float = 0.40
    max_momentum: float = 0.70

    # Adjustment factors
    regime_multiplier: float = 1.0
    performance_multiplier: float = 1.0
    volatility_multiplier: float = 1.0

    last_updated: str = ""


class AdaptiveThresholdEngine:
    """
    Dynamically adjusts thresholds per symbol based on multiple factors.

    Logic:
    1. Base threshold from symbol characteristics
    2. Adjust for current market regime
    3. Adjust for recent performance
    4. Adjust for volatility
    5. Apply safety bounds
    6. Smooth transition to new values
    """

    def __init__(self, settings):
        self.settings = settings
        self.conn = sqlite3.connect(settings.runtime_db_path)
        self.conn.row_factory = sqlite3.Row

        # Default base thresholds (starting point) - BTC only
        self.base_thresholds = {
            "BTCUSDT": AdaptiveThreshold(
                symbol="BTCUSDT",
                early_signal_threshold=0.58,
                confirmation_threshold=0.70,
                momentum_threshold=0.52,
            ),
        }

        # Load historical characteristics
        self.symbol_characteristics = self._load_symbol_characteristics()

    def _load_symbol_characteristics(self) -> Dict[str, SymbolCharacteristics]:
        """Load historical performance data for each symbol from database."""
        characteristics = {}

        for symbol in self.settings.symbols:
            # Query trades for this symbol
            trades = self.conn.execute("""
                SELECT pnl_pct FROM paper_trades
                WHERE symbol = ? AND status IN ('closed', 'shadow_closed') AND pnl_pct IS NOT NULL
                ORDER BY id DESC
            """, (symbol,)).fetchall()

            if trades:
                pnls = [t['pnl_pct'] for t in trades]
                wins = sum(1 for p in pnls if p > 0)
                total = len(pnls)
                win_rate = wins / total * 100 if total > 0 else 50

                gross_profit = sum(p for p in pnls if p > 0)
                gross_loss = abs(sum(p for p in pnls if p < 0))
                profit_factor = gross_profit / gross_loss if gross_loss > 0 else 1.0

                characteristics[symbol] = SymbolCharacteristics(
                    symbol=symbol,
                    avg_win_rate=round(win_rate / 100, 3),
                    avg_profit_factor=round(profit_factor, 2),
                    total_trades=total,
                )
            else:
                # No data yet, use defaults
                characteristics[symbol] = SymbolCharacteristics(symbol=symbol)

        return characteristics

    def calculate_regime_adjustment(self, symbol: str, regime: str) -> float:
        """
        Adjust threshold based on current market regime.

        Trending markets → lower threshold (easier to enter)
        Choppy markets → higher threshold (harder to enter)
        """
        regime_multipliers = {
            "trend_up": 0.85,       # Easier in uptrend
            "trend_down": 0.90,     # Slightly easier in downtrend
            "expansion": 0.88,      # Easier during expansion
            "compression_pre_breakout": 0.92,  # Pre-breakout, be cautious
            "flat": 1.15,           # Harder in flat market
            "chop": 1.25,           # Much harder in chop
            "squeeze": 1.10,        # Cautious in squeeze
        }

        multiplier = regime_multipliers.get(regime, 1.0)

        # Log the adjustment
        print(f"[ADAPTIVE] {symbol}: regime={regime}, multiplier={multiplier:.2f}")

        return multiplier

    def calculate_performance_adjustment(self, symbol: str) -> float:
        """
        Adjust threshold based on recent performance.

        Good performance → can afford to be more selective (higher threshold)
        Poor performance → need to be less selective (lower threshold)
        """
        chars = self.symbol_characteristics.get(symbol)
        if not chars or chars.total_trades < 10:
            return 1.0  # Not enough data

        # Win rate adjustment
        target_wr = 0.50  # Target 50% win rate
        wr_ratio = target_wr / chars.avg_win_rate if chars.avg_win_rate > 0 else 1.0

        # Clamp to reasonable range
        wr_multiplier = max(0.85, min(1.20, wr_ratio))

        # Profit factor adjustment
        target_pf = 1.3
        pf_ratio = target_pf / chars.avg_profit_factor if chars.avg_profit_factor > 0 else 1.0
        pf_multiplier = max(0.85, min(1.20, pf_ratio))

        # Combined (weight WR more)
        combined = 0.6 * wr_multiplier + 0.4 * pf_multiplier

        print(f"[ADAPTIVE] {symbol}: WR={chars.avg_win_rate:.1%}, PF={chars.avg_profit_factor:.2f}, perf_multiplier={combined:.2f}")

        return combined

    def calculate_volatility_adjustment(self, symbol: str, atr_pct: float) -> float:
        """
        Adjust threshold based on volatility.

        High volatility → higher threshold (need more confidence)
        Low volatility → lower threshold (can enter more easily)
        """
        # Normalize ATR (typical range 0.5% - 3%)
        normalized_atr = max(0.5, min(3.0, atr_pct))

        # Higher volatility = harder to predict = raise threshold
        if normalized_atr > 2.0:
            multiplier = 1.15
        elif normalized_atr > 1.5:
            multiplier = 1.08
        elif normalized_atr > 1.0:
            multiplier = 1.0
        elif normalized_atr > 0.7:
            multiplier = 0.95
        else:
            multiplier = 0.90

        print(f"[ADAPTIVE] {symbol}: ATR={atr_pct:.2f}%, vol_multiplier={multiplier:.2f}")

        return multiplier

    def get_adaptive_threshold(
        self,
        symbol: str,
        regime: str,
        atr_pct: float,
        threshold_type: str = "confirmation"
    ) -> float:
        """
        Get current adaptive threshold for a symbol.

        Args:
            symbol: Trading symbol (BTCUSDT, ETHUSDT, XRPUSDT)
            regime: Current market regime
            atr_pct: Current ATR as percentage
            threshold_type: 'early_signal', 'confirmation', or 'momentum'

        Returns:
            Adjusted threshold value
        """
        # Get base threshold
        base = self.base_thresholds.get(symbol)
        if not base:
            # Fallback to global default
            if threshold_type == "early_signal":
                return self.settings.early_signal_threshold
            elif threshold_type == "confirmation":
                return self.settings.confirmation_threshold
            else:
                return self.settings.momentum_threshold

        # Calculate adjustments
        regime_mult = self.calculate_regime_adjustment(symbol, regime)
        perf_mult = self.calculate_performance_adjustment(symbol)
        vol_mult = self.calculate_volatility_adjustment(symbol, atr_pct)

        # Get base value based on type
        if threshold_type == "early_signal":
            base_value = base.early_signal_threshold
            min_val, max_val = base.min_early, base.max_early
        elif threshold_type == "confirmation":
            base_value = base.confirmation_threshold
            min_val, max_val = base.min_confirmation, base.max_confirmation
        else:  # momentum
            base_value = base.momentum_threshold
            min_val, max_val = base.min_momentum, base.max_momentum

        # Apply adjustments
        adjusted = base_value * regime_mult * perf_mult * vol_mult

        # Apply safety bounds
        adjusted = max(min_val, min(max_val, adjusted))

        # Smooth transition (blend 70% old, 30% new)
        if threshold_type == "early_signal":
            current = base.early_signal_threshold
            smoothed = 0.7 * current + 0.3 * adjusted
            base.early_signal_threshold = smoothed
        elif threshold_type == "confirmation":
            current = base.confirmation_threshold
            smoothed = 0.7 * current + 0.3 * adjusted
            base.confirmation_threshold = smoothed
        else:
            current = base.momentum_threshold
            smoothed = 0.7 * current + 0.3 * adjusted
            base.momentum_threshold = smoothed

        base.last_updated = datetime.now(timezone.utc).isoformat()

        print(f"[ADAPTIVE] {symbol} {threshold_type}: final_threshold={smoothed:.3f}\n")

        return smoothed

    def update_characteristics(self, symbol: str, new_wr: float, new_pf: float) -> None:
        """Update symbol characteristics with new performance data."""
        chars = self.symbol_characteristics.get(symbol)
        if chars:
            # Exponential moving average (weight recent data more)
            alpha = 0.3  # 30% weight to new data
            chars.avg_win_rate = (1 - alpha) * chars.avg_win_rate + alpha * new_wr
            chars.avg_profit_factor = (1 - alpha) * chars.avg_profit_factor + alpha * new_pf
            chars.total_trades += 1

    def save_state(self) -> None:
        """Save current threshold state to database."""
        state = {
            symbol: {
                "early_signal_threshold": thresh.early_signal_threshold,
                "confirmation_threshold": thresh.confirmation_threshold,
                "momentum_threshold": thresh.momentum_threshold,
                "last_updated": thresh.last_updated,
            }
            for symbol, thresh in self.base_thresholds.items()
        }

        self.conn.execute("""
            INSERT OR REPLACE INTO runtime_state (key, value)
            VALUES (?, ?)
        """, ("adaptive_thresholds", json.dumps(state)))
        self.conn.commit()

    def close(self):
        """Close database connection."""
        self.conn.close()
