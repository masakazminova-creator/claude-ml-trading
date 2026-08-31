"""
Confirmation Model - Recalibrated main model with proper probability calibration.

This is the enhanced version of the existing HistGradientBoosting model, but with:
- Platt scaling for calibrated probabilities (fixes 0.049 correlation issue)
- Walk-forward validation to prevent overfitting
- Feature importance analysis
- Regime-specific performance tracking
- Higher threshold (0.75-0.80) for validated entries

Purpose: Validate early signals with higher confidence before full position entry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    classification_report,
    precision_score,
    recall_score,
    roc_auc_score,
    brier_score_loss,
)


# Use same features as original system for compatibility
CONFIRMATION_FEATURES = [
    "ret_1",
    "ret_2",
    "ret_3",
    "ret_6",
    "ret_12",
    "range_pct",
    "body_pct",
    "atr_pct_14",
    "realized_vol_12",
    "vol_zscore",
    "turnover_zscore",
    "close_vs_ema_8",
    "close_vs_ema_21",
    "ema_8_vs_21",
    "ema_slope_8",
    "rsi_14",
    "dist_from_rolling_high_20",
    "dist_from_rolling_low_20",
    "recent_range_progress_6",
    "impulse_1_vs_3",
    "range_expansion_vs_atr",
    "ema_gap_change_3",
    "bar_close_position",
    "close_vs_tf5_close",
    "close_vs_tf60_close",
    "tf60_ret_3",
    "tf60_rsi_14",
    "hour_sin",
    "hour_cos",
    "dow",
    "session_asia",
    "session_eu",
    "session_us",
    "ob_spread_bps",
    "ob_imbalance_top_10",
    "ob_bid_depth_ratio",
    "trade_buy_ratio",
    "trade_flow_imbalance",
    "trade_large_ratio",
    "trade_count_norm",
]


@dataclass(slots=True)
class ConfirmationResult:
    """Result from confirmation model prediction."""
    side: str
    probability: float  # Calibrated probability
    raw_probability: float  # Before calibration
    score: float  # 0-100
    confidence: float  # Model confidence
    is_confirmed: bool  # Above threshold?
    feature_quality: str  # 'good', 'fair', 'poor'
    top_features: List[Dict[str, float]]  # Top 5 contributing features


class ConfirmationModel:
    """Recalibrated main model for signal confirmation."""

    def __init__(
        self,
        threshold_long: float = 0.75,
        threshold_short: float = 0.70,
        max_depth: int = 5,
        learning_rate: float = 0.045,
        max_iter: int = 300,
        min_samples_leaf: int = 20,
    ):
        self.threshold_long = threshold_long
        self.threshold_short = threshold_short

        # Model parameters
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.min_samples_leaf = min_samples_leaf

        # Models
        self.long_model: Optional[HistGradientBoostingClassifier] = None
        self.short_model: Optional[HistGradientBoostingClassifier] = None
        self.long_calibrated: Optional[CalibratedClassifierCV] = None
        self.short_calibrated: Optional[CalibratedClassifierCV] = None

        # Metadata
        self.feature_importance: Dict[str, float] = {}
        self.calibration_metrics: Dict[str, Any] = {}
        self.walk_forward_results: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}

    def create_model(self) -> HistGradientBoostingClassifier:
        """Create base classifier with optimized parameters."""
        return HistGradientBoostingClassifier(
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            max_iter=self.max_iter,
            min_samples_leaf=self.min_samples_leaf,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=20,
        )

    def train(
        self,
        df: pd.DataFrame,
        target_column: str,
        side: str,
        train_split: float = 0.8,
        calibrate: bool = True,
    ) -> Dict[str, Any]:
        """
        Train confirmation model with optional calibration.

        Args:
            df: DataFrame with features and labels
            target_column: 'long_target' or 'short_target'
            side: 'long' or 'short'
            train_split: Train/test split ratio
            calibrate: Whether to apply Platt scaling

        Returns:
            Training report with metrics
        """
        # Filter available features
        available_features = [f for f in CONFIRMATION_FEATURES if f in df.columns]
        ready = df.dropna(subset=available_features + [target_column]).reset_index(drop=True)

        if len(ready) < 500:
            raise RuntimeError(f"Not enough data for {side} confirmation model (need 500+, got {len(ready)})")
        if ready[target_column].nunique() < 2:
            raise RuntimeError(
                f"Single-class target '{target_column}' for {side} confirmation model "
                f"(values: {ready[target_column].unique()[:5].tolist()}) — cannot train classifier"
            )

        # Split
        split_idx = max(500, int(len(ready) * train_split))
        split_idx = min(split_idx, len(ready) - 200)
        train_df = ready.iloc[:split_idx].copy()
        test_df = ready.iloc[split_idx:].copy()

        # Train base model
        print(f"[{side}] Training base model...")
        model = self.create_model()
        model.fit(train_df[available_features], train_df[target_column].astype(int))

        # Evaluate base model
        base_proba = model.predict_proba(test_df[available_features])[:, 1]
        base_pred = (base_proba >= 0.5).astype(int)

        base_report = {
            "precision": float(precision_score(test_df[target_column].astype(int), base_pred, zero_division=0)),
            "recall": float(recall_score(test_df[target_column].astype(int), base_pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(test_df[target_column].astype(int), base_proba)) if test_df[target_column].nunique() == 2 else 0.0,
            "brier_score": float(brier_score_loss(test_df[target_column].astype(int), base_proba)),
        }

        # Calibrate if requested
        calibrated_report = None
        calibrated_model = None

        if calibrate:
            print(f"[{side}] Applying Platt scaling for calibration...")
            calibrated = CalibratedClassifierCV(model, cv=5, method='sigmoid')
            calibrated.fit(test_df[available_features], test_df[target_column].astype(int))

            cal_proba = calibrated.predict_proba(test_df[available_features])[:, 1]
            cal_pred = (cal_proba >= (self.threshold_long if side == "long" else self.threshold_short)).astype(int)

            # Check calibration improvement
            cal_brier = float(brier_score_loss(test_df[target_column].astype(int), cal_proba))

            calibrated_report = {
                "precision": float(precision_score(test_df[target_column].astype(int), cal_pred, zero_division=0)),
                "recall": float(recall_score(test_df[target_column].astype(int), cal_pred, zero_division=0)),
                "roc_auc": float(roc_auc_score(test_df[target_column].astype(int), cal_proba)) if test_df[target_column].nunique() == 2 else 0.0,
                "brier_score": cal_brier,
                "brier_improvement": float(base_report["brier_score"] - cal_brier),
            }
            calibrated_model = calibrated

            print(f"[{side}] Calibration Brier improvement: {calibrated_report['brier_improvement']:.4f}")

        # Feature importance via permutation
        print(f"[{side}] Computing feature importance...")
        importance = permutation_importance(
            model,
            test_df[available_features],
            test_df[target_column].astype(int),
            n_repeats=5,
            random_state=42,
            scoring="precision",
        )

        feature_imp = {
            name: float(score)
            for name, score in zip(available_features, importance.importances_mean, strict=False)
        }

        # Store models
        if side == "long":
            self.long_model = model
            self.long_calibrated = calibrated_model
        else:
            self.short_model = model
            self.short_calibrated = calibrated_model

        self.feature_importance = feature_imp
        self.metadata = {
            "side": side,
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "features_used": len(available_features),
            "threshold": self.threshold_long if side == "long" else self.threshold_short,
            "base_report": base_report,
            "calibrated_report": calibrated_report,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }

        return self.metadata

    def predict(
        self,
        row: pd.Series,
        side: str,
        regime: Optional[str] = None,
    ) -> Optional[ConfirmationResult]:
        """
        Predict with calibrated probabilities.

        Args:
            row: Single row with features
            side: 'long' or 'short'
            regime: Current market regime (for diagnostics)

        Returns:
            ConfirmationResult or None if model not trained
        """
        # Get appropriate model
        calibrated = self.long_calibrated if side == "long" else self.short_calibrated
        base_model = self.long_model if side == "long" else self.short_model

        if calibrated is None or base_model is None:
            return None

        # Extract features
        available_features = [f for f in CONFIRMATION_FEATURES if f in row.index]
        features_df = row[available_features].to_frame().T

        # Get both raw and calibrated probabilities
        raw_proba = float(base_model.predict_proba(features_df)[0, 1])
        cal_proba = float(calibrated.predict_proba(features_df)[0, 1])

        threshold = self.threshold_long if side == "long" else self.threshold_short
        is_confirmed = cal_proba >= threshold

        # Calculate confidence (how far from decision boundary)
        confidence = abs(cal_proba - 0.5) * 2

        # Score (0-100)
        score = cal_proba * 100

        # Feature quality based on how many top features are active
        top_feats = self.get_top_features(n=5)
        active_top = [f for f in top_feats if abs(row.get(f["feature"], 0)) > 0.1]
        feature_quality = "good" if len(active_top) >= 3 else ("fair" if len(active_top) >= 2 else "poor")

        return ConfirmationResult(
            side=side,
            probability=round(cal_proba, 4),
            raw_probability=round(raw_proba, 4),
            score=round(score, 2),
            confidence=round(confidence, 4),
            is_confirmed=is_confirmed,
            feature_quality=feature_quality,
            top_features=top_feats[:5],
        )

    def walk_forward_validation(
        self,
        df: pd.DataFrame,
        target_column: str,
        side: str,
        n_folds: int = 5,
    ) -> Dict[str, Any]:
        """
        Walk-forward validation to assess robustness.

        Args:
            df: DataFrame with features and labels
            target_column: 'long_target' or 'short_target'
            side: 'long' or 'short'
            n_folds: Number of folds

        Returns:
            Walk-forward results
        """
        available_features = [f for f in CONFIRMATION_FEATURES if f in df.columns]
        ready = df.dropna(subset=available_features + [target_column]).reset_index(drop=True)

        fold_size = len(ready) // (n_folds + 1)
        if fold_size < 200:
            raise RuntimeError(f"Fold size too small: {fold_size}")

        fold_results = []
        threshold = self.threshold_long if side == "long" else self.threshold_short

        for fold_idx in range(n_folds):
            # Create expanding window
            train_end = (fold_idx + 1) * fold_size
            test_start = train_end
            test_end = min((fold_idx + 2) * fold_size, len(ready))

            if test_end > len(ready):
                break

            train_df = ready.iloc[:train_end].copy()
            test_df = ready.iloc[test_start:test_end].copy()

            # Train
            model = self.create_model()
            model.fit(train_df[available_features], train_df[target_column].astype(int))

            # Calibrate
            calibrated = CalibratedClassifierCV(model, cv=5, method='sigmoid')
            calibrated.fit(test_df[available_features], test_df[target_column].astype(int))

            # Evaluate
            proba = calibrated.predict_proba(test_df[available_features])[:, 1]
            pred = (proba >= threshold).astype(int)

            fold_result = {
                "fold": fold_idx + 1,
                "train_size": len(train_df),
                "test_size": len(test_df),
                "precision": float(precision_score(test_df[target_column].astype(int), pred, zero_division=0)),
                "recall": float(recall_score(test_df[target_column].astype(int), pred, zero_division=0)),
                "roc_auc": float(roc_auc_score(test_df[target_column].astype(int), proba)) if test_df[target_column].nunique() == 2 else 0.0,
                "win_rate": float(pred.mean()),
                "positive_rate": float(test_df[target_column].astype(int).mean()),
            }
            fold_results.append(fold_result)

        self.walk_forward_results = fold_results

        # Aggregate
        avg_precision = np.mean([r["precision"] for r in fold_results])
        avg_recall = np.mean([r["recall"] for r in fold_results])
        avg_roc_auc = np.mean([r["roc_auc"] for r in fold_results])
        consistent_folds = sum(1 for r in fold_results if r["precision"] > 0.5)

        summary = {
            "n_folds": n_folds,
            "avg_precision": round(float(avg_precision), 4),
            "avg_recall": round(float(avg_recall), 4),
            "avg_roc_auc": round(float(avg_roc_auc), 4),
            "consistent_folds": consistent_folds,
            "consistency_ratio": round(consistent_folds / n_folds, 2),
            "fold_results": fold_results,
        }

        return summary

    def save(self, path: Path) -> None:
        """Save model bundle to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        bundle = {
            "long_model": self.long_model,
            "short_model": self.short_model,
            "long_calibrated": self.long_calibrated,
            "short_calibrated": self.short_calibrated,
            "feature_importance": self.feature_importance,
            "calibration_metrics": self.calibration_metrics,
            "walk_forward_results": self.walk_forward_results,
            "metadata": self.metadata,
            "threshold_long": self.threshold_long,
            "threshold_short": self.threshold_short,
        }
        joblib.dump(bundle, path)

    @classmethod
    def load(cls, path: Path) -> "ConfirmationModel":
        """Load model from disk."""
        bundle = joblib.load(path)
        model = cls(
            threshold_long=bundle.get("threshold_long", 0.75),
            threshold_short=bundle.get("threshold_short", 0.70),
        )
        model.long_model = bundle["long_model"]
        model.short_model = bundle["short_model"]
        model.long_calibrated = bundle["long_calibrated"]
        model.short_calibrated = bundle["short_calibrated"]
        model.feature_importance = bundle["feature_importance"]
        model.calibration_metrics = bundle["calibration_metrics"]
        model.walk_forward_results = bundle["walk_forward_results"]
        model.metadata = bundle["metadata"]
        return model

    def get_top_features(self, n: int = 10) -> List[Dict[str, float]]:
        """Get top N most important features."""
        sorted_features = sorted(
            self.feature_importance.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [{"feature": name, "importance": round(imp, 4)} for name, imp in sorted_features[:n]]
