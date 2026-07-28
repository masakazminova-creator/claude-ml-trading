#!/usr/bin/env python
"""
Wrapper script to run paper trading with proper logging.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Setup logging FIRST
from claude_ml.logging_config import setup_logging

log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

setup_logging(
    log_level="INFO",
    log_file=str(log_dir / "runtime.log"),
    enable_telegram=False  # Can be enabled later
)

import logging
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    from claude_ml.runtime import RuntimeEngine
    from claude_ml.config import Settings

    logger.info("="*80)
    logger.info("Claude ML Paper Trading - Starting...")
    logger.info("="*80)

    settings = Settings()
    logger.info(f"Configuration: {len(settings.symbols)} symbols, mode={settings.mode}")
    logger.info(f"Timeframe: {settings.timeframe}m, Poll: {settings.poll_seconds}s")

    engine = RuntimeEngine(settings)
    logger.info(f"Models loaded: {engine.ensemble is not None}")
    logger.info(f"Risk per trade: {settings.risk_per_trade_pct}%")
    logger.info(f"Max drawdown: {settings.max_drawdown_pct}%")
    logger.info("="*80)

    try:
        engine.run()
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
