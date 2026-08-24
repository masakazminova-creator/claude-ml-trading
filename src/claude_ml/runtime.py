"""
Complete runtime orchestrator for Claude ML Trading System.

Integrates:
- Multi-model ensemble (early + confirmation + momentum)
- Two-stage entry system
- Dynamic position sizing via risk manager
- Continuous learning pipeline
- Production safety checks
"""

from __future__ import annotations

import json
import logging
import requests
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .config import Settings
from .data_collector import make_collector
from .feature_engineering import build_features
from .regime_detector import classify_regime
from .notifier import TelegramNotifier
from .ensemble import EnsembleEngine
from .risk_manager import RiskManager
from .continuous_learning import ContinuousLearningEngine
from .adaptive_thresholds import AdaptiveThresholdEngine
from .signal_audit import SignalAuditEngine
from .trailing_stop import TrailingStopState, create_trailing_stop, update_trailing_stop, check_trailing_stop_exit, check_fixed_sl_exit
from .feature_importance import OnlineFeatureSelector
from .multi_timeframe import MultiTimeframeAnalyzer
from .regime_models import ExpertRouter, RegimeClassification
from .atr_percentile import ATRPercentileAnalyzer
from .models.early_signal import EarlySignalModel
from .models.confirmation import ConfirmationModel
from .models.momentum import MomentumModel

# Module logger
logger = logging.getLogger(__name__)


def format_time_moscow(ts_str):
    """Convert UTC timestamp to Moscow time (UTC+3)."""
    if not ts_str:
        return 'N/A'
    try:
        from datetime import datetime, timezone, timedelta
        # Parse ISO format string
        utc_dt = datetime.fromisoformat(str(ts_str).replace('+00:00', ''))
        # Convert to Moscow time (UTC+3)
        moscow_tz = timezone(timedelta(hours=3))
        moscow_dt = utc_dt.replace(tzinfo=timezone.utc).astimezone(moscow_tz)
        return moscow_dt.strftime('%Y-%m-%d %H:%M:%S') + ' MSK'
    except Exception as e:
        return str(ts_str)[:19] + ' UTC'


class RuntimeEngine:
    """Complete runtime with full ensemble and risk management."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_dirs()

        # Validate configuration
        errors = self.settings.validate()
        if errors:
            raise ValueError(f"Configuration errors: {'; '.join(errors)}")

        # Initialize data collectors (one per symbol, using OKX by default)
        from .data_collector import OKXCollector
        self.collectors = {}
        for symbol in settings.symbols:
            # Map symbol to OKX instrument ID
            inst_id = f"{symbol.replace('USDT', '')}-USDT-SWAP"
            self.collectors[symbol] = OKXCollector(
                base_url=settings.okx_base_url,
                inst_id=inst_id
            )

        # Initialize notifier
        self.notifier = TelegramNotifier(
            settings.telegram_bot_token,
            settings.telegram_chat_id
        )

        # Initialize multi-timeframe analyzer (Phase 3) - one per symbol
        self.mtf_analyzers: Dict[str, MultiTimeframeAnalyzer] = {}
        for symbol in settings.symbols:
            self.mtf_analyzers[symbol] = MultiTimeframeAnalyzer(symbol=symbol)

        # Initialize expert router (Phase 5) - regime-specific models
        self.expert_router = ExpertRouter()

        # Load models (if available)
        self.early_model = self._load_early_model()
        self.confirmation_model = self._load_confirmation_model()
        self.momentum_model = self._load_momentum_model()

        # Initialize ensemble engine (only if all models loaded)
        self.ensemble: Optional[EnsembleEngine] = None
        if all(m is not None for m in [self.early_model, self.confirmation_model, self.momentum_model]):
            self.ensemble = EnsembleEngine(
                early_model=self.early_model,
                confirmation_model=self.confirmation_model,
                momentum_model=self.momentum_model,
            )
            logger.info("All models loaded successfully")
        else:
            logger.warning("Running in data-only mode (no models)")

        # Initialize risk manager
        self.risk_manager = RiskManager(settings)

        # Initialize database FIRST (before other engines that need DB).
        # check_same_thread=False so the fast stop-checker thread can use it too.
        self.conn = sqlite3.connect(settings.runtime_db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

        # Thread-safety for the fast stop-checker (shares trailing_stops + DB with main cycle)
        self._stop_lock = threading.Lock()
        self._shutdown = threading.Event()
        self._stop_thread: Optional[threading.Thread] = None

        # Initialize continuous learning engine
        self.learning_engine = ContinuousLearningEngine(settings)
        self.last_retrain_check = 0
        self.retrain_check_interval = 50  # Check every 50 trades

        # Initialize adaptive threshold engine
        self.threshold_engine = AdaptiveThresholdEngine(settings)

        # Initialize signal audit engine
        self.audit_engine = SignalAuditEngine(settings)

        # Trailing stops tracker (symbol -> TrailingStopState)
        self.trailing_stops: Dict[str, TrailingStopState] = {}

        # Restore trailing stops from database on startup
        self._restore_trailing_stops_from_db()

        # Circuit breaker state
        self.trading_paused = False
        self.pause_reason = ""
        self.emergency_stop_triggered = False

        # Initialize online feature selector (Phase 2)
        self.feature_selector = OnlineFeatureSelector(
            rolling_window=50,
            min_correlation=0.05,
            max_noise_ratio=2.0,
            update_interval_bars=10,
        )

        # Initialize ATR Percentile Analyzer (replaces absolute ATR filter)
        self.atr_analyzer = ATRPercentileAnalyzer(window_size=200)

        # Runtime state
        self.error_streak = 0
        self.last_candle_time = {}
        self.stage_tracker = {}  # symbol -> current stage ('stage_1' or 'stage_2')

    def _restore_trailing_stops_from_db(self) -> None:
        """Restore trailing stops for open positions from database on startup."""
        logger.info("Restoring trailing stops from database...")
        print("DEBUG: Restoring trailing stops...")

        try:
            # Get all open positions
            cursor = self.conn.execute("""
                SELECT id, symbol, side, entry_price, payload_json
                FROM paper_trades
                WHERE status = 'open'
            """)

            restored_count = 0
            for row in cursor.fetchall():
                trade_id, symbol, side, entry_price, payload_json = row
                payload = json.loads(payload_json) if payload_json else {}

                # Extract ATR from payload or use default (stored as ratio, not percentage)
                atr_ratio = float(payload.get('atr_pct', 0.0025))
                atr = atr_ratio * entry_price  # Convert ratio to absolute value

                # Calculate TP/SL levels (same as when position was created)
                tp_level = entry_price + (atr * 2.5) if side == "long" else entry_price - (atr * 2.5)
                sl_level = entry_price - (atr * 2.0) if side == "long" else entry_price + (atr * 2.0)

                # Create trailing stop state
                trailing_state = create_trailing_stop(
                    symbol=symbol,
                    side=side,
                    entry_price=entry_price,
                    atr=atr,
                    tp_level=tp_level,
                    sl_level=sl_level,
                    trigger_mult=(abs(tp_level - entry_price)) / atr,
                    stop_mult=1.5,
                    trailing_pct=self.settings.trailing_stop_pct,
                )

                self.trailing_stops[symbol] = trailing_state
                logger.info(f"  Restored trailing stop for {symbol} #{trade_id} ({side}, entry={entry_price:.2f})")
                restored_count += 1

            if restored_count > 0:
                logger.info(f"Restored {restored_count} trailing stop(s) from database")
                print(f"DEBUG: Restored {restored_count} trailing stops")
            else:
                logger.info("No open positions to restore trailing stops for")
                print("DEBUG: No open positions found")

        except Exception as e:
            logger.error(f"Failed to restore trailing stops: {e}", exc_info=True)
            print(f"DEBUG: Restore failed with error: {e}")

    def _load_early_model(self) -> Optional[EarlySignalModel]:
        """Load early signal model."""
        path = self.settings.models_dir / "early_signal.joblib"
        if path.exists():
            try:
                return EarlySignalModel.load(path)
            except Exception as e:
                logger.warning(f"Failed to load early model: {e}")
                return None
        return None

    def _load_confirmation_model(self) -> Optional[ConfirmationModel]:
        """Load confirmation model."""
        path = self.settings.models_dir / "confirmation.joblib"
        if path.exists():
            try:
                return ConfirmationModel.load(path)
            except Exception as e:
                logger.warning(f"Failed to load confirmation model: {e}")
                return None
        return None

    def _load_momentum_model(self) -> Optional[MomentumModel]:
        """Load momentum model."""
        path = self.settings.models_dir / "momentum.joblib"
        if path.exists():
            try:
                return MomentumModel.load(path)
            except Exception as e:
                logger.warning(f"Failed to load momentum model: {e}")
                return None
        return None

    def _create_tables(self) -> None:
        """Create required database tables."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                close_price REAL NOT NULL,
                probability REAL NOT NULL,
                model_type TEXT NOT NULL,
                stage TEXT,
                payload_json TEXT NOT NULL
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_ts TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stage TEXT NOT NULL,
                signal_probability REAL NOT NULL,
                take_profit_pct REAL NOT NULL,
                stop_loss_pct REAL NOT NULL,
                status TEXT NOT NULL,
                exit_ts TEXT,
                exit_price REAL,
                exit_reason TEXT,
                pnl_pct REAL,
                hold_bars INTEGER,
                payload_json TEXT NOT NULL
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS equity_curve (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                balance REAL NOT NULL,
                trade_id INTEGER,
                pnl_pct REAL
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS health_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                status TEXT NOT NULL,
                error_streak INTEGER NOT NULL,
                note TEXT
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS model_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                decision TEXT NOT NULL,
                side TEXT,
                early_score REAL,
                confirmation_score REAL,
                momentum_direction TEXT,
                regime TEXT,
                confidence REAL,
                action TEXT,
                position_size_pct REAL,
                reasoning TEXT,
                payload_json TEXT NOT NULL
            )
        """)

        # Table for adaptive thresholds state
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS runtime_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Note: signal_audit_log table is created by SignalAuditEngine
        # We use it to log ALL decisions (ENTER, SKIP, WAIT)

        self.conn.commit()

    def run(self) -> None:
        """Main runtime loop."""

        logger.info("Claude ML Trading System - Starting...")
        logger.info(f"Mode: {self.settings.mode.upper()}, Symbols: {', '.join(self.settings.symbols)}")
        logger.info(f"Timeframe: {self.settings.timeframe}m, Poll: {self.settings.poll_seconds}s")

        cycle_count = 0

        # Start the fast stop-checker thread (~every stop_check_interval_seconds),
        # which reacts to stop levels near real-time, independent of the 15m cycle.
        self._stop_thread = threading.Thread(
            target=self._stop_check_loop, name="stop-checker", daemon=True
        )
        self._stop_thread.start()

        try:
            while True:
                try:
                    cycle_count += 1
                    logger.debug(f"=== CYCLE #{cycle_count} ===")
                    self._poll_cycle()
                    logger.debug(f"Sleeping for {self.settings.poll_seconds}s...")
                    time.sleep(self.settings.poll_seconds)
                except KeyboardInterrupt:
                    logger.info("Shutdown requested by user")
                    break
                except Exception as e:
                    self.error_streak += 1
                    logger.error(f"Error in poll cycle (streak={self.error_streak}): {e}", exc_info=True)

                    if self.error_streak >= self.settings.max_error_streak:
                        self._log_health("error", f"Max error streak reached: {e}")
                        logger.critical(f"Max error streak ({self.settings.max_error_streak}) reached. Pausing.")
                        break
        finally:
            self._shutdown.set()
            self.conn.close()
            logger.info("Runtime stopped")

    def _poll_cycle(self) -> None:
        """Single polling cycle for all symbols."""

        logger.debug(f"POLL CYCLE STARTED at {datetime.now(timezone.utc).strftime('%H:%M:%S')}")

        # CIRCUIT BREAKER CHECK
        if self.trading_paused:
            logger.info(f"TRADING PAUSED: {self.pause_reason}")
            logger.info("Checking performance and attempting retrain...")

            # Try to retrain to fix the issue
            self._check_and_retrain()

            # If retrain helped, resume
            if not self.emergency_stop_triggered:
                metrics = self.learning_engine.check_performance()
                emergency, reason = self.learning_engine.check_emergency_stop(metrics)

                if not emergency:
                    self.trading_paused = False
                    self.pause_reason = ""
                    logger.info("Issue resolved, resuming trading")
                else:
                    logger.info(f"Still paused, issue persists: {reason}")
            return

        # Check if retraining needed (every N cycles)
        self.last_retrain_check += 1
        if self.last_retrain_check >= self.retrain_check_interval:
            self.last_retrain_check = 0
            self._check_and_retrain()

        for symbol in self.settings.symbols:
            try:
                self._process_symbol(symbol)
            except Exception as e:
                logger.error(f"Processing {symbol}: {e}", exc_info=True)
                continue

        # Log health
        logger.debug("Poll cycle complete, logging health...")
        self._log_health("ok", f"Processed {len(self.settings.symbols)} symbols")
        logger.debug("Health logged")

        # Save adaptive thresholds state
        self.threshold_engine.save_state()

    def _check_and_retrain(self) -> None:
        """Check performance and retrain models if needed."""
        logger.info("=== AUTOMATIC LEARNING CHECK ===")
        try:
            result = self.learning_engine.run_cycle()

            # Check for emergency stop
            metrics = result.get("metrics")
            if metrics:
                emergency, reason = self.learning_engine.check_emergency_stop(metrics)

                if emergency:
                    logger.critical("EMERGENCY STOP TRIGGERED!")
                    logger.critical(f"Reason: {reason}")
                    logger.critical("Trading paused until fixed")

                    self.trading_paused = True
                    self.pause_reason = reason
                    self.emergency_stop_triggered = True

                    # Still try to retrain to fix the issue
                    if result.get("should_retrain"):
                        logger.info("Attempting emergency retrain...")
                        if result.get("retraining_result"):
                            if result["retraining_result"].promoted:
                                logger.info("Emergency retrain completed, models updated")
                                self._reload_models()

                                # Check if issue resolved
                                new_metrics = self.learning_engine.check_performance()
                                new_emergency, _ = self.learning_engine.check_emergency_stop(new_metrics)
                                if not new_emergency:
                                    logger.info("Issue resolved! Resuming trading")
                                    self.trading_paused = False
                                    self.emergency_stop_triggered = False
                                    self.pause_reason = ""
                                else:
                                    logger.warning("Issue persists after retrain")
                            else:
                                logger.error("Emergency retrain failed")
                    return

            # Normal retraining flow
            if result.get("should_retrain"):
                logger.info("Retraining triggered!")
                if result.get("retraining_result"):
                    if result["retraining_result"].promoted:
                        logger.info("Models updated successfully!")
                        # Reload models in ensemble
                        self._reload_models()
                    else:
                        logger.warning("Training failed, keeping old models")
            else:
                logger.info("No retraining needed")

        except Exception as e:
            logger.error(f"Error in learning check: {e}", exc_info=True)

    def _reload_models(self) -> None:
        """Reload models after retraining."""
        logger.info("Reloading models...")
        try:
            self.early_model = self._load_early_model()
            self.confirmation_model = self._load_confirmation_model()
            self.momentum_model = self._load_momentum_model()

            if all([self.early_model, self.confirmation_model, self.momentum_model]):
                self.ensemble = EnsembleEngine(
                    early_model=self.early_model,
                    confirmation_model=self.confirmation_model,
                    momentum_model=self.momentum_model,
                )
                logger.info("Models reloaded successfully")
            else:
                logger.warning("Some models failed to reload")
        except Exception as e:
            logger.error(f"Error reloading models: {e}", exc_info=True)

    def _process_symbol(self, symbol: str) -> None:
        """Process single symbol: fetch data, build features, run ensemble."""
        logger.info(f"=== Processing {symbol} ===")
        logger.debug(f"Processing {symbol}...")

        try:
            collector = self.collectors[symbol]
            logger.debug(f"Collector ready for {symbol}")
        except Exception as e:
            logger.error(f"Failed to get collector for {symbol}: {e}")
            return

        # Fetch latest candles
        logger.debug(f"Fetching data for {symbol}...")
        try:
            df = collector.fetch_history(
                symbol=symbol,
                interval=self.settings.timeframe,
                lookback_bars=200
            )
            logger.debug(f"Fetched {len(df)} candles for {symbol}")
        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}", exc_info=True)
            return

        if df.empty:
            logger.warning(f"Empty data for {symbol}")
            return  # Don't raise, just skip to next symbol

        # Build features (includes early detection features)
        logger.debug(f"Building features for {symbol}...")
        try:
            featured = build_features(df)
            logger.debug(f"Built {len(featured.columns)} features, {len(featured)} rows")
        except Exception as e:
            logger.error(f"Failed to build features for {symbol}: {e}", exc_info=True)
            return

        if featured.empty:
            logger.warning(f"Empty features for {symbol}")
            return  # Don't raise, just skip to next symbol

        # Classify regime
        logger.debug(f"Classifying regime for {symbol}...")
        try:
            regime = classify_regime(featured.iloc[-1])
            regime_name = regime.get('structure_regime', 'unknown')
            logger.debug(f"Regime for {symbol}: {regime_name}")
        except Exception as e:
            logger.error(f"Failed to classify regime for {symbol}: {e}", exc_info=True)
            return

        # Update online feature importance (Phase 2)
        try:
            active_features = self.feature_selector.update_feature_importance(
                df=featured,
                target_column="long_target",
            )
            if active_features:
                logger.debug(f"[{symbol}] Active features: {len(active_features)}")
        except Exception as e:
            logger.warning(f"Feature selector update failed for {symbol}: {e}")

        # Check if candle is fresh
        latest_ts = featured["ts"].iloc[-1]
        if not self._is_candle_fresh(latest_ts, symbol):
            return

        # Phase 5: Get current regime classification from expert router
        try:
            regime_class = self.expert_router.get_current_regime(featured)
            logger.debug(f"[{symbol}] Regime: {regime_class.primary_regime} (confidence={regime_class.confidence:.2f})")
        except Exception as e:
            logger.warning(f"Regime detection failed for {symbol}: {e}")
            regime_class = None

        # Get latest row
        latest_row = featured.iloc[-1]
        close_price = float(latest_row["close"])
        atr_ratio = float(latest_row.get("atr_pct_14", 0.005))  # ATR as ratio (not percentage)
        atr = atr_ratio * close_price  # Convert ratio to absolute value

        # Check trailing stop for existing position
        if symbol in self.trailing_stops:
            trailing_state = self.trailing_stops[symbol]

            # Intrabar extremes used so stops trigger on a wick through the
            # level, not only when the bar CLOSES beyond it
            bar_low = float(latest_row["low"]) if pd.notna(latest_row.get("low")) else None
            bar_high = float(latest_row["high"]) if pd.notna(latest_row.get("high")) else None

            # Check fixed stop loss BEFORE trailing activation
            sl_hit, sl_reason = check_fixed_sl_exit(trailing_state, close_price, bar_low=bar_low, bar_high=bar_high)

            if sl_hit:
                # Exit fills at the SL level (not the bar close), capping loss at SL
                sl_exit_price = float(trailing_state.initial_sl) if trailing_state.initial_sl else close_price
                self._close_position(
                    symbol, trailing_state, sl_exit_price,
                    exit_reason="fixed_stop_loss", title="STOP LOSS HIT",
                    reason_label="Fixed Stop Loss", level_label="SL Level",
                    exit_ts=latest_ts.isoformat(), reason_detail=sl_reason,
                )
                return  # Skip signal generation

            # Update trailing stop with new price
            trailing_state = update_trailing_stop(
                state=trailing_state,
                current_price=close_price,
                atr=atr,
            )
            self.trailing_stops[symbol] = trailing_state

            # Check if trailing stop hit (intrabar extreme, fills at stop level)
            trail_hit = check_trailing_stop_exit(trailing_state, close_price, bar_low=bar_low, bar_high=bar_high)
            if trail_hit:
                # Exit fills at the trailing stop level (not the bar close)
                trail_exit_price = float(trailing_state.current_stop_price)
                self._close_position(
                    symbol, trailing_state, trail_exit_price,
                    exit_reason="trailing_stop", title="TRADE CLOSED",
                    reason_label="Trailing Stop Hit", level_label="Stop Level",
                    exit_ts=latest_ts.isoformat(),
                )
                return  # Skip signal generation for this bar

        # Get adaptive thresholds for this symbol and regime
        atr_pct_for_thresholds = atr_ratio * 100  # Convert ratio to percentage for threshold engine
        early_thresh = self.threshold_engine.get_adaptive_threshold(
            symbol=symbol,
            regime=regime_name,
            atr_pct=atr_pct_for_thresholds,
            threshold_type="early_signal"
        )
        confirm_thresh = self.threshold_engine.get_adaptive_threshold(
            symbol=symbol,
            regime=regime_name,
            atr_pct=atr_pct_for_thresholds,
            threshold_type="confirmation"
        )
        momentum_thresh = self.threshold_engine.get_adaptive_threshold(
            symbol=symbol,
            regime=regime_name,
            atr_pct=atr_pct_for_thresholds,
            threshold_type="momentum"
        )

        logger.debug(f"[ADAPTIVE] {symbol} thresholds: early={early_thresh:.3f}, confirm={confirm_thresh:.3f}, momentum={momentum_thresh:.3f}")

        # Run ensemble if available (pass adaptive thresholds)
        if self.ensemble:
            # Temporarily override settings with adaptive thresholds
            old_early = self.ensemble.early_model.threshold
            old_confirm = self.ensemble.confirmation_model.threshold_long
            old_momentum = self.ensemble.momentum_model.threshold

            self.ensemble.early_model.threshold = early_thresh
            self.ensemble.confirmation_model.threshold_long = confirm_thresh
            self.ensemble.momentum_model.threshold = momentum_thresh

            decision = self.ensemble.evaluate(latest_row, regime=regime_name, stage="full")

            # Restore original thresholds
            self.ensemble.early_model.threshold = old_early
            self.ensemble.confirmation_model.threshold_long = old_confirm
            self.ensemble.momentum_model.threshold = old_momentum

            if decision:
                print(f"[{symbol}] {decision.action.upper()} | Side: {decision.side} | "
                      f"Confidence: {decision.confidence:.0f}% | Size: {decision.position_size_pct*100:.0f}%")
                print(f"         Reasoning: {'; '.join(decision.reasoning[:3])}")

                # Log ALL decisions to signal_audit table (including SKIP/WAIT)
                self._log_all_decisions(
                    ts=latest_ts,
                    symbol=symbol,
                    close_price=close_price,
                    atr_pct=atr_ratio * 100,  # Convert ratio to percentage for logging
                    regime=regime_name,
                    early_prob=decision.early_result.score if decision.early_result else 0,
                    confirm_prob=decision.confirmation_result.score if decision.confirmation_result else 0,
                    momentum_score=decision.momentum_result.score if decision.momentum_result else 0,
                    adaptive_early_thresh=early_thresh,
                    adaptive_confirm_thresh=confirm_thresh,
                    adaptive_momentum_thresh=momentum_thresh,
                    action=decision.action.lower(),
                    confidence=decision.confidence,
                    position_size_pct=decision.position_size_pct,
                    reasoning="; ".join(decision.reasoning[:3]) if decision.reasoning else "No signals",
                )
            else:
                # Decision is None - log as SKIP with all scores at 0
                logger.info(f"[{symbol}] SKIP | No ensemble decision (all models below thresholds)")
                self._log_all_decisions(
                    ts=latest_ts,
                    symbol=symbol,
                    close_price=close_price,
                    atr_pct=atr_ratio * 100,  # Convert ratio to percentage for logging
                    regime=regime_name,
                    early_prob=0,
                    confirm_prob=0,
                    momentum_score=0,
                    adaptive_early_thresh=early_thresh,
                    adaptive_confirm_thresh=confirm_thresh,
                    adaptive_momentum_thresh=momentum_thresh,
                    action="skip",
                    confidence=0,
                    position_size_pct=0,
                    reasoning="Ensemble returned None - all models below thresholds",
                )

        # Calculate position size via risk manager (for ENTER decisions only)
        if decision and decision.action.upper().startswith("ENTER"):
            # NEW: RELATIVE ATR ANALYSIS (replaces absolute filter)
            atr_pct_value = atr_ratio * 100  # Convert ratio to percentage
            atr_result = self.atr_analyzer.analyze(symbol, atr_pct_value)

            logger.info(f"[{symbol}] ATR: {atr_pct_value:.3f}% (percentile: {atr_result.percentile_30d:.1f}%, compressed: {atr_result.is_compressed}, breakout_setup: {atr_result.is_breakout_setup})")

            # Skip only in EXTREME compression (bottom 10% of history)
            if atr_result.recommended_action == 'skip':
                logger.info(f"[{symbol}] ⏸️ ATR extreme compression (percentile {atr_result.percentile_30d:.1f}%), skipping entry")
                return

            # NEW: Check signal_audit_log for key level context (prevent bad entries)
            # For LONG: skip if 2+ of last 3 signals show at_resistance
            # For SHORT: skip if 2+ of last 3 signals show at_support
            try:
                recent_signals = self.conn.execute("""
                    SELECT action_reason FROM signal_audit_log
                    WHERE ts <= ? AND action LIKE '%enter%'
                    ORDER BY ts DESC LIMIT 3
                """, (latest_ts.isoformat(),)).fetchall()

                if decision.side == "long":
                    # Check for resistance (bad for long)
                    bad_level_count = sum(1 for s in recent_signals if s[0] and 'at_resistance' in s[0])
                    level_name = "resistance"
                else:  # short
                    # Check for support (bad for short)
                    bad_level_count = sum(1 for s in recent_signals if s[0] and 'at_support' in s[0])
                    level_name = "support"

                if bad_level_count >= 2:
                    logger.info(f"[{symbol}] ⏸️ Bad level warning: {bad_level_count}/3 recent signals show at_{level_name}, skipping {decision.side} entry")
                    return
            except Exception as e:
                logger.warning(f"Failed to check signal_audit_log for bad levels: {e}")
                # Allow trade to proceed if check fails

            # Apply ATR bonus to evidence score (breakout detection)
            # This is the KEY improvement: catch breakouts from compression
            if atr_result.is_breakout_setup:
                # Boost confidence for breakout setups
                decision.confidence = min(100.0, decision.confidence * atr_result.bonus_multiplier)
                decision.position_size_pct = min(1.0, decision.position_size_pct * atr_result.bonus_multiplier)
                logger.info(f"[{symbol}] ✅ Breakout setup detected! Confidence boosted x{atr_result.bonus_multiplier:.2f}")

            # Also apply bonus at ensemble level if decision hasn't been finalized yet
            # (This is handled inside ensemble.py via MarketContext)

            # Phase 3: CHECK MULTI-TIMEFRAME ALIGNMENT
            try:
                mtf_analyzer = self.mtf_analyzers.get(symbol)
                if mtf_analyzer:
                    alignment = mtf_analyzer.check_alignment()
                    if not alignment.entry_allowed:
                        logger.info(f"[{symbol}] ⏸️ Multi-timeframe blocked: {alignment.reasoning}")
                        return  # Skip entry when timeframes don't align
                    else:
                        logger.info(f"[{symbol}] ✅ MTF aligned: {alignment.reasoning} (score={alignment.alignment_score:.2f})")
            except Exception as e:
                logger.warning(f"Multi-timeframe check failed for {symbol}: {e}")
                # Allow trade to proceed if MTF check fails (don't block on errors)

            # CHECK IF POSITION ALREADY EXISTS - PREVENT DUPLICATE SIGNALS
            existing_position = self.conn.execute("""
                SELECT id FROM paper_trades
                WHERE symbol = ? AND status = 'open'
                ORDER BY id DESC LIMIT 1
            """, (symbol,)).fetchone()

            if existing_position:
                logger.info(f"[{symbol}] ⏸️ Position already open (id={existing_position[0]}), skipping duplicate signal")
                return  # Skip this cycle - already in position

            risk_result = self.risk_manager.calculate_position_size(
                symbol=symbol,
                entry_price=close_price,
                atr=atr,
                regime=regime_name,
                model_confidence=decision.confidence / 100,
                side=decision.side,
            )

            logger.info(f"         Emergency SL: {risk_result.stop_loss_price:.4f} | Trailing Stop Active")
            logger.info(f"         Risk: ${risk_result.risk_amount:.2f}")

            # CREATE PAPER TRADE RECORD (no fixed TP/SL - trailing stop only)
            payload = {
                "confidence": decision.confidence,
                "regime": regime_name,
                "atr_pct": atr_ratio,  # Store as ratio for internal use
                "reasoning": decision.reasoning[:3],
                "exit_strategy": "trailing_stop_only"
            }
            self.conn.execute("""
                INSERT INTO paper_trades (
                    symbol, side, entry_ts, entry_price, stage,
                    signal_probability, take_profit_pct, stop_loss_pct,
                    payload_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, 0), COALESCE(?, 0), ?, 'open')
            """, (
                symbol, decision.side, latest_ts.isoformat(), close_price,
                'full', decision.confidence / 100,
                None, None,  # No fixed TP/SL - will use 0 as default
                json.dumps(payload)
            ))
            trade_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            logger.info(f"[{symbol}] Paper trade #{trade_id} created - trailing stop exit strategy")

            # Create ATR-based trailing stop that activates AT TAKE PROFIT level
            tp_level = risk_result.take_profit_price if risk_result.take_profit_price else close_price + (atr * 2.5)
            sl_level = risk_result.stop_loss_price if risk_result.stop_loss_price else None

            trailing_state = create_trailing_stop(
                symbol=symbol,
                side=decision.side,
                entry_price=close_price,
                atr=atr,
                tp_level=tp_level,
                sl_level=sl_level,
                trigger_mult=(tp_level - close_price) / atr,  # Activate at TP level
                stop_mult=1.5,     # Stop at 1.5 ATR distance from max (capped by trailing_stop_pct)
                trailing_pct=self.settings.trailing_stop_pct,
            )
            self.trailing_stops[symbol] = trailing_state
            logger.info(f"         Trailing stop created (activates at TP: ${tp_level:.2f}, fixed SL: ${sl_level})")

            # Send Telegram notification for entry
            try:
                entry_time_str = format_time_moscow(latest_ts.isoformat())
                entry_msg = (
                    f"🔔 *NEW TRADE ENTRY*\n\n"
                    f"📋 *Trade ID: #{trade_id}*\n"
                    f"Symbol: `{symbol}`\n"
                    f"Side: *{decision.side.upper()}*\n"
                    f"Entry Price: `${close_price:.2f}`\n"
                    f"⏰ Entry Time: `{entry_time_str}`\n\n"
                    f"Confidence: `{decision.confidence:.0f}%`\n"
                    f"Position Size: `{risk_result.adjusted_size_pct:.1f}%`\n\n"
                    f"Take Profit: `${risk_result.take_profit_price:.2f}`\n"
                    f"Stop Loss: `${risk_result.stop_loss_price:.2f}`\n"
                    f"Trailing Stop: `${trailing_state.current_stop_price:.2f}`\n\n"
                    f"Regime: `{regime_name}`\n"
                    f"Reasoning: {'; '.join(decision.reasoning[:3])}"
                )
                url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
                data = {
                    "chat_id": self.settings.telegram_chat_id,
                    "text": entry_msg,
                    "parse_mode": "Markdown"
                }
                response = requests.post(url, json=data, timeout=10)
                if response.status_code == 200:
                    logger.info("Telegram entry notification sent")
                else:
                    logger.warning(f"Telegram API error: {response.text}")
            except Exception as e:
                logger.warning(f"Failed to send Telegram entry notification: {e}")

            # Log decision (original method)
            self._log_decision(
                ts=latest_ts,
                symbol=symbol,
                decision=decision,
                regime=regime_name,
                risk_result=risk_result,
            )

            # Audit log with full context
            self._audit_log_decision(
                ts=latest_ts,
                symbol=symbol,
                close_price=close_price,
                atr_pct=(atr_ratio * 100) if close_price > 0 else 0.5,  # Convert to percentage for logging
                regime=regime_name,
                decision=decision,
                featured=featured,
            )

        else:
            # Data-only mode
            print(f"[{symbol}] Regime: {regime_name}, Price: {close_price:.4f}")

    def _close_position(
        self,
        symbol: str,
        trailing_state: TrailingStopState,
        exit_price: float,
        exit_reason: str,
        title: str,
        reason_label: str,
        level_label: str,
        exit_ts: Optional[str] = None,
        reason_detail: str = "",
    ) -> bool:
        """Close an open position at the given exit price.

        Thread-safe: usable from both the main poll cycle and the fast stop-checker
        thread. The UPDATE only matches rows with status='open', so the first caller
        wins; any second caller (e.g. a race between the two threads) gets rowcount=0
        and returns False — preventing double-close and duplicate Telegram alerts.
        """
        with self._stop_lock:
            if exit_ts is None:
                exit_ts = datetime.now(timezone.utc).isoformat()

            raw_pnl_pct = ((exit_price - trailing_state.entry_price) / trailing_state.entry_price * 100)
            total_cost_bps = self.settings.fee_bps * 2 + self.settings.slippage_bps * 2
            cost_pct = total_cost_bps / 100
            net_pnl_pct = raw_pnl_pct - cost_pct

            cur = self.conn.execute("""
                UPDATE paper_trades
                SET status = 'closed',
                    exit_ts = ?,
                    exit_price = ?,
                    pnl_pct = ?,
                    exit_reason = ?
                WHERE symbol = ? AND status = 'open'
            """, (exit_ts, exit_price, net_pnl_pct, exit_reason, symbol))
            if cur.rowcount == 0:
                logger.info(f"[{symbol}] Position already closed, skipping close")
                return False

            trade_info = self.conn.execute("""
                SELECT id, entry_ts FROM paper_trades
                WHERE symbol = ? AND status = 'closed'
                ORDER BY id DESC LIMIT 1
            """, (symbol,)).fetchone()
            self.trailing_stops.pop(symbol, None)

        logger.info(f"[{symbol}] Position closed ({reason_label}) at {exit_price:.4f}: gross {raw_pnl_pct:+.3f}%, net {net_pnl_pct:+.3f}%")
        if reason_detail:
            logger.info(f"         Reason: {reason_detail}")

        # Send Telegram notification (outside the lock so we don't block the loop)
        try:
            import requests
            pnl_sign = "+" if net_pnl_pct >= 0 else ""
            pnl_emoji = "🟢" if net_pnl_pct > 0 else "🔴"
            trade_id_close = trade_info[0] if trade_info else 'N/A'
            entry_time_str = format_time_moscow(trade_info[1]) if trade_info and trade_info[1] else "N/A"
            exit_time_str = format_time_moscow(exit_ts)

            exit_msg = (
                f"{pnl_emoji} *{title}*\n\n"
                f"📋 *Trade ID: #{trade_id_close}*\n"
                f"Symbol: `{symbol}`\n"
                f"Side: *{trailing_state.side.upper()}*\n"
                f"Entry Price: `${trailing_state.entry_price:.2f}`\n"
                f"Exit Price: `${exit_price:.2f}`\n"
                f"⏰ Entry Time: `{entry_time_str}`\n"
                f"⏰ Exit Time: `{exit_time_str}`\n\n"
                f"Gross PnL: `{pnl_sign}{raw_pnl_pct:.3f}%`\n"
                f"Costs: `-{cost_pct:.3f}%`\n"
                f"*Net PnL: `{pnl_sign}{net_pnl_pct:.3f}%`*\n\n"
                f"Exit Reason: *{reason_label}*\n"
                f"{level_label}: `${exit_price:.2f}`"
            )
            if trailing_state.is_active:
                exit_msg += f"\nHighest: `${trailing_state.highest_price:.2f}`"
            url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
            data = {
                "chat_id": self.settings.telegram_chat_id,
                "text": exit_msg,
                "parse_mode": "Markdown",
            }
            response = requests.post(url, json=data, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram close notification sent")
            else:
                logger.warning(f"Telegram API error: {response.text}")
        except Exception as e:
            logger.warning(f"Failed to send Telegram close notification: {e}")

        return True

    def _stop_check_loop(self) -> None:
        """Background loop that watches the live price and reacts to stop levels."""
        logger.info(f"Fast stop-checker started (interval={self.settings.stop_check_interval_seconds}s)")
        while not self._shutdown.is_set():
            try:
                self._check_stops_fast()
            except Exception as e:
                logger.error(f"[stop-checker] cycle error: {e}", exc_info=True)
            self._shutdown.wait(self.settings.stop_check_interval_seconds)

    def _check_stops_fast(self) -> None:
        """Check the live forming-candle price for each open position and close on stop hit.

        Runs ~ every stop_check_interval_seconds (default 1s) and is independent of the
        heavy 15m signal cycle, so stop-losses react near real-time. Also covers periods
        when the main cycle is paused (it returns early and wouldn't manage stops).
        """
        with self._stop_lock:
            open_symbols = list(self.trailing_stops.keys())

        for symbol in open_symbols:
            try:
                collector = self.collectors.get(symbol)
                if collector is None:
                    continue
                bar_low = bar_high = None
                try:
                    # Live ticker price (near real-time) - primary source for stops
                    price = collector.get_current_price(symbol)
                except AttributeError:
                    # Fallback: last closed candle (may be up to one bar stale)
                    df = collector.fetch_klines(symbol, self.settings.timeframe, limit=1)
                    if df.empty:
                        continue
                    latest = df.iloc[-1]
                    price = float(latest["close"])
                    bar_low = float(latest["low"]) if pd.notna(latest.get("low")) else None
                    bar_high = float(latest["high"]) if pd.notna(latest.get("high")) else None
            except Exception as e:
                logger.warning(f"[stop-checker] fetch failed for {symbol}: {e}")
                continue

            with self._stop_lock:
                ts = self.trailing_stops.get(symbol)
            if ts is None:
                continue

            sl_hit, sl_reason = check_fixed_sl_exit(ts, price, bar_low=bar_low, bar_high=bar_high)
            if sl_hit:
                sl_exit_price = float(ts.initial_sl) if ts.initial_sl else price
                self._close_position(
                    symbol, ts, sl_exit_price,
                    exit_reason="fixed_stop_loss", title="STOP LOSS HIT",
                    reason_label="Fixed Stop Loss", level_label="SL Level",
                    reason_detail=sl_reason,
                )
                continue

            if ts.is_active and check_trailing_stop_exit(ts, price, bar_low=bar_low, bar_high=bar_high):
                trail_exit_price = float(ts.current_stop_price)
                self._close_position(
                    symbol, ts, trail_exit_price,
                    exit_reason="trailing_stop", title="TRADE CLOSED",
                    reason_label="Trailing Stop Hit", level_label="Stop Level",
                )
                continue

    def _is_candle_fresh(self, candle_ts: datetime, symbol: str) -> bool:
        """Check if candle is fresh (not stale)."""
        now = datetime.now(timezone.utc)
        age_minutes = (now - candle_ts.replace(tzinfo=timezone.utc)).total_seconds() / 60

        is_fresh = age_minutes <= (int(self.settings.timeframe) + self.settings.stale_candle_grace_minutes)

        if is_fresh:
            self.last_candle_time[symbol] = candle_ts
        else:
            logger.warning(f"Stale candle for {symbol} (age={age_minutes:.1f} min)")

        return is_fresh

    def _log_decision(
        self,
        ts: datetime,
        symbol: str,
        decision,
        regime: str,
        risk_result,
    ) -> None:
        """Log ensemble decision to database."""
        self.conn.execute("""
            INSERT INTO model_decisions (
                ts, symbol, decision, side,
                early_score, confirmation_score, momentum_direction,
                regime, confidence, action, position_size_pct,
                reasoning, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts.isoformat(),
            symbol,
            "signal_generated",
            decision.side,
            decision.early_result.score if decision.early_result else 0,
            decision.confirmation_result.score if decision.confirmation_result else 0,
            decision.momentum_result.direction if decision.momentum_result else "none",
            regime,
            decision.confidence,
            decision.action,
            decision.position_size_pct,
            "; ".join(decision.reasoning),
            json.dumps({
                "close_price": float(decision.confirmation_result.probability) if decision.confirmation_result else 0,
                "take_profit": risk_result.take_profit_price,
                "stop_loss": risk_result.stop_loss_price,
                "risk_amount": risk_result.risk_amount,
            })
        ))
        self.conn.commit()

    def _audit_log_decision(
        self,
        ts,
        symbol: str,
        close_price: float,
        atr_pct: float,
        regime: str,
        decision,
        featured: pd.DataFrame,
    ) -> None:
        """Log decision to audit table with full context."""
        try:
            # Get probabilities from ensemble
            early_prob = decision.early_result.probability if decision.early_result else 0.0
            confirm_prob = decision.confirmation_result.probability if decision.confirmation_result else 0.0
            momentum_score = decision.momentum_result.score if decision.momentum_result else 0.0

            # Get adaptive thresholds
            adaptive_early = self.threshold_engine.base_thresholds.get(symbol)
            early_thresh = adaptive_early.early_signal_threshold if adaptive_early else 0.60
            confirm_thresh = adaptive_early.confirmation_threshold if adaptive_early else 0.75
            momentum_thresh = adaptive_early.momentum_threshold if adaptive_early else 0.55

            # Extract key features
            latest_row = featured.iloc[-1]
            features_dict = {
                "atr_pct_14": float(latest_row.get("atr_pct_14", 0)),
                "rsi_14": float(latest_row.get("rsi_14", 50)),
                "ema_8_vs_21": float(latest_row.get("ema_8_vs_21", 0)),
                "volume_zscore": float(latest_row.get("vol_zscore", 0)),
                "bar_close_position": float(latest_row.get("bar_close_position", 0.5)),
            }

            # Calculate future returns (simplified - use next few bars if available)
            future_data = {
                "next_1bar_return": 0.0,  # Would need forward data
                "next_3bar_return": 0.0,
                "next_6bar_return": 0.0,
                "next_high": close_price,
                "next_low": close_price,
            }

            # Log to audit table
            self.audit_engine.log_decision(
                ts=ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                symbol=symbol,
                close_price=close_price,
                atr_pct=atr_pct,
                regime=regime,
                early_prob=early_prob,
                confirm_prob=confirm_prob,
                momentum_score=momentum_score,
                adaptive_early_thresh=early_thresh,
                adaptive_confirm_thresh=confirm_thresh,
                adaptive_momentum_thresh=momentum_thresh,
                action=decision.action,
                action_reason="; ".join(decision.reasoning[:3]),
                features_dict=features_dict,
                future_data=future_data,
            )
        except Exception as e:
            logger.warning(f"Audit logging failed: {e}")

    def _log_all_decisions(
        self,
        ts,
        symbol: str,
        close_price: float,
        atr_pct: float,
        regime: str,
        early_prob: float,
        confirm_prob: float,
        momentum_score: float,
        adaptive_early_thresh: float,
        adaptive_confirm_thresh: float,
        adaptive_momentum_thresh: float,
        action: str,
        confidence: float,
        position_size_pct: float,
        reasoning: str,
    ) -> None:
        """
        Log ALL decisions (ENTER, SKIP, WAIT) to signal_audit table for analysis.

        This allows us to analyze missed opportunities and understand why signals were skipped.
        """
        try:
            logger.info(f"Logging decision to signal_audit_log: {symbol} {action} (conf={confidence:.0f}%)")
            self.conn.execute("""
                INSERT INTO signal_audit_log (
                    ts, symbol, close_price, atr_pct, regime,
                    early_probability, confirmation_probability, momentum_score,
                    adaptive_early_threshold, adaptive_confirmation_threshold, adaptive_momentum_threshold,
                    action, action_reason, features_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                symbol,
                close_price,
                atr_pct,
                regime,
                early_prob,
                confirm_prob,
                momentum_score,
                adaptive_early_thresh,
                adaptive_confirm_thresh,
                adaptive_momentum_thresh,
                action,
                reasoning,
                "{}",  # Empty features_json for now
                json.dumps({
                    "confidence_pct": confidence,
                    "position_size_pct": position_size_pct,
                    "close_price": close_price,
                    "logged_at": datetime.now(timezone.utc).isoformat(),
                })
            ))
            self.conn.commit()
            logger.info(f"Decision logged successfully: {symbol} {action}")
        except Exception as e:
            logger.error(f"Failed to log decision to signal_audit_log: {e}", exc_info=True)

    def _log_health(self, status: str, note: str) -> None:
        """Log health check result."""
        self.conn.execute("""
            INSERT INTO health_log (ts, status, error_streak, note)
            VALUES (?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            status,
            self.error_streak,
            note
        ))
        self.conn.commit()

        if status == "ok":
            self.error_streak = 0  # Reset on success


if __name__ == "__main__":
    from .config import Settings

    settings = Settings()
    engine = RuntimeEngine(settings)
    engine.run()
