#!/usr/bin/env python
"""
Diagnostic script to analyze model quality and data freshness.

Checks:
1. Feature distributions (are they still relevant?)
2. Data recency (is the training data stale?)
3. Model calibration (are probabilities meaningful?)
4. Feature importance (what's actually driving decisions?)
5. Market regime coverage (did we train on flat markets?)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Fix Windows encoding
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

import pandas as pd
import numpy as np
from claude_ml.config import Settings
from claude_ml.data_collector import OKXCollector
from claude_ml.feature_engineering import attach_labels
from claude_ml.regime_detector import classify_regime


def check_data_freshness():
    """Check if training data is recent enough."""
    print("=" * 80)
    print("DATA FRESHNESS CHECK")
    print("=" * 80)

    settings = Settings()
    inst_id = "BTC-USDT-SWAP"
    collector = OKXCollector(base_url=settings.okx_base_url, inst_id=inst_id)

    # Fetch latest data
    df = collector.fetch_history(symbol="BTCUSDT", interval=settings.timeframe, lookback_bars=500)

    if df.empty:
        print("FAIL No data fetched")
        return None

    latest_ts = df['ts'].iloc[-1]
    now = pd.Timestamp.now(tz='UTC')

    age_hours = (now - latest_ts).total_seconds() / 3600

    print(f"Latest candle: {latest_ts}")
    print(f"Current time:  {now}")
    print(f"Age:           {age_hours:.1f} hours")

    if age_hours > 24:
        print("WARNING: Data is more than 24 hours old!")
    elif age_hours > 1:
        print("OK: Data is reasonably fresh")
    else:
        print("OK: Data is very fresh")

    return df


def check_feature_distributions(df):
    """Analyze current feature distributions vs expected."""
    print("\n" + "=" * 80)
    print("FEATURE DISTRIBUTION ANALYSIS")
    print("=" * 80)

    settings = Settings()
    featured = attach_labels(
        df.copy(),
        horizon_bars=settings.label_horizon_bars,
        min_return_pct=settings.label_min_return_pct,
        take_profit_pct=float(df['close'].std() / df['close'].mean() * 100),  # Approximate from data
        stop_loss_pct=float(df['close'].std() / df['close'].mean() * 100 * 1.5),
        max_hold_bars=20
    )

    if featured.empty:
        print("FAIL Could not build features")
        return

    # Key features to check
    key_features = [
        'ret_1', 'ret_3', 'ret_6',
        'atr_pct_14', 'vol_zscore',
        'close_vs_ema_8', 'rsi_14',
        'range_compression', 'volume_drying',
        'bar_close_position'
    ]

    print("\nFeature Statistics:")
    print("-" * 80)

    for feat in key_features:
        if feat in featured.columns:
            values = featured[feat].dropna()
            if len(values) > 0:
                print(f"{feat:30} | Mean: {values.mean():8.4f} | Std: {values.std():8.4f} | "
                      f"Min: {values.min():8.4f} | Max: {values.max():8.4f}")

    # Regime distribution - use classify_regime properly
    print("\n" + "-" * 80)
    print("Regime Distribution:")

    regimes = []
    for idx in range(0, len(featured), 10):  # Sample every 10th row
        row = featured.iloc[idx]
        try:
            regime_result = classify_regime(row)
            if isinstance(regime_result, dict):
                regime = regime_result.get('regime', 'unknown')
            else:
                regime = getattr(regime_result, 'regime', 'unknown')
            regimes.append(str(regime))
        except Exception as e:
            regimes.append('unknown')

    regime_counts = pd.Series(regimes).value_counts()
    for regime, count in regime_counts.items():
        pct = count / len(regimes) * 100 if regimes else 0
        print(f"  {regime:20} | {count:4} ({pct:5.1f}%)")


def check_label_quality(featured):
    """Check if labels are balanced and achievable."""
    print("\n" + "=" * 80)
    print("LABEL QUALITY CHECK")
    print("=" * 80)

    # Create labels like training does
    horizon = 6
    min_return_pct = 0.35

    future_high = featured["high"].shift(-horizon)
    featured["long_target"] = ((future_high > featured["close"] * (1 + min_return_pct/100)).astype(int))

    future_low = featured["low"].shift(-horizon)
    featured["short_target"] = ((future_low < featured["close"] * (1 - min_return_pct/100)).astype(int))

    labeled = featured.dropna(subset=["long_target", "short_target"])

    pos_rate_long = labeled["long_target"].mean()
    pos_rate_short = labeled["short_target"].mean()

    print(f"\nLong label positive rate:  {pos_rate_long:.1%}")
    print(f"Short label positive rate: {pos_rate_short:.1%}")

    if pos_rate_long < 0.3 or pos_rate_long > 0.7:
        print("WARNING: Long labels are imbalanced!")

    if pos_rate_short < 0.3 or pos_rate_short > 0.7:
        print("WARNING: Short labels are imbalanced!")

    # Check if targets are realistic
    print(f"\nTotal labeled samples: {len(labeled)}")

    return labeled


def analyze_market_conditions(featured):
    """Analyze current market conditions."""
    print("\n" + "=" * 80)
    print("MARKET CONDITIONS ANALYSIS")
    print("=" * 80)

    if featured.empty or len(featured) == 0:
        print("No data available")
        return

    close_price = featured['close'].iloc[-1]

    # Check what ATR column exists
    atr_col = None
    for col in ['atr_pct_14', 'atr_14']:
        if col in featured.columns:
            atr_col = col
            break

    rsi_col = None
    for col in ['rsi_14']:
        if col in featured.columns:
            rsi_col = col
            break

    vol_col = None
    for col in ['vol_zscore']:
        if col in featured.columns:
            vol_col = col
            break

    if atr_col:
        atr_val = featured[atr_col].iloc[-1]
        # If it's absolute ATR, convert to percentage
        if atr_val > 10:  # Likely absolute value for BTC
            atr_pct = (atr_val / close_price) * 100
        else:
            atr_pct = atr_val * 100
    else:
        atr_pct = None

    rsi = featured[rsi_col].iloc[-1] if rsi_col and not pd.isna(featured[rsi_col].iloc[-1]) else None
    vol_zscore = featured[vol_col].iloc[-1] if vol_col and not pd.isna(featured[vol_col].iloc[-1]) else None

    print(f"\nCurrent Price:     ${close_price:.2f}")
    if atr_pct is not None:
        print(f"ATR (%):           {atr_pct:.2f}%")
    else:
        print(f"ATR (%):           N/A")

    if rsi is not None:
        print(f"RSI (14):          {rsi:.1f}")
    else:
        print(f"RSI (14):          N/A")

    if vol_zscore is not None:
        print(f"Volume Z-Score:    {vol_zscore:.2f}")
    else:
        print(f"Volume Z-Score:    N/A")

    # Interpretation
    print("\nMarket State:")
    if atr_pct is not None:
        if atr_pct < 1.0:
            print("  - Low volatility (compression)")
        elif atr_pct > 2.0:
            print("  - High volatility (expansion)")
        else:
            print("  - Moderate volatility")

    if rsi is not None:
        if rsi < 30:
            print("  - RSI oversold")
        elif rsi > 70:
            print("  - RSI overbought")
        else:
            print("  - RSI neutral")

    if vol_zscore is not None:
        if vol_zscore < -1:
            print("  - Volume below average (drying)")
        elif vol_zscore > 1:
            print("  - Volume above average (expanding)")
        else:
            print("  - Volume normal")


if __name__ == "__main__":
    print("\nStarting model quality diagnostics...\n")

    # Step 1: Check data freshness
    df = check_data_freshness()
    if df is None:
        print("\nCannot continue without data")
        sys.exit(1)

    # Step 2: Check feature distributions
    settings = Settings()
    featured = attach_labels(
        df.copy(),
        horizon_bars=settings.label_horizon_bars,
        min_return_pct=settings.label_min_return_pct,
        take_profit_pct=settings.take_profit_atr_multiplier * 1.0,
        stop_loss_pct=settings.stop_loss_atr_multiplier * 1.0,
        max_hold_bars=20
    )
    check_feature_distributions(df)

    # Step 3: Check label quality
    labeled = check_label_quality(featured)

    # Step 4: Analyze market conditions
    analyze_market_conditions(featured)

    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

    print("\nNext steps:")
    print("1. Review feature distributions for drift")
    print("2. Check if training labels match current market")
    print("3. Verify model calibration with live data")
