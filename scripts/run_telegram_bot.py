#!/usr/bin/env python
"""
Telegram Bot launcher for Claude ML Trading System.

Usage:
    cd C:\Bot\claude_ml_system
    .venv\Scripts\activate
    python scripts/run_telegram_bot.py
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_ml.config import Settings
from claude_ml.telegram_bot import create_bot

def main():
    """Launch Telegram bot."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/telegram_bot.log", encoding='utf-8')
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info("="*60)
    logger.info("Claude ML - Telegram Bot Starting...")
    logger.info("="*60)

    # Load settings
    settings = Settings()

    # Check if Telegram is configured
    if not settings.telegram_bot_token or settings.telegram_bot_token == "your_bot_token_here":
        logger.error("❌ Telegram bot token not configured!")
        logger.error("Please set TELEGRAM_BOT_TOKEN in .env file")
        sys.exit(1)

    if not settings.telegram_chat_id or settings.telegram_chat_id == "your_chat_id_here":
        logger.warning("⚠️ Telegram chat ID not configured!")
        logger.warning("Send /start to your bot to get chat ID")
        logger.warning("Or set it manually in .env file")

    # Create bot
    bot = create_bot(
        token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        db_path=str(settings.runtime_db_path)
    )

    logger.info(f"✓ Bot configured")
    logger.info(f"  Token: {settings.telegram_bot_token[:20]}...")
    logger.info(f"  Chat ID: {settings.telegram_chat_id}")
    logger.info(f"  DB: {settings.runtime_db_path}")
    logger.info("")
    logger.info("Bot is running! Use these commands:")
    logger.info("  /start - Welcome message")
    logger.info("  /balance - Current balance & stats")
    logger.info("  /trades - Recent trades")
    logger.info("  /status - System status")
    logger.info("")
    logger.info("Trade notifications will arrive automatically!")
    logger.info("="*60)

    # Start bot
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("\nStopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
