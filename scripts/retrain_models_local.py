#!/usr/bin/env python
"""
Retrain all models locally with current market data and adaptive labels.

This script:
1. Fetches fresh data from OKX (500 bars)
2. Builds features
3. Creates adaptive labels based on current volatility
4. Trains all 3 models
5. Saves models to local directory
6. Shows training metrics

Usage:
    cd C:\Bot\claude_ml_system
    source .venv/Scripts/activate
    python scripts/retrain_models_local.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

import pandas as pd
from claude_ml.config import Settings
from claude_ml.data_collector import OKXCollector
from claude_ml.feature_engineering import build_features
from claude_ml.adaptive_labels import create_balanced_labels
from claude_ml.models.early_signal import EarlySignalModel
from claude_ml.models.confirmation import ConfirmationModel
from claude_ml.models.momentum import MomentumModel


def retrain():
    """Retrain all models with adaptive labels."""
    settings = Settings()

    print("=" * 80)
    print("RETRAINING MODELS WITH ADAPTIVE LABELS")
    print("=" * 80)

    # Step 1: Fetch fresh data
    print("\n[1/5] Fetching fresh data from OKX...")
    inst_id = "BTC-USDT-SWAP"
    collector = OKXCollector(base_url=settings.okx_base_url, inst_id=inst_id)
    df = collector.fetch_history(
        symbol="BTCUSDT",
        interval=settings.timeframe,
        lookback_bars=2000  # Need more data for training (2000 bars ~ 21 days)
    )

    print(f"  Fetched {len(df)} candles")
    print(f"  Date range: {df['ts'].iloc[0]} to {df['ts'].iloc[-1]}")
    print(f"  Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

    # Step 2: Build features
    print("\n[2/5] Building features...")
    featured = build_features(df)
    print(f"  Built {len(featured.columns)} features")
    print(f"  Complete rows: {len(featured.dropna())}")

    # Step 3: Create adaptive labels
    print("\n[3/5] Creating adaptive labels...")
    labeled_early = create_balanced_labels(
        featured,
        horizon_bars=6,
        base_min_return_pct=float(settings.label_min_return_pct),
        take_profit_mult=float(settings.take_profit_atr_multiplier),
        stop_loss_mult=float(settings.stop_loss_atr_multiplier),
        max_hold_bars=6,
    )

    labeled_momentum = create_balanced_labels(
        featured,
        horizon_bars=3,
        base_min_return_pct=0.20,
        take_profit_mult=float(settings.take_profit_atr_multiplier) * 0.5,
        stop_loss_mult=float(settings.stop_loss_atr_multiplier) * 0.5,
        max_hold_bars=3,
    )

    # Check label balance
    pos_rate_long = labeled_early['long_target'].dropna().mean() * 100
    pos_rate_short = labeled_early['short_target'].dropna().mean() * 100
    print(f"\n  Label balance check:")
    status_long = "OK" if 30 <= pos_rate_long <= 70 else "WARN"
    status_short = "OK" if 30 <= pos_rate_short <= 70 else "WARN"
    print(f"    Long positive rate: {pos_rate_long:.1f}% [{status_long}]")
    print(f"    Short positive rate: {pos_rate_short:.1f}% [{status_short}]")

    # Step 4: Train models
    print("\n[4/5] Training models...")

    # Early Signal Model
    print("\n  --- Early Signal Model ---")
    early_model = EarlySignalModel(threshold=settings.early_signal_threshold)
    try:
        report_long = early_model.train(labeled_early, "long_target", "long")
        print(f"    OK LONG trained:")
        print(f"      Precision: {report_long['precision']:.3f}")
        print(f"      Recall: {report_long['recall']:.3f}")
        print(f"      ROC AUC: {report_long['roc_auc']:.3f}")
        print(f"      Positive rate: {report_long['positive_rate_test']:.1%}")
    except Exception as e:
        print(f"    FAIL LONG failed: {e}")
        report_long = None

    try:
        report_short = early_model.train(labeled_early, "short_target", "short")
        print(f"    OK SHORT trained:")
        print(f"      Precision: {report_short['precision']:.3f}")
        print(f"      Recall: {report_short['recall']:.3f}")
        print(f"      ROC AUC: {report_short['roc_auc']:.3f}")
        print(f"      Positive rate: {report_short['positive_rate_test']:.1%}")
    except Exception as e:
        print(f"    FAIL SHORT failed: {e}")
        report_short = None

    # Confirmation Model
    print("\n  --- Confirmation Model ---")
    confirm_model = ConfirmationModel(
        threshold_long=settings.confirmation_threshold,
        threshold_short=settings.confirmation_threshold - 0.05,
    )

    try:
        print("    Training LONG with Platt scaling...")
        report_confirm_long = confirm_model.train(labeled_early, "long_target", "long", calibrate=True)
        print(f"    OK LONG calibrated:")
        print(f"      Precision: {report_confirm_long['precision']:.3f}")
        print(f"      ROC AUC: {report_confirm_long['roc_auc']:.3f}")
    except Exception as e:
        print(f"    FAIL LONG failed: {e}")
        report_confirm_long = None

    try:
        print("    Training SHORT with Platt scaling...")
        report_confirm_short = confirm_model.train(labeled_early, "short_target", "short", calibrate=True)
        print(f"    OK SHORT calibrated:")
        print(f"      Precision: {report_confirm_short['precision']:.3f}")
        print(f"      ROC AUC: {report_confirm_short['roc_auc']:.3f}")
    except Exception as e:
        print(f"    FAIL SHORT failed: {e}")
        report_confirm_short = None

    # Momentum Model
    print("\n  --- Momentum Model ---")
    momentum_model = MomentumModel(threshold=settings.momentum_threshold, horizon_bars=3)

    try:
        report_mom_long = momentum_model.train(labeled_momentum, "long")
        print(f"    OK LONG trained:")
        print(f"      Horizon: {report_mom_long['horizon_bars']} bars")
        print(f"      Positive rate: {report_mom_long['positive_rate']:.1%}")
    except Exception as e:
        print(f"    FAIL LONG failed: {e}")
        report_mom_long = None

    try:
        report_mom_short = momentum_model.train(labeled_momentum, "short")
        print(f"    OK SHORT trained:")
        print(f"      Horizon: {report_mom_short['horizon_bars']} bars")
        print(f"      Positive rate: {report_mom_short['positive_rate']:.1%}")
    except Exception as e:
        print(f"    FAIL SHORT failed: {e}")
        report_mom_short = None

    # Step 5: Save models
    print("\n[5/5] Saving models...")
    model_dir = Path(__file__).parent.parent / "models"
    model_dir.mkdir(exist_ok=True)

    early_path = model_dir / "early_signal.joblib"
    early_model.save(early_path)
    print(f"  OK Early Signal saved to {early_path}")

    confirm_path = model_dir / "confirmation.joblib"
    confirm_model.save(confirm_path)
    print(f"  OK Confirmation saved to {confirm_path}")

    momentum_path = model_dir / "momentum.joblib"
    momentum_model.save(momentum_path)
    print(f"  OK Momentum saved to {momentum_path}")

    print("\n" + "=" * 80)
    print("TRAINING COMPLETE!")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Test models locally")
    print("2. Commit and push to deploy to server")
    print("   git add models/*.joblib")
    print('   git commit -m "Retrain models with adaptive labels for flat market"')
    print("   git push")


if __name__ == "__main__":
    retrain()
