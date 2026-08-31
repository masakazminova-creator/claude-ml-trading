#!/usr/bin/env python
"""
Quick diagnostic script to check what the ensemble is seeing.
Shows current market conditions, model scores, and why decisions are being skipped.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Fix Windows encoding
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

import pandas as pd
from claude_ml.config import Settings
from claude_ml.data_collector import OKXCollector
from claude_ml.feature_engineering import attach_labels, build_features
from claude_ml.regime_detector import classify_regime
from claude_ml.ensemble import EnsembleEngine
from claude_ml.models.early_signal import EarlySignalModel
from claude_ml.models.confirmation import ConfirmationModel
from claude_ml.models.momentum import MomentumModel


def check_signals():
    """Check current signal generation."""
    settings = Settings()

    print("=" * 80)
    print("CURRENT SIGNAL DIAGNOSTIC")
    print("=" * 80)

    # Load models
    try:
        model_dir = Path(__file__).parent.parent / "models"
        early_model = EarlySignalModel.load(model_dir / "early_signal.joblib")
        confirm_model = ConfirmationModel.load(model_dir / "confirmation.joblib")
        momentum_model = MomentumModel.load(model_dir / "momentum.joblib")
        print("OK Models loaded successfully")
    except Exception as e:
        print(f"FAIL Failed to load models: {e}")
        return

    # Get recent data
    collector = OKXCollector()
    df = collector.fetch_ohlcv("BTCUSDT", settings.timeframe, limit=300)

    if df.empty or len(df) < 200:
        print(f"✗ Not enough data (got {len(df)} bars)")
        return

    print(f"OK Fetched {len(df)} candles")

    # Build features — build_features (with labels attached for downstream
    # inspection), NOT bare attach_labels (attach_labels requires
    # horizon/TP/SL/max_hold args; calling it with none raised TypeError,
    # so this diagnostic script could never run).
    featured = build_features(df.copy())
    labeled = attach_labels(featured, horizon_bars=6, min_return_pct=0.15,
                            take_profit_pct=1.0, stop_loss_pct=1.0, max_hold_bars=6)
    latest_row = labeled.iloc[-1]

    # Get regime
    regime_result = classify_regime(latest_row)
    regime_name = regime_result.get('regime', 'flat') if isinstance(regime_result, dict) else "flat"

    print(f"\n--- MARKET STATE ---")
    print(f"Regime: {regime_name}")
    print(f"Close Price: ${latest_row.get('close', 0):.2f}")

    # Run models
    print(f"\n--- MODEL SCORES ---")
    early_result = early_model.predict(latest_row, side="long", regime=regime_name)
    confirm_long = confirm_model.predict(latest_row, side="long", regime=regime_name)
    confirm_short = confirm_model.predict(latest_row, side="short", regime=regime_name)
    momentum_long = momentum_model.predict(latest_row, side="long")
    momentum_short = momentum_model.predict(latest_row, side="short")

    print(f"Early Signal: {early_result.score:.2f} (threshold: {settings.early_signal_threshold})")
    print(f"Confirmation Long: {confirm_long.score:.2f} (threshold: {settings.confirmation_threshold})")
    print(f"Confirmation Short: {confirm_short.score:.2f}")
    print(f"Momentum Long: {momentum_long.score:.2f} (threshold: {settings.momentum_threshold})")
    print(f"Momentum Short: {momentum_short.score:.2f}")

    # Check agreements
    print(f"\n--- AGREEMENTS ---")
    agreements = []
    if early_result and early_result.score >= 62:
        agreements.append("early")
        print("OK Early signal agrees")
    else:
        print(f"FAIL Early signal too low ({early_result.score:.2f} < 62)")

    if confirm_long and confirm_long.is_confirmed:
        agreements.append("confirm")
        print("OK Confirmation agrees")
    else:
        print(f"FAIL Confirmation not confirmed ({confirm_long.score:.2f} < {settings.confirmation_threshold})")

    if momentum_long and momentum_long.direction == "with_momentum":
        agreements.append("momentum")
        print("OK Momentum agrees")
    else:
        print(f"FAIL Momentum disagrees")

    print(f"\nTotal agreements: {len(agreements)}/3")

    # Decision
    print(f"\n--- DECISION ---")
    if len(agreements) == 3:
        print("ENTER_FULL - All models agree")
    elif len(agreements) == 2:
        print("ENTER_REDUCED - 2 models agree")
    elif len(agreements) == 1:
        if "early" in agreements:
            print("WAIT - Only early signal, waiting for confirmation")
        else:
            print("SKIP - Single model without early signal")
    else:
        print("SKIP - No models agree")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    check_signals()
