"""
ATR-based Trailing Stop System.

Instead of fixed percentage (0.5%), uses Average True Range to dynamically
adjust trailing distance based on market volatility.

Benefits:
- Wider stops in volatile markets (fewer false exits)
- Tighter stops in calm markets (protect profits better)
- Adapts to each asset's characteristics automatically
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TrailingStopState:
    """Current state of a trailing stop for a position."""
    symbol: str
    side: str
    entry_price: float
    current_stop_price: float
    highest_price: float  # For long positions
    lowest_price: float   # For short positions
    is_active: bool = False  # Becomes active after trigger price reached
    trigger_distance_atr_mult: float = 0.5  # ATR multiplier to activate
    stop_distance_atr_mult: float = 1.5     # ATR multiplier for stop distance


def calculate_atr_trailing_stop(
    atr: float,
    current_price: float,
    highest_price: float,
    lowest_price: float,
    entry_price: float,
    side: str,
    trigger_mult: float = 0.5,
    stop_mult: float = 1.5,
) -> tuple[float, bool]:
    """
    Calculate ATR-based trailing stop price.

    Args:
        atr: Current ATR value
        current_price: Current market price
        highest_price: Highest price since entry (for long)
        lowest_price: Lowest price since entry (for short)
        entry_price: Original entry price
        side: 'long' or 'short'
        trigger_mult: ATR multiplier to activate trailing
        stop_mult: ATR multiplier for stop distance

    Returns:
        (new_stop_price, is_triggered)
    """
    trigger_distance = atr * trigger_mult
    stop_distance = atr * stop_mult

    if side == "long":
        # Check if price moved enough to activate trailing
        # Trigger distance from entry price
        profit_from_entry = current_price - entry_price
        is_triggered = profit_from_entry >= trigger_distance

        if is_triggered:
            # Trail below highest price
            new_stop = highest_price - stop_distance
            return new_stop, True
        else:
            return 0.0, False

    else:  # short
        # Check if price moved enough to activate trailing
        # Trigger distance from entry price
        profit_from_entry = entry_price - current_price
        is_triggered = profit_from_entry >= trigger_distance

        if is_triggered:
            # Trail above lowest price
            new_stop = lowest_price + stop_distance
            return new_stop, True
        else:
            return 0.0, False


def update_trailing_stop(
    state: TrailingStopState,
    current_price: float,
    atr: float,
) -> TrailingStopState:
    """
    Update trailing stop state with new price data.

    Args:
        state: Current trailing stop state
        current_price: Current market price
        atr: Current ATR value

    Returns:
        Updated trailing stop state
    """
    # Update highest/lowest prices
    if state.side == "long":
        state.highest_price = max(state.highest_price, current_price)
    else:
        state.lowest_price = min(state.lowest_price, current_price)

    # Calculate new stop price
    new_stop, is_triggered = calculate_atr_trailing_stop(
        atr=atr,
        current_price=current_price,
        highest_price=state.highest_price,
        lowest_price=state.lowest_price,
        entry_price=state.entry_price,
        side=state.side,
        trigger_mult=state.trigger_distance_atr_mult,
        stop_mult=state.stop_distance_atr_mult,
    )

    # Update state
    if is_triggered:
        state.is_active = True
        if state.side == "long":
            # For long, stop should only move up
            if new_stop > state.current_stop_price:
                state.current_stop_price = new_stop
        else:
            # For short, stop should only move down
            if new_stop < state.current_stop_price:
                state.current_stop_price = new_stop
    elif not state.is_active:
        # If not yet active, check if we need to update based on current price movement
        # This ensures highest/lowest are tracked even before activation
        pass

    logger.debug(
        f"[{state.symbol}] Trailing stop updated: "
        f"price={current_price:.4f}, highest={state.highest_price:.4f}, "
        f"stop={state.current_stop_price:.4f}, active={state.is_active}"
    )

    return state


def check_trailing_stop_exit(
    state: TrailingStopState,
    current_price: float,
) -> bool:
    """
    Check if current price has hit the trailing stop.

    Args:
        state: Current trailing stop state
        current_price: Current market price

    Returns:
        True if stop hit, position should be closed
    """
    if not state.is_active:
        return False

    if state.side == "long":
        return current_price <= state.current_stop_price
    else:
        return current_price >= state.current_stop_price


def create_trailing_stop(
    symbol: str,
    side: str,
    entry_price: float,
    atr: float,
    trigger_mult: float = 0.5,
    stop_mult: float = 1.5,
) -> TrailingStopState:
    """
    Create initial trailing stop state for a new position.

    Args:
        symbol: Trading symbol
        side: 'long' or 'short'
        entry_price: Entry price
        atr: Current ATR value
        trigger_mult: ATR multiplier to activate trailing
        stop_mult: ATR multiplier for stop distance

    Returns:
        Initialized TrailingStopState
    """
    initial_stop_distance = atr * stop_mult

    if side == "long":
        initial_stop = entry_price - initial_stop_distance
    else:
        initial_stop = entry_price + initial_stop_distance

    return TrailingStopState(
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        current_stop_price=initial_stop,
        highest_price=entry_price,
        lowest_price=entry_price,
        is_active=False,
        trigger_distance_atr_mult=trigger_mult,
        stop_distance_atr_mult=stop_mult,
    )
