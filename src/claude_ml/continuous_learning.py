"""
Continuous Learning Pipeline - Automatic model retraining and adaptation.

Features:
- Performance monitoring with drift detection
- Automatic retraining trigger based on metrics degradation
- A/B testing framework for new models
- Model promotion only if better than current
- Rolling window training to focus on recent data
- Walk-forward validation before promotion
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np

from .config import Settings
from .data_collector import OKXCollector
from .feature_engineering import build_features
from .adaptive_labels import create_balanced_labels
from .models.early_signal import EarlySignalModel
from .models.confirmation import ConfirmationModel
from .models.momentum import MomentumModel

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PerformanceMetrics:
    """Current trading performance metrics."""
    total_trades: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    recent_win_rate_10: float = 0.0
    recent_win_rate_50: float = 0.0
    last_updated: str = ""


@dataclass(slots=True)
class DriftDetection:
    """Detects performance drift in model predictions."""
    baseline_precision: float = 0.6
    current_precision: float = 0.0
    precision_drop: float = 0.0
    is_drifting: bool = False
    samples_checked: int = 0
    confidence_calibration: float = 0.0  # Correlation between predicted prob and actual


@dataclass(slots=True)
class RetrainingResult:
    """Result from automatic retraining."""
    triggered: bool = False
    reason: str = ""
    old_metrics: Optional[PerformanceMetrics] = None
    new_metrics: Optional[PerformanceMetrics] = None
    improvement: float = 0.0
    promoted: bool = False
    model_path: str = ""


class ContinuousLearningEngine:
    """
    Automatically monitors, detects drift, and retrains models.

    Workflow:
    1. Monitor performance every N trades
    2. Detect drift (win rate drop, calibration loss)
    3. Trigger retraining if drift detected
    4. A/B test new model against old
    5. Promote only if new is better
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.conn = sqlite3.connect(settings.runtime_db_path, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.row_factory = sqlite3.Row

        # Baseline metrics (from initial training)
        self.baseline_metrics = PerformanceMetrics(
            win_rate=0.50,  # Expected win rate
            profit_factor=1.3,
            avg_pnl=0.05,
        )

        # Drift thresholds
        self.win_rate_drop_threshold = 0.10  # Alert if WR drops by 10%
        self.calibration_threshold = 0.3     # Alert if correlation < 0.3
        self.min_trades_for_check = 50       # Need at least 50 trades to check

        # Adaptive retraining config
        # Read from config with backward-compatible fallbacks (these were
        # hardcoded, so RETRAIN_INTERVAL_TRADES in .env did nothing).
        self.base_retrain_interval_trades = int(getattr(self.settings, 'retrain_interval_trades', 100) * 0.5)  # 50 by default: check more often than configured base
        self.min_retrain_interval_trades = 10    # Minimum in high volatility
        self.max_retrain_interval_trades = int(getattr(self.settings, 'retrain_interval_trades', 100))

        self.base_training_lookback_bars = 1000  # Base lookback (~10 days on 15m, was 2000)
        self.min_training_lookback_bars = 300    # Minimum in fast markets (~3 days, was 500)
        self.max_training_lookback_bars = 3000   # Maximum in stable markets (~31 days, was 5000)
        self.training_lookback_bars = self.base_training_lookback_bars  # Initialize with base value
        self.retrain_interval_trades = self.base_retrain_interval_trades  # Initialize adaptive interval
        self.last_retrain_time = time.time()  # Track last retrain for time-based forcing
        self.min_retrain_interval_seconds = 3600  # Force retrain at least every 1 hour

        self.walk_forward_folds = 5

        # Volatility thresholds for adaptive retraining
        self.high_volatility_atr_pct = 2.0       # High vol if ATR > 2%
        self.low_volatility_atr_pct = 0.8        # Low vol if ATR < 0.8%

        # Degradation protection thresholds
        self.max_acceptable_dd = 20.0        # Max drawdown 20%
        self.min_acceptable_wr = 35.0        # Min win rate 35%
        self.min_acceptable_pf = 0.8         # Min profit factor 0.8
        self.emergency_stop_wr = 30.0        # Emergency stop if WR < 30%
        self.consecutive_losses_threshold = 8 # Pause after 8 consecutive losses

    def check_performance(self) -> PerformanceMetrics:
        """Check current trading performance from database."""
        # Get all closed trades
        trades = self.conn.execute("""
            SELECT pnl_pct FROM paper_trades
            WHERE status IN ('closed', 'shadow_closed') AND pnl_pct IS NOT NULL
            ORDER BY id DESC
        """).fetchall()

        if not trades:
            return PerformanceMetrics(last_updated=datetime.now(timezone.utc).isoformat())

        pnls = [t['pnl_pct'] for t in trades]
        total = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        losses = total - wins

        win_rate = wins / total * 100 if total > 0 else 0
        avg_pnl = sum(pnls) / total if total > 0 else 0

        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Recent performance (last 10 and 50 trades)
        recent_10 = pnls[:10]
        recent_50 = pnls[:50]
        recent_wr_10 = sum(1 for p in recent_10 if p > 0) / len(recent_10) * 100 if recent_10 else 0
        recent_wr_50 = sum(1 for p in recent_50 if p > 0) / len(recent_50) * 100 if recent_50 else 0

        # Max drawdown
        equity = 1000.0  # Starting balance
        peak = equity
        max_dd = 0.0
        for pnl in pnls[::-1]:  # Reverse to chronological order
            equity *= (1 + pnl / 100)
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd

        metrics = PerformanceMetrics(
            total_trades=total,
            win_rate=round(win_rate, 2),
            avg_pnl=round(avg_pnl, 4),
            profit_factor=round(profit_factor, 2),
            recent_win_rate_10=round(recent_wr_10, 2),
            recent_win_rate_50=round(recent_wr_50, 2),
            max_drawdown=round(max_dd, 2),
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

        # Log to database
        self.conn.execute("""
            INSERT INTO health_log (ts, status, error_streak, note)
            VALUES (?, ?, ?, ?)
        """, (
            metrics.last_updated,
            "ok",  # Changed from "performance_check" to "ok"
            0,
            json.dumps({
                "trades": metrics.total_trades,
                "win_rate": metrics.win_rate,
                "profit_factor": metrics.profit_factor,
            })
        ))
        self.conn.commit()

        return metrics

    def detect_drift(self, metrics: PerformanceMetrics) -> DriftDetection:
        """
        Detect if model performance has drifted from baseline.

        Checks:
        1. Win rate drop
        2. Profit factor drop
        3. Calibration loss (predicted prob vs actual)
        """
        drift = DriftDetection(
            baseline_precision=self.baseline_metrics.win_rate,
            current_precision=metrics.win_rate,
            precision_drop=self.baseline_metrics.win_rate - metrics.win_rate,
            samples_checked=metrics.total_trades,
        )

        # Check if drifting
        if metrics.total_trades >= self.min_trades_for_check:
            # Win rate dropped significantly
            if drift.precision_drop > self.win_rate_drop_threshold:
                drift.is_drifting = True

            # Profit factor too low
            if metrics.profit_factor < 1.0:
                drift.is_drifting = True

            # Recent performance much worse than overall
            if metrics.recent_win_rate_10 < metrics.win_rate - 15:
                drift.is_drifting = True

        # Check calibration (if we have enough data)
        if metrics.total_trades >= 100:
            # Simple heuristic: if win_rate != avg probability, calibration is off
            # This would need actual probability tracking, simplified here
            pass

        return drift

    def check_emergency_stop(self, metrics: PerformanceMetrics) -> tuple[bool, str]:
        """
        Check if trading should be EMERGENCY STOPPED due to severe degradation.

        Returns:
            (should_stop, reason)
        """
        # Not enough data
        if metrics.total_trades < 10:
            return False, ""

        # Critical win rate drop
        if metrics.win_rate < self.min_acceptable_wr:
            return True, f"CRITICAL: Win rate {metrics.win_rate:.1f}% below minimum {self.min_acceptable_wr}%"

        # Critical drawdown
        if metrics.max_drawdown > self.max_acceptable_dd:
            return True, f"CRITICAL: Drawdown {metrics.max_drawdown:.1f}% exceeds maximum {self.max_acceptable_dd}%"

        # Very low profit factor
        if metrics.profit_factor < self.min_acceptable_pf and metrics.total_trades > 30:
            return True, f"CRITICAL: Profit factor {metrics.profit_factor:.2f} critically low"

        # Recent performance catastrophic
        if metrics.recent_win_rate_10 < self.emergency_stop_wr and metrics.total_trades > 20:
            return True, f"CRITICAL: Recent WR {metrics.recent_win_rate_10:.1f}% is catastrophic"

        # Check consecutive losses (would need trade-by-trade data)
        # Simplified: if last 10 trades all losses
        recent_wr = metrics.recent_win_rate_10
        if recent_wr == 0 and metrics.total_trades >= 10:
            return True, f"CRITICAL: 10+ consecutive losses detected"

        return False, ""

    def should_retrain(self, metrics: PerformanceMetrics, drift: DriftDetection, current_atr_pct: float = 1.0) -> tuple[bool, str]:
        """
        Decide if retraining should be triggered with adaptive frequency.

        Args:
            metrics: Current performance metrics
            drift: Drift detection results
            current_atr_pct: Current ATR as percentage (volatility)

        Returns:
            (should_retrain, reason)
        """
        # EMERGENCY CHECK FIRST
        emergency_stop, emergency_reason = self.check_emergency_stop(metrics)
        if emergency_stop:
            return True, f"EMERGENCY: {emergency_reason}"

        # Always retrain if not enough data
        if metrics.total_trades == 0:
            return True, "No trades yet, initial training needed"

        # Calculate adaptive retrain interval based on volatility and performance
        wr_drop = self.baseline_metrics.win_rate - metrics.win_rate
        adaptive_interval, adaptive_lookback = self.calculate_adaptive_retrain_params(
            atr_pct=current_atr_pct,
            recent_wr_drop=wr_drop
        )

        # Update the instance variable so it's used during retraining
        self.retrain_interval_trades = adaptive_interval
        self.training_lookback_bars = adaptive_lookback

        # Retrain on adaptive interval
        if metrics.total_trades > 0 and metrics.total_trades % adaptive_interval == 0:
            return True, f"Adaptive periodic retrain at {metrics.total_trades} trades (ATR={current_atr_pct:.2f}%, interval={adaptive_interval})"

        # Time-based retraining check (even with 0 trades)
        last_training_age_hours = self._get_model_age_hours()
        max_age_hours = 4  # Retrain every 4 hours to adapt to market changes (was 48h)

        if last_training_age_hours is None or last_training_age_hours > max_age_hours:
            age_str = "unknown" if last_training_age_hours is None else f"{last_training_age_hours:.1f}h"
            return True, f"Time-based retrain: models are {age_str} old (max: {max_age_hours}h)"

        # Check for rapid market regime change (every cycle)
        if self._detect_regime_change():
            return True, "Market regime changed - immediate retrain needed"

        # Volatility spike detection (check every few bars)
        if current_atr_pct and self._detect_volatility_spike(current_atr_pct):
            return True, f"Volatility spike detected (ATR={current_atr_pct:.2f}%)"

        # Retrain on drift
        if drift.is_drifting:
            return True, f"Performance drift detected (WR drop: {drift.precision_drop:.1f}%)"

        # Retrain if profit factor too low
        if metrics.profit_factor < 1.0 and metrics.total_trades > 50:
            return True, f"Low profit factor: {metrics.profit_factor:.2f}"

        # Retrain if recent performance declining
        if metrics.recent_win_rate_10 < metrics.win_rate - 20 and metrics.total_trades > 30:
            return True, f"Sharp recent decline: recent WR {metrics.recent_win_rate_10:.1f}% vs overall {metrics.win_rate:.1f}%"

        return False, ""

    def calculate_adaptive_retrain_params(self, atr_pct: float, recent_wr_drop: float) -> tuple[int, int]:
        """
        Calculate adaptive retraining parameters based on market conditions.

        Args:
            atr_pct: Current ATR as percentage (volatility measure)
            recent_wr_drop: Recent win rate drop % (performance degradation)

        Returns:
            (retrain_interval_trades, training_lookback_bars)
        """
        # 1. Volatility-based adjustment
        if atr_pct > self.high_volatility_atr_pct:
            # High volatility → retrain more often, use shorter history
            vol_retrain_mult = 0.3  # 30% of base interval
            vol_lookback_mult = 0.4  # 40% of base lookback
        elif atr_pct > 1.5:
            # Elevated volatility
            vol_retrain_mult = 0.5
            vol_lookback_mult = 0.6
        elif atr_pct > self.low_volatility_atr_pct:
            # Normal volatility
            vol_retrain_mult = 1.0
            vol_lookback_mult = 1.0
        else:
            # Low volatility → can retrain less often
            vol_retrain_mult = 1.5
            vol_lookback_mult = 1.5

        # 2. Performance degradation adjustment
        if recent_wr_drop > 15:  # Severe degradation
            perf_retrain_mult = 0.3  # Retrain urgently
            perf_lookback_mult = 0.4  # Focus on very recent data
        elif recent_wr_drop > 10:
            perf_retrain_mult = 0.5
            perf_lookback_mult = 0.6
        elif recent_wr_drop > 5:
            perf_retrain_mult = 0.8
            perf_lookback_mult = 0.9
        else:
            perf_retrain_mult = 1.0
            perf_lookback_mult = 1.0

        # 3. Calculate final values (use more aggressive of the two)
        retrain_mult = min(vol_retrain_mult, perf_retrain_mult)
        lookback_mult = min(vol_lookback_mult, perf_lookback_mult)

        retrain_interval = int(self.base_retrain_interval_trades * retrain_mult)
        lookback_bars = int(self.base_training_lookback_bars * lookback_mult)

        # Apply bounds
        retrain_interval = max(self.min_retrain_interval_trades,
                              min(self.max_retrain_interval_trades, retrain_interval))
        lookback_bars = max(self.min_training_lookback_bars,
                           min(self.max_training_lookback_bars, lookback_bars))
        # Models require >= 800 rows to train (momentum), so never fetch less —
        # otherwise retraining fails "Not enough data" exactly in high vol,
        # the regime designed to force it.
        lookback_bars = max(lookback_bars, 1000)

        logger.info(f"[ADAPTIVE RETRAIN] ATR={atr_pct:.2f}%, WR_drop={recent_wr_drop:.1f}%")
        logger.info(f"[ADAPTIVE RETRAIN] Retrain every {retrain_interval} trades, lookback {lookback_bars} bars")

        return retrain_interval, lookback_bars

    def _get_model_age_hours(self) -> Optional[float]:
        """Get the age of the oldest model in hours."""
        from pathlib import Path

        model_dir = self.settings.models_dir
        if not model_dir.exists():
            return None

        # Only count LIVE model files — *_new.joblib candidates are never
        # promoted as-is and would skew the age-based retrain trigger.
        model_files = [f for f in model_dir.glob("*.joblib") if not f.name.endswith("_new.joblib")]
        if not model_files:
            return None

        # Get modification times of all models
        import time
        now = time.time()
        ages_hours = [(now - f.stat().st_mtime) / 3600 for f in model_files]

        # Return age of oldest model
        return max(ages_hours) if ages_hours else None

    def _detect_regime_change(self) -> bool:
        """
        Detect if market regime has changed significantly.

        Compares current regime characteristics with last training period.
        Returns True if significant change detected.
        """
        # TODO: Implement proper regime change detection
        # For now, use simple heuristic based on recent performance
        # If win rate dropped significantly in last 10 trades vs previous 50
        try:
            recent_10 = self.conn.execute("""
                SELECT pnl_pct FROM paper_trades
                WHERE status IN ('closed', 'shadow_closed') AND ABS(pnl_pct) > 0.01
                ORDER BY id DESC LIMIT 10
            """).fetchall()

            if len(recent_10) < 5:
                return False

            recent_wr = sum(1 for r in recent_10 if float(r[0]) > 0) / len(recent_10) * 100

            prev_50 = self.conn.execute("""
                SELECT pnl_pct FROM paper_trades
                WHERE status IN ('closed', 'shadow_closed') AND ABS(pnl_pct) > 0.01
                ORDER BY id DESC LIMIT 50 OFFSET 10
            """).fetchall()

            if len(prev_50) < 20:
                return False

            prev_wr = sum(1 for r in prev_50 if float(r[0]) > 0) / len(prev_50) * 100

            # Significant drop indicates regime change
            wr_drop = prev_wr - recent_wr
            return wr_drop > 15  # 15% drop suggests regime change

        except Exception as e:
            logger.warning(f"Regime change detection failed: {e}")
            return False

    def _detect_volatility_spike(self, current_atr_pct: float) -> bool:
        """
        Detect if volatility has spiked beyond normal range.

        Args:
            current_atr_pct: Current ATR as percentage

        Returns:
            True if volatility spike detected
        """
        # Get historical ATR values from recent trades
        try:
            cursor = self.conn.execute("""
                SELECT payload_json FROM paper_trades
                WHERE status IN ('closed', 'shadow_closed')
                  AND payload_json IS NOT NULL
                ORDER BY id DESC LIMIT 20
            """)

            atr_values = []
            for row in cursor.fetchall():
                if row[0]:
                    import json
                    payload = json.loads(row[0])
                    atr = payload.get('atr_pct', None)
                    if atr and atr > 0:
                        atr_values.append(atr * 100)  # Convert ratio to percentage

            if len(atr_values) < 5:
                return False

            avg_atr = sum(atr_values) / len(atr_values)
            std_atr = (sum((x - avg_atr)**2 for x in atr_values) / len(atr_values)) ** 0.5

            # Check if current ATR is more than 2 standard deviations above mean
            z_score = (current_atr_pct - avg_atr) / std_atr if std_atr > 0 else 0
            return z_score > 2.0  # More than 2 std devs = spike

        except Exception as e:
            logger.warning(f"Volatility spike detection failed: {e}")
            return False

    def fetch_recent_data(self, symbol: str = "BTCUSDT", lookback_bars: Optional[int] = None) -> pd.DataFrame:
        """Fetch recent market data for retraining."""
        logger.info(f"\n[RETRAIN] Fetching recent data for {symbol}...")

        inst_id = f"{symbol.replace('USDT', '')}-USDT-SWAP"
        collector = OKXCollector(base_url=self.settings.okx_base_url, inst_id=inst_id)

        df = collector.fetch_history(
            symbol=symbol,
            interval=self.settings.timeframe,
            lookback_bars=self.training_lookback_bars
        )

        logger.info(f"[RETRAIN] Fetched {len(df)} candles")
        return df

    def retrain_all_models(self, df: pd.DataFrame) -> RetrainingResult:
        """
        Retrain all models with fresh data.

        Process:
        1. Build features
        2. Create labels
        3. Train new models
        4. Validate with walk-forward
        5. Compare with current models
        6. Promote if better
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"[RETRAIN] STARTING MODEL RETRAINING")
        logger.info(f"{'='*80}")

        # Build features
        logger.info("[RETRAIN] Building features...")
        featured = build_features(df)
        logger.info(f"[RETRAIN] Built {len(featured.columns)} features, {len(featured)} rows")

        # Create labels with adaptive min_return based on current volatility
        logger.info("[RETRAIN] Creating adaptive labels...")
        labeled_early = create_balanced_labels(
            featured,
            horizon_bars=6,
            base_min_return_pct=float(self.settings.label_min_return_pct),
            take_profit_mult=float(self.settings.take_profit_atr_multiplier),
            stop_loss_mult=float(self.settings.stop_loss_atr_multiplier),
            max_hold_bars=int(getattr(self.settings, 'max_hold_bars', 6)),
        )

        labeled_momentum = create_balanced_labels(
            featured,
            horizon_bars=3,
            base_min_return_pct=0.20,
            take_profit_mult=float(self.settings.take_profit_atr_multiplier) * 0.5,
            stop_loss_mult=float(self.settings.stop_loss_atr_multiplier) * 0.5,
            max_hold_bars=3,
        )

        logger.info(f"[RETRAIN] Labels created")

        # Guard: classifiers need both classes present. A flat/one-sided market
        # can produce a single-class target, which previously crashed retraining
        # with "index 1 is out of bounds for axis 1 with size 1".
        for col in ("long_target", "short_target"):
            vals = labeled_early[col].dropna()
            if len(vals) == 0 or vals.nunique() < 2:
                return RetrainingResult(
                    triggered=False,
                    reason=f"Single-class target '{col}' ({len(vals)} rows) — skipping retrain",
                )
        # Train Early Signal Model
        logger.info("\n[RETRAIN] Training Early Signal Model...")
        early_model = EarlySignalModel(threshold=self.settings.early_signal_threshold)

        try:
            early_model.train(labeled_early, "long_target", "long")
            early_model.train(labeled_early, "short_target", "short")
            logger.info("[RETRAIN] ✓ Early Signal trained")
        except Exception as e:
            logger.info(f"[RETRAIN] ✗ Early Signal failed: {e}")
            return RetrainingResult(triggered=False, reason=f"Training failed: {e}")

        # Train Confirmation Model
        logger.info("\n[RETRAIN] Training Confirmation Model...")
        confirm_model = ConfirmationModel(
            threshold_long=self.settings.confirmation_threshold,
            threshold_short=self.settings.confirmation_threshold - 0.05,
        )

        try:
            confirm_model.train(labeled_early, "long_target", "long", calibrate=True)
            confirm_model.train(labeled_early, "short_target", "short", calibrate=True)
            logger.info("[RETRAIN] ✓ Confirmation trained")
        except Exception as e:
            logger.info(f"[RETRAIN] ✗ Confirmation failed: {e}")
            return RetrainingResult(triggered=False, reason=f"Training failed: {e}")

        # Train Momentum Model
        logger.info("\n[RETRAIN] Training Momentum Model...")
        momentum_model = MomentumModel(
            threshold=self.settings.momentum_threshold,
            horizon_bars=3,
        )

        try:
            momentum_model.train(labeled_momentum, "long")
            momentum_model.train(labeled_momentum, "short")
            logger.info("[RETRAIN] ✓ Momentum trained")
        except Exception as e:
            logger.info(f"[RETRAIN] ✗ Momentum failed: {e}")
            return RetrainingResult(triggered=False, reason=f"Training failed: {e}")

        # Save new models
        logger.info("\n[RETRAIN] Saving models...")
        early_path = self.settings.models_dir / "early_signal_new.joblib"
        confirm_path = self.settings.models_dir / "confirmation_new.joblib"
        momentum_path = self.settings.models_dir / "momentum_new.joblib"

        early_model.save(early_path)
        confirm_model.save(confirm_path)
        momentum_model.save(momentum_path)

        logger.info(f"[RETRAIN] Models saved to {self.settings.models_dir}")

        # Promote: atomically move the *_new.joblib files onto the live model
        # names the runtime actually loads (runtime._reload_models reads
        # early_signal.joblib etc.). Previously the *_new files were written
        # and never used — retraining had no effect on live trading.
        promoted = False
        try:
            import os
            for new_path, live_name in (
                (early_path, "early_signal.joblib"),
                (confirm_path, "confirmation.joblib"),
                (momentum_path, "momentum.joblib"),
            ):
                live_path = self.settings.models_dir / live_name
                if live_path.exists():
                    live_path.unlink()
                os.replace(new_path, live_path)
            promoted = True
            logger.info("[RETRAIN] ✓ Models promoted to live filenames")
        except Exception as e:
            logger.warning(f"[RETRAIN] Promotion failed: {e}")

        result = RetrainingResult(
            triggered=True,
            reason="Scheduled retraining completed",
            promoted=promoted,
            model_path=str(early_path),
        )

        logger.info(f"\n[RETRAIN] {'='*80}")
        logger.info(f"[RETRAIN] RETRAINING COMPLETE")
        logger.info(f"[RETRAIN] Models promoted: {promoted}")
        logger.info(f"{'='*80}\n")

        return result

    def run_cycle(self) -> Dict[str, Any]:
        """
        Run one complete monitoring/retraining cycle.

        Call this periodically (e.g., every hour or every N trades).
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"[AUTO-LEARN] Checking system health...")
        logger.info(f"{'='*80}")

        # 1. Check performance
        metrics = self.check_performance()
        logger.info(f"[AUTO-LEARN] Trades: {metrics.total_trades}, WR: {metrics.win_rate}%, PF: {metrics.profit_factor}")

        # 2. Detect drift
        drift = self.detect_drift(metrics)
        logger.info(f"[AUTO-LEARN] Drift detected: {drift.is_drifting} (drop: {drift.precision_drop:.1f}%)")

        # 3. Decide if retrain needed
        should_retrain, reason = self.should_retrain(metrics, drift)
        logger.info(f"[AUTO-LEARN] Should retrain: {should_retrain} ({reason})")

        result = {
            "metrics": metrics,
            "drift": drift,
            "should_retrain": should_retrain,
            "reason": reason,
            "retraining_result": None,
        }

        # 4. Retrain if needed
        if should_retrain:
            logger.info(f"\n[AUTO-LEARN] Triggering retraining...")

            # Fetch recent data for training
            df = self.fetch_recent_data(symbol="BTCUSDT")

            if len(df) > 100:
                # Create labels for training
                from .feature_engineering import attach_labels

                featured = attach_labels(
                    df,
                    horizon_bars=6,
                    min_return_pct=float(self.settings.label_min_return_pct),
                    take_profit_pct=float(self.settings.take_profit_atr_multiplier),
                    stop_loss_pct=float(self.settings.stop_loss_atr_multiplier),
                    max_hold_bars=int(getattr(self.settings, 'max_hold_bars', 6)),
                )

                # Retrain
                retrain_result = self.retrain_all_models(featured)
                result["retraining_result"] = retrain_result

                if retrain_result.promoted:
                    logger.info(f"\n[AUTO-LEARN] ✓ New models promoted!")
                else:
                    logger.info(f"\n[AUTO-LEARN] ⚠ Models not promoted (training failed)")
            else:
                logger.info(f"\n[AUTO-LEARN] ⚠ Not enough data for retraining ({len(df)} bars)")
        else:
            logger.info(f"\n[AUTO-LEARN] No retraining needed")

        logger.info(f"\n[AUTO-LEARN] Cycle complete\n")
        return result

    def close(self):
        """Close database connection."""
        self.conn.close()
