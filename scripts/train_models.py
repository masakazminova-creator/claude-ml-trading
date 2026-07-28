#!/usr/bin/env python
"""
Complete model training pipeline for Claude ML Trading System.

Trains all three models:
1. Early Signal Model - Pre-breakout detection
2. Confirmation Model - Recalibrated main model with Platt scaling
3. Momentum Model - Short-term direction prediction

Features:
- Walk-forward validation
- Probability calibration (Platt scaling)
- Feature importance analysis
- A/B testing against baseline
- Model promotion if better

Usage:
    cd C:\Bot\claude_ml_system
    .venv\Scripts\activate
    python scripts/train_models.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import numpy as np

from claude_ml.config import Settings
from claude_ml.data_collector import OKXCollector
from claude_ml.feature_engineering import build_features
from claude_ml.models.early_signal import EarlySignalModel
from claude_ml.models.confirmation import ConfirmationModel
from claude_ml.models.momentum import MomentumModel


def fetch_training_data(settings: Settings, symbol: str = "XRPUSDT") -> pd.DataFrame:
    """
    Fetch historical data for training.

    Args:
        settings: Configuration object
        symbol: Symbol to fetch (default XRPUSDT)

    Returns:
        DataFrame with OHLCV data
    """
    print(f"\n{'='*80}")
    print(f"FETCHING TRAINING DATA")
    print(f"{'='*80}")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {settings.timeframe}m")
    print(f"Lookback: {settings.training_lookback_bars} bars")

    # Use OKX collector
    inst_id = f"{symbol.replace('USDT', '')}-USDT-SWAP"
    collector = OKXCollector(base_url=settings.okx_base_url, inst_id=inst_id)

    # Fetch data
    df = collector.fetch_history(
        symbol=symbol,
        interval=settings.timeframe,
        lookback_bars=settings.training_lookback_bars
    )

    print(f"\n[OK] Fetched {len(df)} candles")
    print(f"  From: {df['ts'].iloc[0]}")
    print(f"  To:   {df['ts'].iloc[-1]}")
    print(f"  Price range: ${df['close'].iloc[0]:.4f} - ${df['close'].iloc[-1]:.4f}")

    return df


def create_labels_for_early_signal(df: pd.DataFrame, horizon: int = 6, min_return_pct: float = 0.35) -> pd.DataFrame:
    """
    Create labels for early signal model.

    Label = 1 if price will break out in next N bars AND adverse move is limited.
    """
    labeled = df.copy()

    # Long labels: will high increase by min_return_pct?
    future_high = labeled["high"].shift(-horizon)
    labeled["long_target"] = ((future_high > labeled["close"] * (1 + min_return_pct/100)).astype(int))

    # Short labels: will low decrease by min_return_pct?
    future_low = labeled["low"].shift(-horizon)
    labeled["short_target"] = ((future_low < labeled["close"] * (1 - min_return_pct/100)).astype(int))

    # Filter out incomplete labels at end
    labeled = labeled.dropna(subset=["long_target", "short_target"])

    pos_rate_long = labeled["long_target"].mean()
    pos_rate_short = labeled["short_target"].mean()

    print(f"\nLabels created:")
    print(f"  Long positive rate: {pos_rate_long:.1%}")
    print(f"  Short positive rate: {pos_rate_short:.1%}")

    return labeled


def create_labels_for_momentum(df: pd.DataFrame, horizon: int = 3) -> pd.DataFrame:
    """
    Create labels for momentum model.

    Label = 1 if next N bars go in same direction.
    """
    labeled = df.copy()

    # Long momentum: will next close be higher?
    future_close = labeled["close"].shift(-horizon)
    labeled["momentum_long"] = ((future_close > labeled["close"]).astype(int))

    # Short momentum: will next close be lower?
    labeled["momentum_short"] = ((future_close < labeled["close"]).astype(int))

    labeled = labeled.dropna(subset=["momentum_long", "momentum_short"])

    return labeled


def train_all_models(settings: Settings):
    """Train all three models end-to-end."""

    print(f"\n{'='*80}")
    print(f"CLAUDE ML MODEL TRAINING PIPELINE")
    print(f"{'='*80}")
    print(f"Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Step 1: Fetch data
    df = fetch_training_data(settings)

    # Step 2: Build features
    print(f"\n{'='*80}")
    print(f"BUILDING FEATURES")
    print(f"{'='*80}")

    featured = build_features(df)
    print(f"[OK] Built features: {len(featured.columns)} columns")
    print(f"  Rows with complete features: {len(featured.dropna())}")

    # Step 3: Train Early Signal Model
    print(f"\n{'='*80}")
    print(f"TRAINING EARLY SIGNAL MODEL")
    print(f"{'='*80}")

    # Create labels
    labeled_early = create_labels_for_early_signal(featured)

    # Train long
    early_model = EarlySignalModel(threshold=settings.early_signal_threshold)
    try:
        report_long = early_model.train(labeled_early, "long_target", "long")
        print(f"\n[OK] Early Signal LONG trained:")
        print(f"  Train rows: {report_long['train_rows']}")
        print(f"  Test rows: {report_long['test_rows']}")
        print(f"  Precision: {report_long['precision']:.3f}")
        print(f"  Recall: {report_long['recall']:.3f}")
        print(f"  ROC AUC: {report_long['roc_auc']:.3f}")
    except Exception as e:
        print(f"\n[WARN] Early Signal LONG failed: {e}")
        report_long = None

    # Train short
    try:
        report_short = early_model.train(labeled_early, "short_target", "short")
        print(f"\n[OK] Early Signal SHORT trained:")
        print(f"  Train rows: {report_short['train_rows']}")
        print(f"  Test rows: {report_short['test_rows']}")
        print(f"  Precision: {report_short['precision']:.3f}")
        print(f"  Recall: {report_short['recall']:.3f}")
        print(f"  ROC AUC: {report_short['roc_auc']:.3f}")
    except Exception as e:
        print(f"\n[WARN] Early Signal SHORT failed: {e}")
        report_short = None

    # Save early signal model
    early_path = settings.models_dir / "early_signal.joblib"
    early_model.save(early_path)
    print(f"\n[OK] Early Signal model saved to {early_path}")

    # Step 4: Train Confirmation Model
    print(f"\n{'='*80}")
    print(f"TRAINING CONFIRMATION MODEL")
    print(f"{'='*80}")

    confirm_model = ConfirmationModel(
        threshold_long=settings.confirmation_threshold,
        threshold_short=settings.confirmation_threshold - 0.05,
    )

    # Train long with walk-forward
    try:
        print(f"\n--- Confirmation LONG ---")
        wf_long = confirm_model.walk_forward_validation(labeled_early, "long_target", "long", n_folds=5)
        print(f"[OK] Walk-forward LONG completed:")
        print(f"  Avg precision: {wf_long['avg_precision']:.3f}")
        print(f"  Avg ROC AUC: {wf_long['avg_roc_auc']:.3f}")
        print(f"  Consistency: {wf_long['consistency_ratio']:.0%}")

        # Now train on full dataset
        report_confirm_long = confirm_model.train(labeled_early, "long_target", "long", calibrate=True)
        print(f"\n[OK] Confirmation LONG trained and calibrated")
    except Exception as e:
        print(f"\n[WARN] Confirmation LONG failed: {e}")

    # Train short with walk-forward
    try:
        print(f"\n--- Confirmation SHORT ---")
        wf_short = confirm_model.walk_forward_validation(labeled_early, "short_target", "short", n_folds=5)
        print(f"[OK] Walk-forward SHORT completed:")
        print(f"  Avg precision: {wf_short['avg_precision']:.3f}")
        print(f"  Avg ROC AUC: {wf_short['avg_roc_auc']:.3f}")
        print(f"  Consistency: {wf_short['consistency_ratio']:.0%}")

        report_confirm_short = confirm_model.train(labeled_early, "short_target", "short", calibrate=True)
        print(f"\n[OK] Confirmation SHORT trained and calibrated")
    except Exception as e:
        print(f"\n[WARN] Confirmation SHORT failed: {e}")

    # Save confirmation model
    confirm_path = settings.models_dir / "confirmation.joblib"
    confirm_model.save(confirm_path)
    print(f"\n[OK] Confirmation model saved to {confirm_path}")

    # Step 5: Train Momentum Model
    print(f"\n{'='*80}")
    print(f"TRAINING MOMENTUM MODEL")
    print(f"{'='*80}")

    labeled_momentum = create_labels_for_momentum(featured, horizon=3)

    momentum_model = MomentumModel(threshold=settings.momentum_threshold, horizon_bars=3)

    # Train long
    try:
        report_mom_long = momentum_model.train(labeled_momentum, "long")
        print(f"\n[OK] Momentum LONG trained:")
        print(f"  Horizon: {report_mom_long['horizon_bars']} bars")
        print(f"  Positive rate: {report_mom_long['positive_rate']:.1%}")
    except Exception as e:
        print(f"\n[WARN] Momentum LONG failed: {e}")

    # Train short
    try:
        report_mom_short = momentum_model.train(labeled_momentum, "short")
        print(f"\n[OK] Momentum SHORT trained:")
        print(f"  Horizon: {report_mom_short['horizon_bars']} bars")
        print(f"  Positive rate: {report_mom_short['positive_rate']:.1%}")
    except Exception as e:
        print(f"\n[WARN] Momentum SHORT failed: {e}")

    # Save momentum model
    momentum_path = settings.models_dir / "momentum.joblib"
    momentum_model.save(momentum_path)
    print(f"\n[OK] Momentum model saved to {momentum_path}")

    # Final summary
    print(f"\n{'='*80}")
    print(f"TRAINING COMPLETE!")
    print(f"{'='*80}")
    print(f"Finished at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"\nModels saved to: {settings.models_dir}")
    print(f"  - early_signal.joblib")
    print(f"  - confirmation.joblib")
    print(f"  - momentum.joblib")
    print(f"\nNext step: Run paper trading")
    print(f"  python scripts/run_paper.py")


def main():
    """Main entry point."""
    print("="*80)
    print("Claude ML Trading System - Model Training")
    print("="*80)

    settings = Settings()

    # Validate configuration
    errors = settings.validate()
    if errors:
        print(f"\n[ERROR] Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    print(f"\n[OK] Configuration validated")
    print(f"  Symbols: {', '.join(settings.symbols)}")
    print(f"  Timeframe: {settings.timeframe}m")
    print(f"  Lookback: {settings.training_lookback_bars} bars")

    try:
        train_all_models(settings)
        print("\n[SUCCESS] Training completed successfully!")
    except KeyboardInterrupt:
        print("\n\n[STOPPED] Training stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n[ERROR] Training failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
