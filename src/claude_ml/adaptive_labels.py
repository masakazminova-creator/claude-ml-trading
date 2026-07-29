"""
Adaptive label generation based on current market volatility.

Instead of fixed min_return_pct, adjusts targets based on ATR to ensure
labels are achievable in current market conditions.
"""

import pandas as pd


def calculate_adaptive_min_return(df: pd.DataFrame, base_return_pct: float = 0.35) -> float:
    """
    Calculate adaptive minimum return percentage based on current ATR.

    Args:
        df: DataFrame with OHLCV data (must have 'atr_14' and 'close' columns)
        base_return_pct: Base target return (default 0.35%)

    Returns:
        Adaptive min return % that's achievable in current market

    Logic:
        - If ATR is low (< 1%): reduce target (easier to achieve)
        - If ATR is high (> 2%): can increase target slightly
        - Target should be ~50-70% of typical move to get balanced labels
    """
    if df.empty or 'atr_14' not in df.columns:
        return base_return_pct

    # Calculate recent ATR as percentage of price
    recent_atr_pct = (df['atr_14'].iloc[-1] / df['close'].iloc[-1]) * 100

    # Scale target based on ATR
    # Low vol (0.5% ATR) → target 0.15%
    # Normal vol (1.5% ATR) → target 0.35%
    # High vol (3% ATR) → target 0.60%
    if recent_atr_pct < 0.8:
        # Very low volatility - significantly reduce target
        adaptive = max(0.12, base_return_pct * 0.4)
    elif recent_atr_pct < 1.2:
        # Low volatility - reduce target
        adaptive = max(0.18, base_return_pct * 0.6)
    elif recent_atr_pct < 2.0:
        # Normal volatility - use base target
        adaptive = base_return_pct
    else:
        # High volatility - can increase target
        adaptive = min(0.60, base_return_pct * 1.3)

    return round(adaptive, 2)


def create_balanced_labels(
    df: pd.DataFrame,
    horizon_bars: int = 6,
    base_min_return_pct: float = 0.35,
    take_profit_mult: float = 2.0,
    stop_loss_mult: float = 1.5,
    max_hold_bars: int = 20
) -> pd.DataFrame:
    """
    Create balanced labels with adaptive min_return based on volatility.

    This ensures positive rate stays around 35-45% instead of dropping to 16%.

    Args:
        df: OHLCV dataframe
        horizon_bars: How many bars ahead to check
        base_min_return_pct: Base target (will be adjusted)
        take_profit_mult: TP multiplier for label validation
        stop_loss_mult: SL multiplier for label validation
        max_hold_bars: Maximum bars to hold position

    Returns:
        DataFrame with long_target and short_target columns
    """
    labeled = df.copy()

    # Calculate adaptive min return
    adaptive_min_return = calculate_adaptive_min_return(df, base_min_return_pct)

    # Use realistic TP/SL based on ATR
    atr = df['atr_14'].iloc[-1] if 'atr_14' in df.columns else df['close'].std()
    tp_pct = (atr / df['close'].iloc[-1]) * 100 * take_profit_mult
    sl_pct = (atr / df['close'].iloc[-1]) * 100 * stop_loss_mult

    # Ensure reasonable bounds
    tp_pct = max(0.3, min(2.0, tp_pct))
    sl_pct = max(0.2, min(1.5, sl_pct))

    # Create labels using existing function
    from claude_ml.feature_engineering import attach_labels

    result = attach_labels(
        labeled,
        horizon_bars=horizon_bars,
        min_return_pct=adaptive_min_return,
        take_profit_pct=float(tp_pct),
        stop_loss_pct=float(sl_pct),
        max_hold_bars=max_hold_bars
    )

    # Log what we did
    pos_rate_long = result['long_target'].dropna().mean() * 100
    pos_rate_short = result['short_target'].dropna().mean() * 100

    print(f"[ADAPTIVE LABELS] min_return={adaptive_min_return:.2f}% (base={base_min_return_pct}%)")
    print(f"[ADAPTIVE LABELS] TP={tp_pct:.2f}%, SL={sl_pct:.2f}%")
    print(f"[ADAPTIVE LABELS] Long positive rate: {pos_rate_long:.1f}%")
    print(f"[ADAPTIVE LABELS] Short positive rate: {pos_rate_short:.1f}%")

    return result
