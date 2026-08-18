"""
ATR Percentile Analyzer - Replaces absolute ATR threshold with relative percentile.

Instead of using a fixed ATR threshold (e.g., 0.3%), this module calculates
the historical ATR percentile for each symbol. This allows the system to
enter trades when volatility is low RELATIVE to historical norms, catching
breakouts that occur after compression periods.

Key insight: Low ATR is often a precursor to strong moves.
If current ATR is in the bottom 30% historically but not bottom 10%,
the market is likely preparing for a breakout.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ATRPercentileResult:
    """Result of ATR percentile analysis."""
    current_atr_pct: float          # Current ATR as percentage (e.g., 0.12)
    percentile_30d: float          # 30-day ATR percentile (0-100)
    is_compressed: bool            # True if ATR is low but not extremely low
    is_breakout_setup: bool        # True if compression + preparation signals
    recommended_action: str        # 'allow', 'caution', 'skip'
    bonus_multiplier: float        # Multiplier for evidence score (0.8-1.2)


class ATRPercentileAnalyzer:
    """
    Tracks historical ATR values and calculates percentiles.

    Maintains a rolling window of ATR values to determine if current
    volatility is abnormally low or normal.
    """

    def __init__(self, window_size: int = 200):
        # Store ATR history per symbol
        self.history: Dict[str, deque] = {}
        self.window_size = window_size

        # Thresholds (percentiles)
        self.extreme_compression_threshold = 10  # Bottom 10% = skip
        self.compression_threshold = 30          # Bottom 30% = potential breakout setup

    def update(self, symbol: str, atr_pct: float) -> None:
        """Add new ATR value to history."""
        if symbol not in self.history:
            self.history[symbol] = deque(maxlen=self.window_size)

        self.history[symbol].append(atr_pct)

    def analyze(self, symbol: str, current_atr_pct: float) -> ATRPercentileResult:
        """
        Analyze current ATR in context of historical values.

        Args:
            symbol: Trading symbol
            current_atr_pct: Current ATR as percentage

        Returns:
            ATRPercentileResult with recommendations
        """
        # Update history
        self.update(symbol, current_atr_pct)

        # Need at least 30 samples for meaningful percentile
        if symbol not in self.history or len(self.history[symbol]) < 30:
            return ATRPercentileResult(
                current_atr_pct=current_atr_pct,
                percentile_30d=50.0,  # Default to median
                is_compressed=False,
                is_breakout_setup=False,
                recommended_action='allow',  # Allow if insufficient data
                bonus_multiplier=1.0,
            )

        history_list = sorted(self.history[symbol])

        # Calculate percentile (what % of historical values are below current)
        values_below = sum(1 for v in history_list if v < current_atr_pct)
        percentile = (values_below / len(history_list)) * 100

        # Determine if compressed (low but not extreme)
        is_compressed = percentile < self.compression_threshold
        is_extreme_compression = percentile < self.extreme_compression_threshold

        # Breakout setup: compressed but not extreme (preparing to move)
        is_breakout_setup = (
            is_compressed and not is_extreme_compression
        )

        # Determine action and bonus
        if is_extreme_compression:
            # ATR is in bottom 10% - market truly dead
            recommended_action = 'skip'
            bonus_multiplier = 0.85  # Small penalty
        elif is_breakout_setup:
            # ATR is low but preparing for breakout
            recommended_action = 'allow'
            bonus_multiplier = 1.15  # Bonus for catching breakout!
        elif percentile < 50:
            # ATR is below median - cautious but allowed
            recommended_action = 'caution'
            bonus_multiplier = 1.0
        else:
            # Normal or high volatility - standard
            recommended_action = 'allow'
            bonus_multiplier = 1.0

        return ATRPercentileResult(
            current_atr_pct=current_atr_pct,
            percentile_30d=round(percentile, 1),
            is_compressed=is_compressed,
            is_breakout_setup=is_breakout_setup,
            recommended_action=recommended_action,
            bonus_multiplier=bonus_multiplier,
        )

    def get_stats(self, symbol: str) -> Dict:
        """Get statistics about ATR history for a symbol."""
        if symbol not in self.history or len(self.history[symbol]) < 1:
            return {"samples": 0}

        history_list = list(self.history[symbol])
        return {
            "samples": len(history_list),
            "min": min(history_list),
            "max": max(history_list),
            "avg": sum(history_list) / len(history_list),
            "current": history_list[-1] if history_list else None,
        }
