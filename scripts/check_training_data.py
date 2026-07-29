#!/usr/bin/env python
"""Simple script to check training data quality."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from claude_ml.config import Settings
from claude_ml.data_collector import OKXCollector
from claude_ml.feature_engineering import build_features

print("=" * 80)
print("TRAINING DATA CHECK")
print("=" * 80)

settings = Settings()
inst_id = "BTC-USDT-SWAP"
collector = OKXCollector(base_url=settings.okx_base_url, inst_id=inst_id)

# Fetch more data
print("\nFetching 500 candles...")
df = collector.fetch_history(symbol="BTCUSDT", interval=settings.timeframe, lookback_bars=500)

print(f"Got {len(df)} rows")
print(f"Date range: {df['ts'].iloc[0]} to {df['ts'].iloc[-1]}")
print(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

# Build features
print("\nBuilding features...")
featured = build_features(df)

print(f"Built {len(featured.columns)} features")
print(f"Complete rows (no NaN): {len(featured.dropna())}")

# Check key features
if len(featured) > 0 and not featured.empty:
    print("\nKey feature values (last row):")
    check_cols = ['atr_14', 'rsi_14', 'vol_zscore', 'ema_8_vs_21']
    for col in check_cols:
        if col in featured.columns:
            val = featured[col].iloc[-1]
            print(f"  {col:20} = {val:.4f}")

# Show sample
print("\nFirst 3 columns:")
print(featured.iloc[-1][featured.columns[:10]])
