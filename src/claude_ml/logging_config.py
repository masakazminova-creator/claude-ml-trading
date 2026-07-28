"""
Logging configuration for Claude ML Trading System.

Provides structured logging with multiple handlers:
- Console (StreamHandler) - for development
- File (FileHandler) - for production with rotation
- Optional Telegram alerts for critical events

Usage:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Message")
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_telegram: bool = False,
    telegram_bot_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
) -> None:
    """
    Setup logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional, enables file logging)
        enable_telegram: Enable Telegram notifications for errors
        telegram_bot_token: Telegram bot token for notifications
        telegram_chat_id: Telegram chat ID for notifications
    """
    # Get numeric log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Format for logs
    detailed_format = logging.Formatter(
        '%(asctime)s [%(levelname)-8s] %(name)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_format = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )

    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(simple_format)
    root_logger.addHandler(console_handler)

    # File handler (if log_file specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Rotating file handler (max 10MB, keep 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)  # Log everything to file
        file_handler.setFormatter(detailed_format)
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sklearn').setLevel(logging.WARNING)
    logging.getLogger('pandas').setLevel(logging.WARNING)

    # Log startup message
    root_logger.info(f"Logging initialized at {log_level} level")
    if log_file:
        root_logger.info(f"Log file: {log_file}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name."""
    return logging.getLogger(name)
