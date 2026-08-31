"""
Early Signal Model - Detects pre-breakout setups before the move happens.

Uses lightweight features to identify:
- Range compression (volatility squeeze)
- Volume drying up before expansion
- Order book accumulation patterns
- MTF alignment forming

Characteristics:
- Lower threshold (0.60-0.65) for earlier entries
- Smaller position size (30-50% of normal)
- Wider SL to give trade room
- Fast inference (no heavy computation)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import precision_score, recall_score, roc_auc_score


# Features specifically for early signal detection
EARLY_SIGNAL_FEATURES = [
    # Range compression
    "atr_slope_3",
    "atr_slope_6",
    "range_compression",
    "bollinger_width_pct",
    # Volume trends
    "volume_slope_3",
    "volume_slope_6",
    "volume_drying",
    # Order book accumulation
    "ob_imbalance_trend_3",
    "ob_imbalance_trend_6",
    "ob_accumulation_score",
    # MTF alignment forming
    "mtf_alignment_forming",
    "ema_convergence_ratio",
    # Momentum divergence
    "rsi_divergence_score",
    "price_momentum_vs_rsi",
    # Extreme positions
    "extreme_close_position",
    "distance_from_vwap",
    # Breakout potential
    "donchian_breakout_score",
    "keltner_position",
    # Basic context
    "bar_close_position",
    "recent_range_progress_6",
    "ema_8_vs_21",
    "rsi_14",
]


@dataclass(slots=True)
class EarlySignalResult:
    """Result from early signal detection."""
    side: str  # 'long' or 'short'
    probability: float
    score: float  # Combined score (0-100)
    confidence: float  # Model confidence (0-1)
    regime: str
    features_used: int
    compression_detected: bool
    volume_drying: bool
    ob_accumulation: bool
    mtf_forming: bool


class EarlySignalModel:
    """Lightweight model for detecting pre-breakout setups."""

    def __init__(self, threshold: float = 0.62):
        self.threshold = threshold
        self.long_model: Optional[HistGradientBoostingClassifier] = None
        self.short_model: Optional[HistGradientBoostingClassifier] = None
        self.long_calibrated: Optional[CalibratedClassifierCV] = None
        self.short_calibrated: Optional[CalibratedClassifierCV] = None
        self.feature_importance: Dict[str, float] = {}
        self.metadata: Dict[str, Any] = {}

    def create_model(self) -> HistGradientBoostingClassifier:
        """Create a lightweight classifier for early signals."""
        return HistGradientBoostingClassifier(
            max_depth=4,  # Shallower for faster inference
            learning_rate=0.05,
            max_iter=200,  # Fewer iterations
            min_samples_leaf=25,  # More samples to avoid overfitting
            random_state=42,
            early_stopping=True,
            validation_fraction=0.15,
        )

    def train(
        self,
        df: pd.DataFrame,
        target_column: str,
        side: str,
        train_split: float = 0.8
    ) -> Dict[str, Any]:
        """
        Train early signal model for one side.

        Args:
            df: DataFrame with features and labels
            target_column: 'long_target' or 'short_target'
            side: 'long' or 'short'
            train_split: Train/test split ratio

        Returns:
            Training report with metrics
        """
        # Filter to early signal features only
        available_features = [f for f in EARLY_SIGNAL_FEATURES if f in df.columns]
        ready = df.dropna(subset=available_features + [target_column]).reset_index(drop=True)

        if len(ready) < 500:
            raise RuntimeError(f"Not enough data for {side} early signal model (need 500+, got {len(ready)})")
        if ready[target_column].nunique() < 2:
            raise RuntimeError(
                f"Single-class target '{target_column}' for {side} early signal model "
                f"(values: {ready[target_column].unique()[:5].tolist()}) — cannot train classifier"
            )

        # Split
        split_idx = max(250, int(len(ready) * train_split))
        split_idx = min(split_idx, len(ready) - 100)
        train_df = ready.iloc[:split_idx].copy()
        test_df = ready.iloc[split_idx:].copy()

        # Train base model
        model = self.create_model()
        model.fit(train_df[available_features], train_df[target_column].astype(int))

        # Calibrate probabilities (Platt scaling)
        calibrated = CalibratedClassifierCV(model, cv=5, method='sigmoid')
        calibrated.fit(test_df[available_features], test_df[target_column].astype(int))

        # Evaluate
        proba = calibrated.predict_proba(test_df[available_features])[:, 1]
        pred = (proba >= self.threshold).astype(int)

        # Feature importance using permutation importance (works with all sklearn versions)
        from sklearn.inspection import permutation_importance
        perm_importance = permutation_importance(model, test_df[available_features], test_df[target_column].astype(int), n_repeats=5, random_state=42)
        importance = {
            name: float(score)
            for name, score in zip(available_features, perm_importance.importances_mean, strict=False)
        }

        report = {
            "side": side,
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "features_used": len(available_features),
            "threshold": self.threshold,
            "positive_rate_test": float(test_df[target_column].astype(int).mean()),
            "precision": float(precision_score(test_df[target_column].astype(int), pred, zero_division=0)),
            "recall": float(recall_score(test_df[target_column].astype(int), pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(test_df[target_column].astype(int), proba)) if test_df[target_column].nunique() == 2 else 0.0,
            "feature_importance": importance,
        }

        # Store models
        if side == "long":
            self.long_model = model
            self.long_calibrated = calibrated
        else:
            self.short_model = model
            self.short_calibrated = calibrated

        self.feature_importance = importance
        self.metadata = report

        return report

    def predict(
        self,
        row: pd.Series,
        side: str,
        regime: Optional[str] = None
    ) -> Optional[EarlySignalResult]:
        """
        Predict early signal for a single bar.

        Args:
            row: Single row with features
            side: 'long' or 'short'
            regime: Current market regime (optional filter)

        Returns:
            EarlySignalResult or None if no signal
        """
        # Get appropriate model
        calibrated = self.long_calibrated if side == "long" else self.short_calibrated
        if calibrated is None:
            return None

        # Extract features
        available_features = [f for f in EARLY_SIGNAL_FEATURES if f in row.index]
        features = row[available_features].to_dict()
        features_df = pd.DataFrame([features])

        # Predict
        proba = float(calibrated.predict_proba(features_df)[0, 1])
        confidence = abs(proba - 0.5) * 2  # Scale to 0-1, centered at 0.5

        # Check if above threshold
        if proba < self.threshold:
            return None

        # Calculate score (0-100)
        score = proba * 100

        # Check early detection conditions
        compression = bool(row.get("range_compression", False))
        vol_drying = bool(row.get("volume_drying", False))
        ob_accum = bool(row.get("ob_accumulation_score", 0) > 0)
        mtf_form = bool(row.get("mtf_alignment_forming", False))

        # Boost score if multiple early conditions met
        conditions_met = sum([compression, vol_drying, ob_accum, mtf_form])
        if conditions_met >= 3:
            score = min(100, score + 15)  # Bonus for strong setup
        elif conditions_met >= 2:
            score = min(100, score + 8)

        return EarlySignalResult(
            side=side,
            probability=round(proba, 4),
            score=round(score, 2),
            confidence=round(confidence, 4),
            regime=regime or "unknown",
            features_used=len(available_features),
            compression_detected=compression,
            volume_drying=vol_drying,
            ob_accumulation=ob_accum,
            mtf_forming=mtf_form,
        )

    def save(self, path: Path) -> None:
        """Save model to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        bundle = {
            "long_model": self.long_model,
            "short_model": self.short_model,
            "long_calibrated": self.long_calibrated,
            "short_calibrated": self.short_calibrated,
            "feature_importance": self.feature_importance,
            "metadata": self.metadata,
            "threshold": self.threshold,
        }
        joblib.dump(bundle, path)

    @classmethod
    def load(cls, path: Path) -> "EarlySignalModel":
        """Load model from disk."""
        bundle = joblib.load(path)
        model = cls(threshold=bundle.get("threshold", 0.62))
        model.long_model = bundle["long_model"]
        model.short_model = bundle["short_model"]
        model.long_calibrated = bundle["long_calibrated"]
        model.short_calibrated = bundle["short_calibrated"]
        model.feature_importance = bundle["feature_importance"]
        model.metadata = bundle["metadata"]
        return model

    def get_top_features(self, n: int = 10) -> List[Dict[str, float]]:
        """Get top N most important features."""
        sorted_features = sorted(
            self.feature_importance.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [{"feature": name, "importance": round(imp, 4)} for name, imp in sorted_features[:n]]
