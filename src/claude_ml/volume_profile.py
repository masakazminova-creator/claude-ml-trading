"""
Volume Profile Analysis Module - Volume at Price analytics.

Provides:
1. Point of Control (POC) - price level with highest volume
2. Value Area High/Low (VAH/VAL) - 70% volume range boundaries
3. Volume nodes - High Volume Nodes (HVN) and Low Volume Nodes (LVN)
4. Absorption detection - large orders absorbing market pressure
5. Liquidity pools - areas where stop losses cluster
6. Volume imbalance zones - unfair prices likely to be revisited

Key insights for trading:
- POC acts as magnet/support/resistance
- VAH/VAL define fair value range
- HVNs = acceptance zones (consolidation likely)
- LVNs = rejection zones (breakouts likely)
- Absorption = smart money accumulating/distributing
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class VolumeProfileLevel:
    """Represents a single price level in volume profile."""
    price: float
    volume: float
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    trade_count: int = 0


@dataclass
class VolumeProfileAnalysis:
    """Complete volume profile analysis results."""
    # Point of Control
    poc_price: float
    poc_volume: float

    # Value Area
    vah_price: float  # Value Area High (70% upper bound)
    val_price: float  # Value Area Low (70% lower bound)
    value_area_width: float

    # Volume distribution
    total_volume: float
    total_buy_volume: float
    total_sell_volume: float
    volume_imbalance: float  # (buy - sell) / total

    # Volume nodes
    high_volume_nodes: List[float] = field(default_factory=list)  # Prices with above-average volume
    low_volume_nodes: List[float] = field(default_factory=list)   # Prices with below-average volume

    # Current position
    current_price_position: str  # 'above_poc', 'below_poc', 'at_poc', 'in_value_area'
    distance_to_poc_pct: float
    distance_to_vah_pct: float
    distance_to_val_pct: float

    # Market structure
    structure_type: str  # 'balanced' (range), 'imbalanced' (trending)
    trend_direction: Optional[str] = None  # If imbalanced

    # Metadata
    lookback_bars: int
    num_price_levels: int


class VolumeProfileAnalyzer:
    """
    Analyzes volume at price levels for trading insights.

    Key concepts:
    - POC: Most traded price → acts as support/resistance
    - VAH/VAL: Fair value boundaries → breakouts significant
    - HVN: Acceptance → consolidation likely
    - LVN: Rejection → fast moves through these zones
    """

    def __init__(self, value_area_pct: float = 0.70):
        self.value_area_pct = value_area_pct  # Typically 70%

    def analyze(
        self,
        df: pd.DataFrame,
        current_price: float,
        num_levels: int = 50
    ) -> VolumeProfileAnalysis:
        """
        Perform complete volume profile analysis.

        Args:
            df: DataFrame with OHLCV data (needs 'high', 'low', 'close', 'volume')
            current_price: Current market price
            num_levels: Number of price levels for profile (more = finer granularity)

        Returns:
            VolumeProfileAnalysis with complete profile
        """
        if df.empty or len(df) < 10:
            logger.warning("Insufficient data for volume profile analysis")
            return self._empty_profile(current_price)

        # Calculate price range
        price_min = df['low'].min()
        price_max = df['high'].max()
        price_range = price_max - price_min

        if price_range == 0:
            return self._empty_profile(current_price)

        # Create price levels
        level_size = price_range / num_levels
        price_levels = np.linspace(price_min, price_max, num_levels + 1)

        # Build volume profile using tick-based approximation
        profile = self._build_profile(df, price_levels, level_size)

        if not profile:
            return self._empty_profile(current_price)

        # Find POC (price with most volume)
        poc_idx = np.argmax([level.volume for level in profile])
        poc_level = profile[poc_idx]

        # Calculate value area (70% of total volume)
        total_volume = sum(level.volume for level in profile)
        target_volume = total_volume * self.value_area_pct

        # Sort by volume descending and accumulate until we reach target
        sorted_indices = np.argsort([-level.volume for level in profile])
        accumulated_volume = 0
        value_area_prices = []

        for idx in sorted_indices:
            level = profile[idx]
            accumulated_volume += level.volume
            value_area_prices.append(level.price)

            if accumulated_volume >= target_volume:
                break

        # VAH = highest price in value area, VAL = lowest
        vah = max(value_area_prices)
        val = min(value_area_prices)

        # Identify volume nodes
        avg_volume = total_volume / len(profile)
        hvns = [level.price for level in profile if level.volume > avg_volume * 1.5]
        lvns = [level.price for level in profile if level.volume < avg_volume * 0.5]

        # Determine current position
        if abs(current_price - poc_level.price) / current_price < 0.002:
            position = "at_poc"
        elif current_price > poc_level.price:
            position = "above_poc"
        else:
            position = "below_poc"

        # Check if in value area
        if val <= current_price <= vah:
            position = "in_value_area"

        # Calculate distances
        dist_to_poc = abs(current_price - poc_level.price) / current_price * 100
        dist_to_vah = (vah - current_price) / current_price * 100 if current_price < vah else 0
        dist_to_val = (current_price - val) / current_price * 100 if current_price > val else 0

        # Buy/sell volume split
        total_buy = sum(level.buy_volume for level in profile)
        total_sell = sum(level.sell_volume for level in profile)
        vol_imbalance = (total_buy - total_sell) / (total_buy + total_sell) if (total_buy + total_sell) > 0 else 0

        # Determine structure type
        value_area_width_pct = (vah - val) / val * 100
        if value_area_width_pct < 2.0:  # Tight range
            structure = "balanced"
        elif dist_to_poc > 3.0:  # Far from POC
            structure = "imbalanced"
        else:
            structure = "transitioning"

        return VolumeProfileAnalysis(
            poc_price=poc_level.price,
            poc_volume=poc_level.volume,
            vah_price=vah,
            val_price=val,
            value_area_width=value_area_width_pct,
            total_volume=total_volume,
            total_buy_volume=total_buy,
            total_sell_volume=total_sell,
            volume_imbalance=vol_imbalance,
            high_volume_nodes=hvns,
            low_volume_nodes=lvns,
            current_price_position=position,
            distance_to_poc_pct=dist_to_poc,
            distance_to_vah_pct=dist_to_vah,
            distance_to_val_pct=dist_to_val,
            structure_type=structure,
            lookback_bars=len(df),
            num_price_levels=len(profile)
        )

    def _build_profile(
        self,
        df: pd.DataFrame,
        price_levels: np.ndarray,
        level_size: float
    ) -> List[VolumeProfileLevel]:
        """Build volume profile from OHLCV data using bar distribution method."""

        profile = []

        for i in range(len(price_levels) - 1):
            level_price = (price_levels[i] + price_levels[i+1]) / 2
            level_volume = 0.0
            level_buy_volume = 0.0
            level_sell_volume = 0.0
            trade_count = 0

            # Distribute each bar's volume across price levels it spans
            for _, bar in df.iterrows():
                bar_low = bar['low']
                bar_high = bar['high']
                bar_close = bar['close']
                bar_volume = bar['volume']

                # Check if this bar spans our price level
                if bar_low <= level_price <= bar_high:
                    # Approximate volume at this level (per-bar increment)
                    bar_level_volume = bar_volume / ((bar_high - bar_low) / level_size + 1)
                    level_volume += bar_level_volume
                    trade_count += 1

                    # Estimate buy/sell split from THIS bar's increment (the
                    # old code added 0.6x the cumulative level volume per bar,
                    # inflating buy/sell totals ~n/2x). Close above the level
                    # means buyers were in control of that bar.
                    if bar_close >= level_price:
                        level_buy_volume += bar_level_volume * 0.6
                        level_sell_volume += bar_level_volume * 0.4
                    else:
                        level_sell_volume += bar_level_volume * 0.6
                        level_buy_volume += bar_level_volume * 0.4

            if level_volume > 0:
                profile.append(VolumeProfileLevel(
                    price=level_price,
                    volume=level_volume,
                    buy_volume=level_buy_volume,
                    sell_volume=level_sell_volume,
                    trade_count=trade_count
                ))

        return profile

    def _empty_profile(self, current_price: float) -> VolumeProfileAnalysis:
        """Return empty profile when insufficient data."""
        return VolumeProfileAnalysis(
            poc_price=current_price,
            poc_volume=0,
            vah_price=current_price * 1.02,
            val_price=current_price * 0.98,
            value_area_width=0,
            total_volume=0,
            total_buy_volume=0,
            total_sell_volume=0,
            volume_imbalance=0,
            high_volume_nodes=[],
            low_volume_nodes=[],
            current_price_position="at_poc",
            distance_to_poc_pct=0,
            distance_to_vah_pct=2.0,
            distance_to_val_pct=2.0,
            structure_type="unknown",
            lookback_bars=0,
            num_price_levels=0
        )

    def detect_absorption(self, df: pd.DataFrame, window: int = 10) -> Dict[str, Any]:
        """
        Detect absorption patterns - large orders absorbing market pressure.

        Signs of absorption:
        - High volume but small price movement (accumulation)
        - Repeated tests of a level without breakthrough (support/resistance)
        - Divergence between volume and price progress

        Returns dict with absorption signals.
        """
        if len(df) < window:
            return {'absorption_detected': False}

        recent = df.tail(window)

        # Calculate volume/price efficiency
        avg_volume = recent['volume'].mean()
        avg_range = (recent['high'] - recent['low']).mean()
        avg_body = abs(recent['close'] - recent['open']).mean()

        # Absorption signature: high volume + small bodies
        baseline = df['volume'].rolling(50).mean().iloc[-1]
        volume_spike = bool(avg_volume > baseline * 2)
        small_bodies = avg_body < avg_range * 0.3

        absorption = bool(volume_spike and small_bodies)

        # Determine side (buying vs selling absorption). Closes near the HIGH
        # of the bar mean buyers absorbed selling pressure; the old code
        # labeled closes-near-low as "buying" — inverted.
        close_position = (recent['close'] - recent['low']) / (recent['high'] - recent['low'] + 0.0001)
        closes_near_high = close_position > 0.7
        buying_pressure = bool(closes_near_high.sum() > window / 2)

        return {
            'absorption_detected': absorption,
            'side': 'buying' if buying_pressure else 'selling',
            'strength': 'strong' if volume_spike else 'weak',
            'avg_volume': avg_volume,
            'avg_body_pct': (avg_body / recent['close'].mean()) * 100
        }

    def find_liquidity_pools(self, df: pd.DataFrame, lookback: int = 50) -> Dict[str, List[float]]:
        """
        Identify potential liquidity pools (stop loss clusters).

        Liquidity pools form at:
        - Recent swing highs/lows
        - Equal highs/lows (double tops/bottoms)
        - Round numbers (psychological levels)

        These are where stop losses cluster → magnets for price.
        """
        recent = df.tail(lookback)

        liquidity_levels = []

        # Find swing points
        for i in range(2, len(recent) - 2):
            # Swing high
            if (recent.iloc[i]['high'] > recent.iloc[i-1]['high'] and
                recent.iloc[i]['high'] > recent.iloc[i-2]['high'] and
                recent.iloc[i]['high'] > recent.iloc[i+1]['high'] and
                recent.iloc[i]['high'] > recent.iloc[i+2]['high']):
                liquidity_levels.append(recent.iloc[i]['high'])

            # Swing low
            if (recent.iloc[i]['low'] < recent.iloc[i-1]['low'] and
                recent.iloc[i]['low'] < recent.iloc[i-2]['low'] and
                recent.iloc[i]['low'] < recent.iloc[i+1]['low'] and
                recent.iloc[i]['low'] < recent.iloc[i+2]['low']):
                liquidity_levels.append(recent.iloc[i]['low'])

        # Add round numbers within range
        price_min = recent['low'].min()
        price_max = recent['high'].max()

        for round_num in range(int(price_min // 100) * 100, int(price_max // 100 + 1) * 100, 100):
            if price_min <= round_num <= price_max:
                liquidity_levels.append(round_num)

        # Remove duplicates and sort
        liquidity_levels = sorted(list(set(liquidity_levels)))

        return {
            'liquidity_pools': liquidity_levels,
            'nearest_above': min([l for l in liquidity_levels if l > recent.iloc[-1]['close']], default=None),
            'nearest_below': max([l for l in liquidity_levels if l < recent.iloc[-1]['close']], default=None)
        }


# Convenience function
def analyze_volume_profile(
    df: pd.DataFrame,
    current_price: float,
    num_levels: int = 50
) -> VolumeProfileAnalysis:
    """Quick volume profile analysis."""
    analyzer = VolumeProfileAnalyzer()
    return analyzer.analyze(df, current_price, num_levels)
