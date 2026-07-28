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
import sqlite3
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
from .trailing_stop import TrailingStopState, create_trailing_stop, update_trailing_stop, check_trailing_stop_exit
from .models.early_signal import EarlySignalModel
from .models.confirmation import ConfirmationModel
from .models.momentum import MomentumModel

# Module logger
logger = logging.getLogger(__name__)


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

        # Load models (if available)
        self.early_model = self._load_early_model()
        self.confirmation_model = self._load_confirmation_model()
        self.momentum_model = self._load_momentum_model()

        # Initialize ensemble engine (only if all models loaded)
        self.ensemble: Optional[EnsembleEngine] = None
        if all([self.early_model, self.confirmation_model, self.momentum_model]):
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

        # Initialize database FIRST (before other engines that need DB)
        self.conn = sqlite3.connect(settings.runtime_db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

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

        # Circuit breaker state
        self.trading_paused = False
        self.pause_reason = ""
        self.emergency_stop_triggered = False

        # Runtime state
        self.error_streak = 0
        self.last_candle_time = {}
        self.stage_tracker = {}  # symbol -> current stage ('stage_1' or 'stage_2')

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

        self.conn.commit()

    def run(self) -> None:
        """Main runtime loop."""

        logger.info("Claude ML Trading System - Starting...")
        logger.info(f"Mode: {self.settings.mode.upper()}, Symbols: {', '.join(self.settings.symbols)}")
        logger.info(f"Timeframe: {self.settings.timeframe}m, Poll: {self.settings.poll_seconds}s")

        cycle_count = 0

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
            raise RuntimeError(f"No data fetched for {symbol}")

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
            raise RuntimeError(f"No features built for {symbol}")

        # Classify regime
        logger.debug(f"Classifying regime for {symbol}...")
        try:
            regime = classify_regime(featured.iloc[-1])
            regime_name = regime.get('structure_regime', 'unknown')
            logger.debug(f"Regime for {symbol}: {regime_name}")
        except Exception as e:
            logger.error(f"Failed to classify regime for {symbol}: {e}", exc_info=True)
            return

        # Check if candle is fresh
        latest_ts = featured["ts"].iloc[-1]
        if not self._is_candle_fresh(latest_ts, symbol):
            return

        # Get latest row
        latest_row = featured.iloc[-1]
        close_price = float(latest_row["close"])
        atr_pct = float(latest_row.get("atr_pct_14", 0.5))  # ATR as percentage
        atr = atr_pct * close_price / 100  # Convert % to absolute value

        # Check trailing stop for existing position
        if symbol in self.trailing_stops:
            trailing_state = self.trailing_stops[symbol]

            # Update trailing stop with new price
            trailing_state = update_trailing_stop(
                state=trailing_state,
                current_price=close_price,
                atr=atr,
            )
            self.trailing_stops[symbol] = trailing_state

            # Check if stop hit
            if check_trailing_stop_exit(trailing_state, close_price):
                pnl_pct = ((close_price - trailing_state.entry_price) / trailing_state.entry_price * 100)
                logger.info(f"[{symbol}] TRAILING STOP HIT at {close_price:.4f}")
                logger.info(f"         PnL: {pnl_pct:.2f}%")

                # Send Telegram notification for exit
                try:
                    from telegram import Bot
                    bot = Bot(token=self.settings.telegram_bot_token)
                    pnl_sign = "+" if pnl_pct >= 0 else ""
                    pnl_emoji = "🟢" if pnl_pct > 0 else "🔴"
                    exit_msg = (
                        f"{pnl_emoji} *TRADE CLOSED*\n\n"
                        f"Symbol: `{symbol}`\n"
                        f"Side: *{trailing_state.side.upper()}*\n"
                        f"Entry Price: `${trailing_state.entry_price:.2f}`\n"
                        f"Exit Price: `${close_price:.2f}`\n"
                        f"PnL: `{pnl_sign}{pnl_pct:.2f}%`\n\n"
                        f"Exit Reason: *Trailing Stop Hit*\n"
                        f"Highest Price: `${trailing_state.highest_price:.2f}`\n"
                        f"Final Stop: `${trailing_state.current_stop_price:.2f}`"
                    )
                    bot.send_message(chat_id=self.settings.telegram_chat_id, text=exit_msg, parse_mode="Markdown")
                    logger.info("Telegram exit notification sent")
                except Exception as e:
                    logger.warning(f"Failed to send Telegram exit notification: {e}")

                # TODO: Close position in database
                # For now, just log and remove from tracking
                del self.trailing_stops[symbol]
                return  # Skip signal generation for this bar

        # Get adaptive thresholds for this symbol and regime
        early_thresh = self.threshold_engine.get_adaptive_threshold(
            symbol=symbol,
            regime=regime_name,
            atr_pct=atr_pct,
            threshold_type="early_signal"
        )
        confirm_thresh = self.threshold_engine.get_adaptive_threshold(
            symbol=symbol,
            regime=regime_name,
            atr_pct=atr_pct,
            threshold_type="confirmation"
        )
        momentum_thresh = self.threshold_engine.get_adaptive_threshold(
            symbol=symbol,
            regime=regime_name,
            atr_pct=atr_pct,
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

                # Calculate position size via risk manager
                if decision.action.startswith("enter"):
                    risk_result = self.risk_manager.calculate_position_size(
                        symbol=symbol,
                        entry_price=close_price,
                        atr=atr,
                        regime=regime_name,
                        model_confidence=decision.confidence / 100,
                        side=decision.side,
                    )

                    logger.info(f"         TP: {risk_result.take_profit_price:.4f} | "
                          f"SL: {risk_result.stop_loss_price:.4f} | "
                          f"Risk: ${risk_result.risk_amount:.2f}")

                    # Create ATR-based trailing stop
                    trailing_state = create_trailing_stop(
                        symbol=symbol,
                        side=decision.side,
                        entry_price=close_price,
                        atr=atr,
                        trigger_mult=0.5,  # Activate after 0.5 ATR profit
                        stop_mult=1.5,     # Stop at 1.5 ATR distance
                    )
                    self.trailing_stops[symbol] = trailing_state
                    logger.info(f"         Trailing stop created: {trailing_state.current_stop_price:.4f}")

                    # Send Telegram notification for entry
                    try:
                        from telegram import Bot
                        bot = Bot(token=self.settings.telegram_bot_token)
                        entry_msg = (
                            f"🔔 *NEW TRADE ENTRY*\n\n"
                            f"Symbol: `{symbol}`\n"
                            f"Side: *{decision.side.upper()}*\n"
                            f"Entry Price: `${close_price:.2f}`\n"
                            f"Confidence: `{decision.confidence:.0f}%`\n"
                            f"Position Size: `{risk_result.adjusted_size_pct:.1f}%`\n\n"
                            f"Take Profit: `${risk_result.take_profit_price:.2f}`\n"
                            f"Stop Loss: `${risk_result.stop_loss_price:.2f}`\n"
                            f"Trailing Stop: `${trailing_state.current_stop_price:.2f}`\n\n"
                            f"Regime: `{regime_name}`\n"
                            f"Reasoning: {'; '.join(decision.reasoning[:3])}"
                        )
                        bot.send_message(chat_id=self.settings.telegram_chat_id, text=entry_msg, parse_mode="Markdown")
                        logger.info("Telegram entry notification sent")
                    except Exception as e:
                        logger.warning(f"Failed to send Telegram entry notification: {e}")

                    # Log decision
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
                        atr_pct=atr_pct * 100 / close_price if close_price > 0 else 0.5,
                        regime=regime_name,
                        decision=decision,
                        featured=featured,
                    )

        else:
            # Data-only mode
            print(f"[{symbol}] Regime: {regime_name}, Price: {close_price:.4f}")

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
