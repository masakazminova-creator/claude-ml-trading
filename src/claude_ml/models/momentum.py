"""
Momentum Model - Short-term direction prediction for entry timing refinement.

Predicts next 1-3 bars direction using pure momentum features:
- Price acceleration
- Volume momentum
- RSI momentum
- Order flow momentum
- Microstructure momentum

Characteristics:
- Very fast inference (lightweight features only)
- Lower threshold (0.55) for timing refinement
- Used together with confirmation model
- Helps avoid entering when momentum is against us
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV


# Lightweight momentum-only features for fast inference
MOMENTUM_FEATURES = [
    # Price momentum
    "ret_1",
    "ret_2",
    "ret_3",
    "impulse_1_vs_3",
    "ema_slope_8",
    # Volume momentum
    "vol_zscore",
    "volume_slope_3",
    "turnover_zscore",
    # RSI momentum
    "rsi_14",
    "tf60_rsi_14",
    # Close position
    "bar_close_position",
    "recent_range_progress_6",
    # Microstructure
    "ob_imbalance_top_10",
    "trade_flow_imbalance",
    "trade_buy_ratio",
    # Time context
    "hour_sin",
    "hour_cos",
    "session_asia",
    "session_eu",
    "session_us",
]


@dataclass(slots=True)
class MomentumResult:
    """Result from momentum model prediction."""
    side: str
    probability: float
    score: float  # 0-100
    confidence: float
    direction: str  # 'with_momentum', 'against_momentum', 'neutral'
    strength: str  # 'strong', 'moderate', 'weak'
    acceleration: bool  # Price accelerating?


class MomentumModel:
    """Lightweight model for short-term momentum prediction."""

    def __init__(
        self,
        threshold: float = 0.55,
        horizon_bars: int = 3,
    ):
        self.threshold = threshold
        self.horizon_bars = horizon_bars

        self.long_model: Optional[HistGradientBoostingClassifier] = None
        self.short_model: Optional[HistGradientBoostingClassifier] = None
        self.long_calibrated: Optional[CalibratedClassifierCV] = None
        self.short_calibrated: Optional[CalibratedClassifierCV] = None

        self.feature_importance: Dict[str, float] = {}
        self.metadata: Dict[str, Any] = {}

    def create_model(self) -> HistGradientBoostingClassifier:
        """Create lightweight classifier for momentum."""
        return HistGradientBoostingClassifier(
            max_depth=3,  # Very shallow for speed
            learning_rate=0.06,
            max_iter=150,  # Fast training
            min_samples_leaf=30,  # Prevent overfitting
            random_state=42,
            early_stopping=True,
            validation_fraction=0.1,
        )

    def _create_momentum_labels(
        self,
        df: pd.DataFrame,
        side: str,
    ) -> pd.Series:
        """
        Create labels based on next N bars direction.

        For long: next N bars high > current high
        For short: next N bars low < current low
        """
        if side == "long":
            future_high = df["high"].shift(-self.horizon_bars)
            return ((future_high > df["high"]).astype(int))
        else:
            future_low = df["low"].shift(-self.horizon_bars)
            return ((future_low < df["low"]).astype(int))

    def train(
        self,
        df: pd.DataFrame,
        side: str,
        train_split: float = 0.8,
    ) -> Dict[str, Any]:
        """Train momentum model for one side."""
        # Create momentum labels
        target_col = f"momentum_{side}_{self.horizon_bars}bars"
        df[target_col] = self._create_momentum_labels(df, side)

        # Filter available features
        available_features = [f for f in MOMENTUM_FEATURES if f in df.columns]
        ready = df.dropna(subset=available_features + [target_col]).reset_index(drop=True)

        if len(ready) < 800:
            raise RuntimeError(f"Not enough data for {side} momentum model (need 800+, got {len(ready)})")

        # Split
        split_idx = max(400, int(len(ready) * train_split))
        split_idx = min(split_idx, len(ready) - 150)
        train_df = ready.iloc[:split_idx].copy()
        test_df = ready.iloc[split_idx:].copy()

        # Train
        model = self.create_model()
        model.fit(train_df[available_features], train_df[target_col].astype(int))

        # Calibrate
        calibrated = CalibratedClassifierCV(model, cv=5, method='sigmoid')
        calibrated.fit(test_df[available_features], test_df[target_col].astype(int))

        # Store
        if side == "long":
            self.long_model = model
            self.long_calibrated = calibrated
        else:
            self.short_model = model
            self.short_calibrated = calibrated

        # Feature importance
        from sklearn.inspection import permutation_importance
        importance = permutation_importance(
            model,
            test_df[available_features],
            test_df[target_col].astype(int),
            n_repeats=3,
            random_state=42,
        )

        self.feature_importance = {
            name: float(score)
            for name, score in zip(available_features, importance.importances_mean, strict=False)
        }

        report = {
            "side": side,
            "horizon_bars": self.horizon_bars,
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "features_used": len(available_features),
            "threshold": self.threshold,
            "positive_rate": float(test_df[target_col].astype(int).mean()),
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }

        self.metadata = report
        return report

    def predict(
        self,
        row: pd.Series,
        side: str,
    ) -> Optional[MomentumResult]:
        """Predict short-term momentum direction."""
        calibrated = self.long_calibrated if side == "long" else self.short_calibrated
        if calibrated is None:
            return None

        # Extract features
        available_features = [f for f in MOMENTUM_FEATURES if f in row.index]
        features_df = row[available_features].to_frame().T

        # Predict
        proba = float(calibrated.predict_proba(features_df)[0, 1])

        # Determine direction
        if proba > 0.60:
            direction = "with_momentum"
            strength = "strong" if proba > 0.70 else "moderate"
        elif proba < 0.40:
            direction = "against_momentum"
            strength = "strong" if proba < 0.30 else "moderate"
        else:
            direction = "neutral"
            strength = "weak"

        # Check acceleration (ret_1 vs ret_3/3)
        ret_1 = abs(row.get("ret_1", 0))
        ret_3_avg = abs(row.get("ret_3", 0)) / 3 if row.get("ret_3", 0) != 0 else 0
        acceleration = ret_1 > ret_3_avg * 1.2

        score = proba * 100
        confidence = abs(proba - 0.5) * 2

        return MomentumResult(
            side=side,
            probability=round(proba, 4),
            score=round(score, 2),
            confidence=round(confidence, 4),
            direction=direction,
            strength=strength,
            acceleration=acceleration,
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
            "horizon_bars": self.horizon_bars,
        }
        joblib.dump(bundle, path)

    @classmethod
    def load(cls, path: Path) -> "MomentumModel":
        """Load model from disk."""
        bundle = joblib.load(path)
        model = cls(
            threshold=bundle.get("threshold", 0.55),
            horizon_bars=bundle.get("horizon_bars", 3),
        )
        model.long_model = bundle["long_model"]
        model.short_model = bundle["short_model"]
        model.long_calibrated = bundle["long_calibrated"]
        model.short_calibrated = bundle["short_calibrated"]
        model.feature_importance = bundle["feature_importance"]
        model.metadata = bundle["metadata"]
        return model
