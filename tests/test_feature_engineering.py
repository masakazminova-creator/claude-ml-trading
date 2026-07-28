"""
Basic unit tests for Feature Engineering module.

Tests cover:
- Feature calculation correctness
- Handling of edge cases (empty data, NaN)
- Multi-timeframe merging
"""

import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_ml.feature_engineering import build_features


class TestFeatureEngineering:
    """Test suite for feature engineering."""

    def create_sample_data(self, n_bars=100):
        """Create sample OHLCV data for testing."""
        dates = pd.date_range("2026-01-01", periods=n_bars, freq="15min")

        # Create simple price series as pandas Series
        close = pd.Series(50000 + np.cumsum(np.random.randn(n_bars) * 100))
        high = close + np.abs(pd.Series(np.random.randn(n_bars) * 50))
        low = close - np.abs(pd.Series(np.random.randn(n_bars) * 50))
        open_price = close.shift(1).fillna(close.iloc[0])
        volume = pd.Series(np.random.uniform(1000, 5000, n_bars))

        # Add turnover (approximate as close * volume)
        turnover = close * volume

        df = pd.DataFrame({
            "ts": dates,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "turnover": turnover,
        })

        return df

    def test_build_features_basic(self):
        """Test that features are built successfully."""
        df = self.create_sample_data()
        featured = build_features(df)

        assert not featured.empty
        assert len(featured) == len(df)
        assert "atr_pct_14" in featured.columns
        assert "rsi_14" in featured.columns
        assert "ema_8_vs_21" in featured.columns

    def test_features_no_nan_after_warmup(self):
        """Test that features don't have NaN after warmup period."""
        df = self.create_sample_data(n_bars=200)  # Enough data for warmup
        featured = build_features(df)

        # After first 50 bars, should have no NaN
        stable_data = featured.iloc[50:]
        nan_count = stable_data.isna().sum().sum()
        assert nan_count == 0, f"Found {nan_count} NaN values in stable region"

    def test_features_with_empty_dataframe(self):
        """Test handling of empty dataframe."""
        df = pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
        featured = build_features(df)

        assert featured.empty

    def test_atr_calculation_positive(self):
        """Test that ATR is always positive."""
        df = self.create_sample_data()
        featured = build_features(df)

        atr_values = featured["atr_pct_14"].dropna()
        assert (atr_values >= 0).all(), "Found negative ATR values"

    def test_rsi_bounds(self):
        """Test that RSI stays within 0-100 bounds."""
        df = self.create_sample_data()
        featured = build_features(df)

        rsi_values = featured["rsi_14"].dropna()
        assert (rsi_values >= 0).all(), "RSI below 0"
        assert (rsi_values <= 100).all(), "RSI above 100"

    def test_bar_close_position_bounds(self):
        """Test that bar close position stays within 0-1."""
        df = self.create_sample_data()
        featured = build_features(df)

        bcp_values = featured["bar_close_position"].dropna()
        assert (bcp_values >= 0).all(), "Bar close position below 0"
        assert (bcp_values <= 1).all(), "Bar close position above 1"

    def test_volume_zscore_normalization(self):
        """Test that volume z-score has mean ~0 and std ~1."""
        df = self.create_sample_data(n_bars=500)  # Need more data for stats
        featured = build_features(df)

        vol_z = featured["vol_zscore"].dropna()

        if len(vol_z) > 10:
            mean = vol_z.mean()
            std = vol_z.std()

            # Mean should be close to 0, std close to 1
            assert abs(mean) < 0.5, f"Volume z-score mean too high: {mean}"
            assert 0.5 < std < 2.0, f"Volume z-score std out of range: {std}"


class TestMultiTimeframeFeatures:
    """Test multi-timeframe feature merging."""

    def create_mtf_data(self):
        """Create multi-timeframe data."""
        # 15m data
        dates_15m = pd.date_range("2026-01-01", periods=100, freq="15min")
        close_15m = pd.Series(50000 + np.cumsum(np.random.randn(100) * 50))
        df_15m = pd.DataFrame({
            "ts": dates_15m,
            "open": close_15m.shift(1).fillna(close_15m.iloc[0]),
            "high": close_15m + np.abs(pd.Series(np.random.randn(100) * 30)),
            "low": close_15m - np.abs(pd.Series(np.random.randn(100) * 30)),
            "close": close_15m,
            "volume": np.random.uniform(1000, 5000, 100),
        })
        df_15m["turnover"] = df_15m["close"] * df_15m["volume"]

        # 60m data (fewer bars)
        dates_60m = pd.date_range("2026-01-01", periods=25, freq="60min")
        close_60m = pd.Series(50000 + np.cumsum(np.random.randn(25) * 100))
        df_60m = pd.DataFrame({
            "ts": dates_60m,
            "open": close_60m.shift(1).fillna(close_60m.iloc[0]),
            "high": close_60m + np.abs(pd.Series(np.random.randn(25) * 60)),
            "low": close_60m - np.abs(pd.Series(np.random.randn(25) * 60)),
            "close": close_60m,
            "volume": np.random.uniform(4000, 20000, 25),
        })
        df_60m["turnover"] = df_60m["close"] * df_60m["volume"]

        return df_15m, {"60": df_60m}

    def test_mtf_merge(self):
        """Test that multi-timeframe features are merged correctly."""
        df_15m, mtf_frames = self.create_mtf_data()

        featured = build_features(df_15m, mtf_frames=mtf_frames)

        # Should have 60m features now
        assert "close_vs_tf60_close" in featured.columns or "tf60_ret_3" in featured.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
