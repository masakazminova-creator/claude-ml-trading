"""
Basic unit tests for Risk Manager module.

Tests cover:
- Position sizing calculations
- Drawdown tracking
- Circuit breaker logic
"""

import pytest
from unittest.mock import Mock

# Import the module to test
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_ml.config import Settings
from claude_ml.risk_manager import RiskManager


class TestRiskManager:
    """Test suite for RiskManager."""

    def setup_method(self):
        """Setup test fixtures."""
        self.settings = Settings()
        self.risk_manager = RiskManager(self.settings)

    def test_initial_state(self):
        """Test initial risk manager state."""
        assert self.risk_manager.current_balance == 10000.0
        assert self.risk_manager.daily_pnl == 0.0
        assert self.risk_manager.drawdown_pct == 0.0
        assert self.risk_manager.win_count == 0
        assert self.risk_manager.loss_count == 0

    def test_update_performance_win(self):
        """Test updating performance after a winning trade."""
        self.risk_manager.update_performance(pnl_pct=1.5, symbol="BTCUSDT")

        assert self.risk_manager.win_count == 1
        assert self.risk_manager.loss_count == 0
        assert self.risk_manager.current_balance > 10000.0

    def test_update_performance_loss(self):
        """Test updating performance after a losing trade."""
        initial_balance = self.risk_manager.current_balance
        self.risk_manager.update_performance(pnl_pct=-1.0, symbol="BTCUSDT")

        assert self.risk_manager.loss_count == 1
        assert self.risk_manager.current_balance < initial_balance

    def test_peak_balance_tracking(self):
        """Test that peak balance is tracked correctly."""
        # Start at 10000
        assert self.risk_manager.peak_balance == 10000.0

        # Win trade → balance increases, peak should update
        self.risk_manager.update_performance(pnl_pct=10.0, symbol="BTCUSDT")
        assert self.risk_manager.current_balance == 11000.0
        assert self.risk_manager.peak_balance == 11000.0

        # Loss trade → balance decreases, peak should stay same
        self.risk_manager.update_performance(pnl_pct=-5.0, symbol="BTCUSDT")
        assert self.risk_manager.current_balance < 11000.0
        assert self.risk_manager.peak_balance == 11000.0  # Still at peak!

    def test_drawdown_calculation(self):
        """Test drawdown calculation from peak."""
        # Win to create peak
        self.risk_manager.update_performance(pnl_pct=10.0, symbol="BTCUSDT")
        peak = self.risk_manager.peak_balance  # Should be 11000

        # Loss to create drawdown
        self.risk_manager.update_performance(pnl_pct=-5.0, symbol="BTCUSDT")

        # Drawdown should be calculated from peak, not start balance
        expected_dd = ((peak - self.risk_manager.current_balance) / peak) * 100
        assert abs(self.risk_manager.drawdown_pct - expected_dd) < 0.01

    def test_circuit_breaker_emergency_stop(self):
        """Test circuit breaker fires on severe drawdown with real assertions."""
        # Simulate catastrophic loss: -35% → drawdown far above pause threshold
        self.risk_manager.update_performance(pnl_pct=-35.0, symbol="BTCUSDT")

        allowed, reason = self.risk_manager.check_circuit_breakers()

        # Drawdown here is 35% (peak=10000, balance=6500), pause threshold 12%
        # → trading NOT allowed. Contract: (allowed=False, explanatory reason).
        # Previously this test only asserted types, so a fully broken
        # circuit breaker would still pass.
        assert allowed is False, f"circuit breaker should block at 35% drawdown"
        assert reason
        assert "drawdown" in reason.lower()

    def test_position_size_within_bounds(self):
        """Test that position size is within reasonable bounds."""
        risk_result = self.risk_manager.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000.0,
            atr=500.0,  # 1% ATR
            regime="trend_up",
            model_confidence=0.75,
            side="long",
        )

        # Position size should be positive and reasonable
        assert risk_result.adjusted_size_pct > 0
        assert risk_result.adjusted_size_pct <= self.risk_manager.settings.max_position_size_pct

        # TP should be above entry for long
        assert risk_result.take_profit_price > 50000.0

        # SL should be below entry for long
        assert risk_result.stop_loss_price < 50000.0


class TestPositionSizing:
    """Test position sizing logic."""

    def setup_method(self):
        """Setup test fixtures."""
        self.settings = Settings()
        self.risk_manager = RiskManager(self.settings)

    def test_regime_multiplier_chop(self):
        """Test position size reduction in chop regime."""
        result_normal = self.risk_manager.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000.0,
            atr=500.0,
            regime="trend_up",
            model_confidence=0.75,
            side="long",
        )

        result_chop = self.risk_manager.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000.0,
            atr=500.0,
            regime="chop",
            model_confidence=0.75,
            side="long",
        )

        # Chop should have smaller position
        assert result_chop.adjusted_size_pct < result_normal.adjusted_size_pct

    def test_high_confidence_increases_size(self):
        """Test that high model confidence increases position size."""
        result_low_conf = self.risk_manager.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000.0,
            atr=500.0,
            regime="trend_up",
            model_confidence=0.60,
            side="long",
        )

        result_high_conf = self.risk_manager.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000.0,
            atr=500.0,
            regime="trend_up",
            model_confidence=0.90,
            side="long",
        )

        # Higher confidence should increase size
        assert result_high_conf.adjusted_size_pct > result_low_conf.adjusted_size_pct


    def test_take_profit_capped_at_max_pct(self):
        """TP (trailing-activation trigger) is capped at max_take_profit_pct.

        A far ATR-based TP (2.5x here = 5%) would be hunted and often reversed
        into a loss; the cap arms the trailing stop sooner at +0.80% / -0.80%.
        """
        long_result = self.risk_manager.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000.0, atr=1000.0,
            regime="trend_up", model_confidence=0.75, side="long",
        )
        short_result = self.risk_manager.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000.0, atr=1000.0,
            regime="trend_up", model_confidence=0.75, side="short",
        )
        # 1.50% of 50000 = 750 -> capped TP distance
        assert abs(long_result.take_profit_price - 50750.0) < 0.01
        assert abs(short_result.take_profit_price - 49250.0) < 0.01


    def test_stop_loss_floored_at_min_pct(self):
        """SL is never tighter than min_stop_loss_pct, so low-vol noise doesn't stop out trades."""
        short_result = self.risk_manager.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000.0, atr=100.0,  # 0.2% ATR -> 2x = 0.4%, floored to 0.80%
            regime="flat", model_confidence=0.75, side="short",
        )
        long_result = self.risk_manager.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000.0, atr=100.0,
            regime="flat", model_confidence=0.75, side="long",
        )
        # 0.80% of 50000 = 400 -> SL floor distance (not the 0.4% ATR-based one)
        assert abs((short_result.stop_loss_price - 50000.0) - 400.0) < 0.01
        assert short_result.stop_loss_price > 50000.0
        assert abs((50000.0 - long_result.stop_loss_price) - 400.0) < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
