"""
Online Feature Importance - Dynamic feature selection based on current market conditions.

Instead of using static feature importance from training, this module continuously
monitors which features are predictive RIGHT NOW and adjusts feature selection accordingly.

Key benefits:
- Adapts to changing market regimes automatically
- Filters out noisy/irrelevant features in real-time
- Focuses models on currently working signals
- Reduces overfitting to stale patterns
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FeatureMetrics:
    """Tracking metrics for a single feature."""
    name: str
    rolling_correlation: float = 0.0  # Correlation with target over recent window
    stability_score: float = 1.0      # How consistent the feature is (0-1)
    noise_ratio: float = 0.0          # Signal-to-noise ratio (lower is better)
    last_updated: str = ""


class OnlineFeatureSelector:
    """
    Continuously monitors feature importance and selects relevant features.

    Uses rolling window analysis to detect:
    1. Which features are currently predictive
    2. Which features have become noisy
    3. When to switch feature sets based on regime
    """

    def __init__(
        self,
        rolling_window: int = 50,       # Look back 50 bars (~12.5 hours on 15m)
        min_correlation: float = 0.05,   # Minimum correlation to keep feature
        max_noise_ratio: float = 2.0,    # Maximum noise ratio before excluding
        update_interval_bars: int = 10,  # Update every 10 bars
    ):
        self.rolling_window = rolling_window
        self.min_correlation = min_correlation
        self.max_noise_ratio = max_noise_ratio
        self.update_interval_bars = update_interval_bars

        # State tracking
        self.feature_metrics: Dict[str, FeatureMetrics] = {}
        self.active_features: List[str] = []
        self.bar_count = 0
        self.last_update_bar = 0

    def update_feature_importance(
        self,
        df: pd.DataFrame,
        target_column: str = "long_target",
        all_features: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Update feature importance using recent data.

        Args:
            df: Recent market data with features and labels
            target_column: Target variable to correlate against
            all_features: Optional list of all available features

        Returns:
            List of active/relevant features for current market
        """
        self.bar_count += 1

        # Only update at specified intervals
        if self.bar_count - self.last_update_bar < self.update_interval_bars:
            return self.active_features

        self.last_update_bar = self.bar_count

        if df.empty or len(df) < self.rolling_window:
            logger.warning(f"Not enough data for feature update ({len(df)} bars)")
            return self.active_features

        # Use only recent data for relevance
        recent_df = df.tail(self.rolling_window).copy()

        # Get feature list
        if all_features is None:
            all_features = [col for col in recent_df.columns
                          if col not in ['ts', 'open', 'high', 'low', 'close', 'volume', target_column]]

        # Calculate rolling correlations
        new_active_features = []
        for feature in all_features:
            if feature not in recent_df.columns or target_column not in recent_df.columns:
                continue

            # Skip if too many NaN values
            if recent_df[feature].isna().sum() > len(recent_df) * 0.3:
                continue

            # Calculate correlation with target
            valid_data = recent_df[[feature, target_column]].dropna()
            if len(valid_data) < 20:
                continue

            correlation = abs(valid_data[feature].corr(valid_data[target_column]))
            if np.isnan(correlation):
                continue

            # Calculate noise ratio (std / mean of absolute values)
            feature_std = valid_data[feature].std()
            feature_mean = abs(valid_data[feature]).mean()
            noise_ratio = feature_std / feature_mean if feature_mean > 0 else float('inf')

            # Update or create metrics
            if feature not in self.feature_metrics:
                self.feature_metrics[feature] = FeatureMetrics(name=feature)

            metrics = self.feature_metrics[feature]
            metrics.rolling_correlation = round(float(correlation), 4)
            metrics.noise_ratio = round(float(noise_ratio), 2)

            # Stability score based on consistency across sub-windows
            metrics.stability_score = self._calculate_stability(recent_df, feature, target_column)
            metrics.last_updated = datetime.now(timezone.utc).isoformat()

            # Decide if feature should be active
            if (correlation >= self.min_correlation and
                noise_ratio <= self.max_noise_ratio):
                new_active_features.append(feature)

        # Update active features (compute the diff BEFORE overwriting — the
        # old code reassigned self.active_features first, then diffed it
        # against itself, so "added"/"removed" were always empty)
        old_features = list(self.active_features)
        old_count = len(old_features)
        new_count = len(new_active_features)

        self.active_features = new_active_features

        # Log changes
        if old_count != new_count:
            logger.info(f"[FEATURE UPDATE] Active features: {old_count} → {new_count}")

        added = set(new_active_features) - set(old_features)
        removed = set(old_features) - set(new_active_features)

        if added:
            logger.debug(f"  Added: {', '.join(list(added)[:5])}")
        if removed:
            logger.debug(f"  Removed: {', '.join(list(removed)[:5])}")

        return self.active_features

    def _calculate_stability(
        self,
        df: pd.DataFrame,
        feature: str,
        target: str,
        n_splits: int = 5,
    ) -> float:
        """
        Calculate how stable the feature-target relationship is across sub-windows.

        Returns 0-1 where 1 means very consistent.
        """
        chunk_size = len(df) // n_splits
        if chunk_size < 10:
            return 0.5

        correlations = []
        for i in range(n_splits):
            chunk = df.iloc[i*chunk_size:(i+1)*chunk_size]
            valid_data = chunk[[feature, target]].dropna()

            if len(valid_data) >= 10:
                corr = abs(valid_data[feature].corr(valid_data[target]))
                if not np.isnan(corr):
                    correlations.append(corr)

        if len(correlations) < 2:
            return 0.3

        # Stability = 1 - coefficient of variation
        mean_corr = np.mean(correlations)
        std_corr = np.std(correlations)
        cv = std_corr / mean_corr if mean_corr > 0 else float('inf')

        return round(max(0.0, 1.0 - cv), 3)

    def get_top_features(self, n: int = 10) -> List[Dict]:
        """Get top N most important features by current correlation."""
        sorted_features = sorted(
            self.feature_metrics.values(),
            key=lambda m: m.rolling_correlation,
            reverse=True,
        )

        return [
            {
                "name": m.name,
                "correlation": m.rolling_correlation,
                "stability": m.stability_score,
                "noise_ratio": m.noise_ratio,
                "last_updated": m.last_updated,
            }
            for m in sorted_features[:n]
            if m.rolling_correlation > 0
        ]

    def get_feature_summary(self) -> Dict:
        """Get summary of current feature selection state."""
        active_count = len(self.active_features)
        total_tracked = len(self.feature_metrics)

        avg_correlation = np.mean([
            m.rolling_correlation for m in self.feature_metrics.values()
            if m.rolling_correlation > 0
        ]) if self.feature_metrics else 0.0

        return {
            "active_features": active_count,
            "total_tracked": total_tracked,
            "avg_correlation": round(float(avg_correlation), 4),
            "last_update_bar": self.last_update_bar,
            "top_features": self.get_top_features(n=5),
        }
