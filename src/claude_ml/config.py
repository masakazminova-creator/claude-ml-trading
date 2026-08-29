"""
Configuration module for Claude ML Trading System.

Enhanced version with multi-symbol support, dynamic position sizing,
and production-grade risk management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
from typing import List, Optional

from dotenv import load_dotenv


# Determine root directory: use PROJECT_ROOT env var if set (for Docker), otherwise auto-detect
PROJECT_ROOT_ENV = os.getenv("PROJECT_ROOT", "")
if PROJECT_ROOT_ENV:
    ROOT_DIR = Path(PROJECT_ROOT_ENV)
else:
    ROOT_DIR = Path(__file__).resolve().parents[2]  # One level up from src/claude_ml (points to claude_ml_system/)
load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str) -> str:
    """Get environment variable with fallback."""
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: str) -> bool:
    """Parse boolean environment variable."""
    return _env(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    """Parse float environment variable."""
    value = os.getenv(name)
    return float(value) if value not in (None, "") else float(default)


def _env_list(name: str, default: str) -> List[str]:
    """Parse comma-separated list from environment."""
    value = _env(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    """Centralized configuration for Claude ML Trading System."""

    # === Project Structure ===
    root_dir: Path = ROOT_DIR
    src_dir: Path = field(default_factory=lambda: ROOT_DIR / "src")
    data_dir: Path = field(default_factory=lambda: ROOT_DIR / "data")
    models_dir: Path = field(default_factory=lambda: ROOT_DIR / "models")
    logs_dir: Path = field(default_factory=lambda: ROOT_DIR / "logs")

    # === Market Data ===
    market_data_provider: str = _env("MARKET_DATA_PROVIDER", "okx").lower()
    bybit_base_url: str = _env("BYBIT_BASE_URL", "https://api.bybit.com")
    okx_base_url: str = _env("OKX_BASE_URL", "https://www.okx.com")

    # === Multi-Symbol Configuration ===
    symbols: List[str] = field(default_factory=lambda: _env_list("SYMBOLS", "BTCUSDT"))
    market_category: str = _env("MARKET_CATEGORY", "linear").lower()
    timeframe: str = _env("TIMEFRAME", "15")

    # === Data Collection ===
    lookback_bars: int = int(_env("LOOKBACK_BARS", "3000"))
    training_lookback_bars: int = int(_env("TRAINING_LOOKBACK_BARS", "10000"))
    train_split: float = float(_env("TRAIN_SPLIT", "0.8"))

    # === Feature Engineering ===
    label_horizon_bars: int = int(_env("LABEL_HORIZON_BARS", "6"))
    label_min_return_pct: float = float(_env("LABEL_MIN_RETURN_PCT", "0.20"))  # Updated to match .env
    atr_period: int = int(_env("ATR_PERIOD", "14"))
    rsi_period: int = int(_env("RSI_PERIOD", "14"))
    ema_fast: int = int(_env("EMA_FAST", "8"))
    ema_slow: int = int(_env("EMA_SLOW", "21"))

    # === Model Configuration ===
    model_max_depth: int = int(_env("MODEL_MAX_DEPTH", "5"))
    model_learning_rate: float = float(_env("MODEL_LEARNING_RATE", "0.045"))
    model_max_iter: int = int(_env("MODEL_MAX_ITER", "300"))
    model_min_samples_leaf: int = int(_env("MODEL_MIN_SAMPLES_LEAF", "20"))
    model_random_state: int = int(_env("MODEL_RANDOM_STATE", "42"))

    # === Entry Thresholds ===
    early_signal_threshold: float = float(_env("EARLY_SIGNAL_THRESHOLD", "0.60"))
    confirmation_threshold: float = float(_env("CONFIRMATION_THRESHOLD", "0.75"))
    momentum_threshold: float = float(_env("MOMENTUM_THRESHOLD", "0.55"))

    # === Risk Management ===
    risk_per_trade_pct: float = float(_env("RISK_PER_TRADE_PCT", "1.0"))
    max_portfolio_risk_pct: float = float(_env("MAX_PORTFOLIO_RISK_PCT", "5.0"))
    max_drawdown_pct: float = float(_env("MAX_DRAWDOWN_PCT", "15.0"))
    reduce_size_at_dd_pct: float = float(_env("REDUCE_SIZE_AT_DD_PCT", "10.0"))
    pause_at_dd_pct: float = float(_env("PAUSE_AT_DD_PCT", "12.0"))
    max_position_size_pct: float = float(_env("MAX_POSITION_SIZE_PCT", "3.0"))

    # === Position Sizing Multipliers ===
    size_multiplier_chop: float = float(_env("SIZE_MULTIPLIER_CHOP", "0.5"))
    size_multiplier_expansion: float = float(_env("SIZE_MULTIPLIER_EXPANSION", "1.2"))
    size_multiplier_trend: float = float(_env("SIZE_MULTIPLIER_TREND", "1.0"))

    # === Exit Configuration ===
    min_atr_pct_for_entry: float = float(_env("MIN_ATR_PCT_FOR_ENTRY", "0.5"))  # Minimum ATR% to allow entries
    take_profit_atr_multiplier: float = float(_env("TAKE_PROFIT_ATR_MULTIPLIER", "2.5"))
    max_take_profit_pct: float = float(_env("MAX_TAKE_PROFIT_PCT", "1.50"))  # Cap TP (trailing-activation trigger) at this % of entry
    stop_loss_atr_multiplier: float = float(_env("STOP_LOSS_ATR_MULTIPLIER", "2.0"))
    min_stop_loss_pct: float = float(_env("MIN_STOP_LOSS_PCT", "0.80"))  # Floor: SL never tighter than this % of entry (avoids stop-outs from low-vol noise)
    trailing_stop_pct: float = float(_env("TRAILING_STOP_PCT", "0.5"))  # Trailing stop keeps at most this % of distance from the extreme (caps give-back)
    trailing_trigger_atr_multiplier: float = float(_env("TRAILING_TRIGGER_ATR_MULTIPLIER", "0.5"))
    trailing_step_atr_multiplier: float = float(_env("TRAILING_STEP_ATR_MULTIPLIER", "1.0"))
    soft_exit_enabled: bool = _env_bool("SOFT_EXIT_ENABLED", "true")
    soft_exit_min_bars: int = int(_env("SOFT_EXIT_MIN_BARS", "2"))

    # === Continuous Learning ===
    retrain_interval_trades: int = int(_env("RETRAIN_INTERVAL_TRADES", "100"))
    drift_check_correlation_threshold: float = float(_env("DRIFT_CHECK_CORRELATION_THRESHOLD", "0.3"))
    min_trades_for_calibration: int = int(_env("MIN_TRADES_FOR_CALIBRATION", "50"))
    walk_forward_folds: int = int(_env("WALK_FORWARD_FOLDS", "5"))

    # === Runtime ===
    poll_seconds: int = int(_env("POLL_SECONDS", "15"))
    stop_check_interval_seconds: int = int(_env("STOP_CHECK_INTERVAL_SECONDS", "1"))
    mode: str = _env("MODE", "paper").lower()
    paper_start_balance: float = float(_env("PAPER_START_BALANCE", "10000"))
    leverage: float = float(_env("LEVERAGE", "1"))

    # === Costs ===
    fee_bps: float = float(_env("FEE_BPS", "5.0"))
    slippage_bps: float = float(_env("SLIPPAGE_BPS", "3.0"))

    # === Health Checks ===
    stale_candle_grace_minutes: int = int(_env("STALE_CANDLE_GRACE_MINUTES", "5"))
    max_error_streak: int = int(_env("MAX_ERROR_STREAK", "3"))
    daily_pnl_limit_pct: float = float(_env("DAILY_PNL_LIMIT_PCT", "5.0"))

    # === Notifications ===
    telegram_bot_token: str = _env("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = _env("TELEGRAM_CHAT_ID", "")

    # === Blocked Conditions ===
    blocked_regimes: List[str] = field(default_factory=lambda: _env_list("BLOCKED_REGIMES", ""))
    blocked_hours_msk: List[str] = field(default_factory=lambda: _env_list("BLOCKED_HOURS_MSK", ""))

    @property
    def runtime_db_path(self) -> Path:
        """Path to runtime SQLite database."""
        return self.data_dir / "runtime.sqlite"

    @property
    def models_candidates_dir(self) -> Path:
        """Path to candidate models directory."""
        return self.models_dir / "candidates"

    @property
    def models_experts_dir(self) -> Path:
        """Path to expert models directory."""
        return self.models_dir / "experts"

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.models_candidates_dir.mkdir(parents=True, exist_ok=True)
        self.models_experts_dir.mkdir(parents=True, exist_ok=True)

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if self.mode not in ("paper", "live"):
            errors.append(f"Invalid mode: {self.mode}. Must be 'paper' or 'live'.")

        if self.risk_per_trade_pct <= 0 or self.risk_per_trade_pct > 5:
            errors.append(f"risk_per_trade_pct must be between 0 and 5, got {self.risk_per_trade_pct}")

        if self.max_drawdown_pct <= 0 or self.max_drawdown_pct > 50:
            errors.append(f"max_drawdown_pct must be between 0 and 50, got {self.max_drawdown_pct}")

        if self.reduce_size_at_dd_pct >= self.pause_at_dd_pct:
            errors.append("reduce_size_at_dd_pct must be less than pause_at_dd_pct")

        if self.stop_loss_atr_multiplier >= self.take_profit_atr_multiplier:
            errors.append("stop_loss_atr_multiplier must be less than take_profit_atr_multiplier")

        if not self.symbols:
            errors.append("symbols list cannot be empty")

        return errors
