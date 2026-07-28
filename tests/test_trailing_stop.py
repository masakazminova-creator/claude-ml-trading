"""
Unit tests for ATR-based Trailing Stop system.

Tests cover:
- Trailing stop creation
- Price updates
- Activation logic
- Exit detection
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_ml.trailing_stop import (
    TrailingStopState,
    create_trailing_stop,
    update_trailing_stop,
    check_trailing_stop_exit,
)


class TestTrailingStopCreation:
    """Test trailing stop initialization."""

    def test_create_long_position(self):
        """Test creating trailing stop for long position."""
        state = create_trailing_stop(
            symbol="BTCUSDT",
            side="long",
            entry_price=50000.0,
            atr=500.0,
            trigger_mult=0.5,
            stop_mult=1.5,
        )

        assert state.symbol == "BTCUSDT"
        assert state.side == "long"
        assert state.entry_price == 50000.0
        assert state.highest_price == 50000.0
        assert state.is_active is False

        # Initial stop should be below entry
        expected_stop = 50000.0 - (500.0 * 1.5)  # entry - 1.5 ATR
        assert abs(state.current_stop_price - expected_stop) < 0.01

    def test_create_short_position(self):
        """Test creating trailing stop for short position."""
        state = create_trailing_stop(
            symbol="BTCUSDT",
            side="short",
            entry_price=50000.0,
            atr=500.0,
        )

        # Initial stop should be above entry for short
        expected_stop = 50000.0 + (500.0 * 1.5)  # entry + 1.5 ATR
        assert abs(state.current_stop_price - expected_stop) < 0.01


class TestTrailingStopUpdates:
    """Test trailing stop price updates."""

    def setup_method(self):
        """Create a long position for testing."""
        self.state = create_trailing_stop(
            symbol="BTCUSDT",
            side="long",
            entry_price=50000.0,
            atr=500.0,
        )

    def test_highest_price_updates_on_rise(self):
        """Test that highest price updates when price rises."""
        # Price goes up to 51000
        updated = update_trailing_stop(self.state, 51000.0, atr=500.0)

        assert updated.highest_price == 51000.0

    def test_highest_price_stays_on_drop(self):
        """Test that highest price doesn't decrease."""
        # First go up
        update_trailing_stop(self.state, 51000.0, atr=500.0)

        # Then drop
        updated = update_trailing_stop(self.state, 50500.0, atr=500.0)

        # Highest should stay at 51000
        assert updated.highest_price == 51000.0

    def test_activation_after_trigger_distance(self):
        """Test that trailing activates after trigger distance reached."""
        # Trigger distance = 0.5 ATR = 250
        # Price needs to go to 50250 to activate

        # Move just below trigger
        updated = update_trailing_stop(self.state, 50249.0, atr=500.0)
        assert updated.is_active is False

        # Move above trigger
        updated = update_trailing_stop(self.state, 50251.0, atr=500.0)
        assert updated.is_active is True

    def test_stop_only_moves_up_for_long(self):
        """Test that stop only moves up (never down) for long positions."""
        # Activate trailing
        update_trailing_stop(self.state, 51000.0, atr=500.0)
        first_stop = self.state.current_stop_price

        # Price drops but stop should stay
        update_trailing_stop(self.state, 50800.0, atr=500.0)
        second_stop = self.state.current_stop_price

        # Stop should not have moved down
        assert second_stop >= first_stop


class TestTrailingStopExit:
    """Test exit detection logic."""

    def test_no_exit_before_activation(self):
        """Test that no exit signal before activation."""
        state = create_trailing_stop("BTCUSDT", "long", 50000.0, 500.0)

        # Price hasn't moved enough to activate
        assert check_trailing_stop_exit(state, 50100.0) is False

    def test_exit_on_stop_hit_long(self):
        """Test exit when price hits stop for long position."""
        state = create_trailing_stop("BTCUSDT", "long", 50000.0, 500.0)

        # Activate trailing by moving price up significantly
        update_trailing_stop(state, 52000.0, atr=500.0)

        # Now stop should be active at some level
        assert state.is_active is True

        # Price drops to stop level
        exit_triggered = check_trailing_stop_exit(state, state.current_stop_price - 10)
        assert exit_triggered is True

    def test_no_exit_while_above_stop_long(self):
        """Test no exit while price stays above stop for long."""
        state = create_trailing_stop("BTCUSDT", "long", 50000.0, 500.0)

        # Activate and move up
        update_trailing_stop(state, 52000.0, atr=500.0)

        # Price stays above stop
        exit_triggered = check_trailing_stop_exit(state, state.current_stop_price + 100)
        assert exit_triggered is False


class TestShortPositionTrailing:
    """Test trailing stop for short positions."""

    def test_short_lowest_price_updates(self):
        """Test that lowest price updates when price drops for short."""
        state = create_trailing_stop("BTCUSDT", "short", 50000.0, 500.0)

        # Price drops to 49000
        updated = update_trailing_stop(state, 49000.0, atr=500.0)

        assert updated.lowest_price == 49000.0

    def test_short_stop_only_moves_down(self):
        """Test that stop only moves down (never up) for short positions."""
        state = create_trailing_stop("BTCUSDT", "short", 50000.0, 500.0)

        # Activate trailing by dropping price
        update_trailing_stop(state, 48000.0, atr=500.0)
        first_stop = state.current_stop_price

        # Price rises but stop should stay
        update_trailing_stop(state, 48500.0, atr=500.0)
        second_stop = state.current_stop_price

        # Stop should not have moved up
        assert second_stop <= first_stop


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
