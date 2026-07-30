"""
Multi-Model Ensemble - Combines Early Signal, Confirmation, and Momentum models.

Ensemble logic:
1. Early Signal Model detects pre-breakout setup (threshold 0.62)
2. Confirmation Model validates with calibrated probability (threshold 0.75)
3. Momentum Model checks short-term direction (threshold 0.55)

Decision matrix:
- All 3 agree → Full position (100% size)
- Early + Confirm agree → Reduced position (70% size)
- Early + Momentum agree → Small position (40% size)
- Only Early signals → Watch list (no entry)
- Any disagrees → Skip

Two-Stage Entry:
- Stage 1 (Early): 30-50% size when early signal detected
- Stage 2 (Confirmation): Add 50-70% when confirmed
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from .models.early_signal import EarlySignalModel, EarlySignalResult
from .models.confirmation import ConfirmationModel, ConfirmationResult
from .models.momentum import MomentumModel, MomentumResult


@dataclass(slots=True)
class EnsembleDecision:
    """Final decision from ensemble."""
    action: str  # 'enter_full', 'enter_reduced', 'enter_small', 'stage_1', 'stage_2', 'wait', 'skip'
    side: str
    confidence: float  # 0-100
    score: float  # Combined score
    early_result: Optional[EarlySignalResult] = None
    confirmation_result: Optional[ConfirmationResult] = None
    momentum_result: Optional[MomentumResult] = None
    position_size_pct: float = 1.0  # Multiplier (1.0 = 100%)
    reasoning: List[str] = None


class EnsembleEngine:
    """Combines all three models for robust decision making."""

    def __init__(
        self,
        early_model: EarlySignalModel,
        confirmation_model: ConfirmationModel,
        momentum_model: MomentumModel,
    ):
        self.early_model = early_model
        self.confirmation_model = confirmation_model
        self.momentum_model = momentum_model

    def evaluate(
        self,
        row: pd.Series,
        regime: Optional[str] = None,
        stage: str = "full",  # 'stage_1', 'stage_2', or 'full' (single-stage)
    ) -> Optional[EnsembleDecision]:
        """
        Evaluate ensemble decision for a single bar.

        Args:
            row: Row with all features
            regime: Current market regime
            stage: Entry stage ('stage_1', 'stage_2', or 'full')

        Returns:
            EnsembleDecision or None if no signals
        """
        # Run all three models
        early_result = self.early_model.predict(row, side="long", regime=regime)
        confirm_long = self.confirmation_model.predict(row, side="long", regime=regime)
        confirm_short = self.confirmation_model.predict(row, side="short", regime=regime)
        momentum_long = self.momentum_model.predict(row, side="long")
        momentum_short = self.momentum_model.predict(row, side="short")

        # Choose best side based on confirmation (with None checks)
        confirm_score_long = confirm_long.score if confirm_long else 0
        confirm_score_short = confirm_short.score if confirm_short else 0
        confirm_result = confirm_long if confirm_score_long > confirm_score_short else confirm_short

        momentum_score_long = momentum_long.score if momentum_long else 0
        momentum_score_short = momentum_short.score if momentum_short else 0
        momentum_result = momentum_long if momentum_score_long > momentum_score_short else momentum_short

        # Determine side with clear priority: confirmation > early signal > default short
        if confirm_result:
            side = confirm_result.side
        elif early_result and early_result.side:
            side = early_result.side
        else:
            side = "short"  # Conservative default when no signals

        # Decision logic based on model agreement
        agreements = []
        if early_result and early_result.score >= 62:
            agreements.append("early")
        if confirm_result and confirm_result.is_confirmed:
            agreements.append("confirm")
        if momentum_result and momentum_result.direction == "with_momentum":
            agreements.append("momentum")

        # Determine action based on agreements and stage
        if stage == "stage_1":
            # Early entry stage - only need early signal
            if early_result and early_result.score >= 62:
                action = "stage_1"
                position_size = 0.4  # 40% size for early entry
                confidence = early_result.score
            else:
                return None  # No early signal

        elif stage == "stage_2":
            # Confirmation stage - need confirmation
            if confirm_result and confirm_result.is_confirmed:
                action = "stage_2"
                position_size = 0.6  # 60% size for confirmation
                confidence = confirm_result.score
            else:
                return None  # Not confirmed

        else:
            # Full ensemble (single-stage mode)
            if len(agreements) == 3:
                # All agree - full position
                action = "enter_full"
                position_size = 1.0
                early_score = early_result.score if early_result else 0
                confirm_score = confirm_result.score if confirm_result else 0
                momentum_score = momentum_result.score if momentum_result else 0
                confidence = (early_score + confirm_score + momentum_score) / 3

            elif len(agreements) == 2:
                if "early" in agreements and "confirm" in agreements:
                    # Early + Confirm
                    action = "enter_reduced"
                    position_size = 0.7
                    early_score = early_result.score if early_result else 0
                    confirm_score = confirm_result.score if confirm_result else 0
                    confidence = (early_score + confirm_score) / 2
                elif "early" in agreements and "momentum" in agreements:
                    # Early + Momentum
                    action = "enter_small"
                    position_size = 0.4
                    early_score = early_result.score if early_result else 0
                    momentum_score = momentum_result.score if momentum_result else 0
                    confidence = (early_score + momentum_score) / 2
                else:
                    # Confirm + Momentum (no early) - still enter reduced
                    action = "enter_reduced"
                    position_size = 0.6
                    confirm_score = confirm_result.score if confirm_result else 0
                    momentum_score = momentum_result.score if momentum_result else 0
                    confidence = (confirm_score + momentum_score) / 2

            elif len(agreements) == 1:
                if "early" in agreements:
                    action = "wait"  # Only early, wait for confirmation
                    position_size = 0.0
                    confidence = early_result.score
                else:
                    action = "skip"  # Only confirm or momentum without early
                    position_size = 0.0
                    confidence = 0.0

            else:
                action = "skip"
                position_size = 0.0
                confidence = 0.0

        # Build reasoning
        reasoning = []
        if early_result:
            reasoning.append(f"Early: {early_result.score:.0f} (compression={early_result.compression_detected}, volume={early_result.volume_drying})")
        if confirm_result:
            reasoning.append(f"Confirm: {confirm_result.score:.0f} (calibrated={confirm_result.probability:.2%})")
        if momentum_result:
            reasoning.append(f"Momentum: {momentum_result.direction} ({momentum_result.strength})")

        return EnsembleDecision(
            action=action,
            side=side,
            confidence=round(confidence, 2),
            score=round(confidence * position_size, 2),
            early_result=early_result,
            confirmation_result=confirm_result,
            momentum_result=momentum_result,
            position_size_pct=position_size,
            reasoning=reasoning,
        )

    def get_feature_summary(self) -> Dict[str, Any]:
        """Get summary of important features across all models."""
        return {
            "early_top_features": self.early_model.get_top_features(n=5),
            "confirmation_top_features": self.confirmation_model.get_top_features(n=5),
            "momentum_top_features": self.momentum_model.get_top_features(n=5),
        }
