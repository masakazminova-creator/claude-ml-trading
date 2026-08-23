"""
Telegram Bot for Claude ML Trading System.

Features:
- Trade notifications (entry/exit)
- Balance button with real-time updates
- Performance metrics display
- Position tracking

Usage:
    python scripts/run_telegram_bot.py
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

logger = logging.getLogger(__name__)


class TradingBot:
    """Telegram bot for trading notifications and monitoring."""

    def __init__(self, token: str, chat_id: str, db_path: str):
        self.token = token
        self.chat_id = chat_id
        self.db_path = db_path

        # Create application
        self.application = Application.builder().token(token).build()

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("balance", self.balance))
        self.application.add_handler(CommandHandler("trades", self.trades))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler("position", self.position))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    @staticmethod
    def get_main_keyboard() -> ReplyKeyboardMarkup:
        """Create main reply keyboard with buttons."""
        keyboard = [
            [
                KeyboardButton("💰 Баланс"),
                KeyboardButton("📈 Статус"),
            ],
            [
                KeyboardButton("📊 Сделки"),
                KeyboardButton("📍 Позиция"),
            ],
            [
                KeyboardButton("🔄 Обновить"),
            ],
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with persistent keyboard."""
        welcome_msg = (
            "🤖 *Claude ML Trading Bot*\n\n"
            "Система автоматического трейдинга запущена!\n\n"
            "Используйте кнопки снизу для управления:"
        )

        await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=self.get_main_keyboard())

    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /balance command."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Calculate REALIZED balance only (start balance + closed trades PnL)
            cursor.execute("SELECT value FROM runtime_state WHERE key='paper_start_balance'")
            start_row = cursor.fetchone()
            start_balance = float(start_row[0]) if start_row and start_row[0] is not None else 10000.0

            # Get all CLOSED trades PnL (not open positions)
            cursor.execute("""
                SELECT pnl_pct FROM paper_trades
                WHERE status = 'closed'
                  AND exit_ts IS NOT NULL
                  AND ABS(pnl_pct) > 0.01
                ORDER BY id
            """)
            pnl_rows = cursor.fetchall()

            # Calculate balance using COMPOUND returns (not simple sum!)
            current_balance = start_balance
            for row in pnl_rows:
                pnl_pct = float(row[0]) if row[0] is not None else 0.0
                current_balance *= (1 + pnl_pct / 100)  # Compound each trade

            # Total PnL percentage
            total_pnl_pct = ((current_balance - start_balance) / start_balance * 100) if start_balance > 0 else 0.0

            # Total PnL percentage already calculated above
            total_pnl = total_pnl_pct

            # Get REAL trade count (exclude trades with very small PnL - likely test/duplicate)
            cursor.execute("""
                SELECT COUNT(*) FROM paper_trades
                WHERE status = 'closed'
                  AND exit_ts IS NOT NULL
                  AND ABS(pnl_pct) > 0.01
            """)
            trade_count = int(cursor.fetchone()[0])

            # Get win rate for REAL trades only
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
                    COUNT(*) as total
                FROM paper_trades
                WHERE status = 'closed'
                  AND exit_ts IS NOT NULL
                  AND ABS(pnl_pct) > 0.01
            """)
            wr_row = cursor.fetchone()
            wins = int(wr_row[0]) if wr_row and wr_row[0] is not None else 0
            total_trades = int(wr_row[1]) if wr_row and wr_row[1] is not None else 0
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

            # Calculate drawdown from equity curve
            cursor.execute("""
                SELECT MAX(balance) FROM equity_curve
            """)
            peak_row = cursor.fetchone()
            peak_balance = float(peak_row[0]) if peak_row and peak_row[0] is not None else current_balance
            drawdown = ((peak_balance - current_balance) / peak_balance * 100) if peak_balance > 0 else 0.0

            conn.close()

            # Format message with safe values
            pnl_sign = "+" if total_pnl >= 0 else ""
            dd_sign = "-" if drawdown > 0 else ""

            msg = (
                f"💰 *Trading Balance*\n\n"
                f"Текущий баланс: `${current_balance:,.2f}`\n"
                f"Общий PnL: `{pnl_sign}{total_pnl:.2f}%`\n"
                f"Peak баланс: `${peak_balance:,.2f}`\n"
                f"Drawdown: `{dd_sign}{drawdown:.2f}%`\n\n"
                f"📊 *Статистика:*\n"
                f"Всего сделок: `{trade_count}`\n"
                f"Win Rate: `{win_rate:.1f}%`\n"
                f"Wins: `{wins}` | Losses: `{total_trades - wins}`"
            )

            # Add refresh button
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_balance")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in balance command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка получения баланса: {e}")

    async def trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trades command."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT entry_ts, symbol, side, entry_price, pnl_pct, exit_reason
                FROM paper_trades
                WHERE status IN ('closed', 'shadow_closed') AND pnl_pct IS NOT NULL
                ORDER BY id DESC
                LIMIT 10
            """)
            trades = cursor.fetchall()

            conn.close()

            if not trades:
                await update.message.reply_text("📭 Нет завершённых сделок")
                return

            msg = "📊 *Последние 10 сделок:*\n\n"
            for trade in trades:
                entry_ts, symbol, side, entry_price, pnl_pct, exit_reason = trade

                # Handle None values safely
                if pnl_pct is None:
                    pnl_pct = 0.0
                if entry_price is None:
                    entry_price = 0.0
                if exit_reason is None:
                    exit_reason = "N/A"

                pnl_sign = "+" if pnl_pct >= 0 else ""
                emoji = "🟢" if pnl_pct > 0 else "🔴" if pnl_pct < 0 else "⚪"

                # Escape special characters in strings
                symbol_str = str(symbol).replace('_', r'\_') if symbol else "N/A"
                side_str = str(side).upper().replace('_', r'\_') if side else "N/A"
                exit_str = str(exit_reason).replace('_', r'\_')
                ts_str = str(entry_ts)[:19] if entry_ts else 'N/A'

                msg += (
                    f"{emoji} *{symbol_str}* {side_str}\n"
                    f"   Entry: \\${entry_price:.2f}\n"
                    f"   PnL: `{pnl_sign}{pnl_pct:.2f}%`\n"
                    f"   Exit: {exit_str}\n"
                    f"   Time: {ts_str}\n\n"
                )

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in trades command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка получения сделок: {e}")

    async def position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /position command - show current open position details."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get open position
            cursor.execute("""
                SELECT id, symbol, side, entry_ts, entry_price, signal_probability, payload_json
                FROM paper_trades
                WHERE status = 'open'
                ORDER BY id DESC
                LIMIT 1
            """)
            pos = cursor.fetchone()

            if not pos:
                await update.message.reply_text("📭 Нет открытых позиций")
                conn.close()
                return

            trade_id, symbol, side, entry_ts, entry_price, confidence, payload_json = pos
            import json
            payload = json.loads(payload_json) if payload_json else {}

            # Extract data from payload
            atr_pct = float(payload.get('atr_pct', 0.0))
            regime = payload.get('regime', 'N/A')
            reasoning = payload.get('reasoning', [])
            exit_strategy = payload.get('exit_strategy', 'N/A')

            # Calculate TP/SL levels (using same logic as runtime)
            atr_value = entry_price * atr_pct
            tp_distance = atr_value * 2.5
            sl_distance = atr_value * 2.0

            if side == "long":
                tp_level = entry_price + tp_distance
                sl_level = entry_price - sl_distance
            else:  # short
                tp_level = entry_price - tp_distance
                sl_level = entry_price + sl_distance

            # Get current price from Bybit (matches the exchange chart the user watches).
            # Note: trades are executed on OKX (BTC-USDT-SWAP), so entry prices are OKX;
            # the two exchanges differ by a few dollars, which is why the bot prices and
            # a Bybit chart can look slightly out of sync.
            import requests, time
            try:
                response = requests.get(
                    'https://api.bybit.com/v5/market/tickers',
                    params={'category': 'linear', 'symbol': symbol},
                    timeout=5,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                data = response.json()
                item = data.get('result', {}).get('list', [{}])[0]
                if 'lastPrice' not in item:
                    raise ValueError("Bybit ticker returned no lastPrice")
                current_price = float(item['lastPrice'])

                # Timestamp from Bybit to show how fresh the price is
                price_ts_ms = int(item.get('timestamp') or item.get('ts') or item.get('updateTime') or 0)
                if price_ts_ms > 0:
                    price_age_sec = (int(time.time() * 1000) - price_ts_ms) / 1000
                    price_freshness = f"(price age: {price_age_sec:.1f}s)"
                else:
                    price_freshness = ""

                pnl_pct = ((current_price - entry_price) / entry_price * 100) if side == "long" else ((entry_price - current_price) / entry_price * 100)
            except Exception as e:
                logger.warning(f"Failed to fetch current price: {e}")
                current_price = None
                pnl_pct = None
                price_freshness = ""

            conn.close()

            # Format message (escape special chars for Telegram Markdown)
            side_emoji = "🟢" if side == "long" else "🔴"
            side_str = side.upper()

            # Escape dollar signs and other special chars
            entry_price_str = f"{entry_price:,.2f}"
            tp_level_str = f"{tp_level:,.2f}"
            sl_level_str = f"{sl_level:,.2f}"
            current_price_str = f"{current_price:,.2f}" if current_price else "N/A"

            msg = f"{side_emoji} *Текущая позиция #{trade_id}*\n\n"
            msg += f"*Symbol:* `{symbol}`\n"
            msg += f"*Side:* *{side_str}*\n"
            msg += f"*Entry:* ${entry_price_str}\n"
            msg += f"*Confidence:* `{confidence*100:.1f}%`\n"
            msg += f"*Regime:* `{regime}`\n\n"

            # TP/SL info
            msg += f"🎯 *Уровни:*\n"
            msg += f"Take Profit: ${tp_level_str}\n"
            msg += f"Stop Loss: ${sl_level_str}\n"
            msg += f"Exit Strategy: `{exit_strategy}`\n\n"

            # Current PnL
            if current_price is not None and pnl_pct is not None:
                pnl_sign = "+" if pnl_pct >= 0 else ""
                pnl_emoji_char = "🟢" if pnl_pct > 0 else "🔴"
                msg += f"📈 *Текущий статус:*\n"
                msg += f"Current Price: ${current_price_str}\n"
                if price_freshness:
                    msg += f"_Last update: {price_freshness}_\n"
                msg += f"PnL: `{pnl_sign}{pnl_pct:.3f}%` {pnl_emoji_char}\n\n"

            # Entry time (convert to Moscow time UTC+3)
            if entry_ts:
                try:
                    from datetime import datetime, timezone, timedelta
                    # Parse UTC timestamp
                    utc_dt = datetime.fromisoformat(entry_ts.replace('+00:00', ''))
                    # Convert to Moscow time (UTC+3)
                    moscow_tz = timezone(timedelta(hours=3))
                    moscow_dt = utc_dt.replace(tzinfo=timezone.utc).astimezone(moscow_tz)
                    entry_time_msk = moscow_dt.strftime('%Y-%m-%d %H:%M:%S') + ' MSK'
                except Exception as e:
                    entry_time_msk = str(entry_ts)[:19] + ' UTC'
            else:
                entry_time_msk = 'N/A'
            msg += f"⏰ *Время входа:* {entry_time_msk}\n\n"

            # Reasoning
            if reasoning:
                msg += f"💡 *Причина входа:*\n"
                for i, reason in enumerate(reasoning[:3], 1):
                    # Escape special Markdown chars in reasoning
                    safe_reason = reason.replace('_', '\\_').replace('*', '\\*')
                    msg += f"{i}. {safe_reason}\n"

            # Add refresh button
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить цену", callback_data=f"refresh_position_{trade_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in position command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка получения позиции: {e}")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Check if system is running (recent health log)
            cursor.execute("""
                SELECT ts, status FROM health_log
                ORDER BY id DESC LIMIT 1
            """)
            health = cursor.fetchone()

            # Count open positions
            cursor.execute("""
                SELECT COUNT(*) FROM paper_trades
                WHERE status = 'open'
            """)
            open_positions = cursor.fetchone()[0]

            conn.close()

            if health:
                ts, status = health
                status_emoji = "✅" if status == "ok" else "❌"
                msg = f"{status_emoji} *System Status*\n\n"
                msg += f"Статус: `{status}`\n"
                msg += f"Last update: `{ts[:19] if ts else 'N/A'}`\n"
                msg += f"Open positions: `{open_positions}`\n\n"
                msg += "Система работает и мониторит рынок! 🚀"
            else:
                msg = "⚠️ Система не запущена или нет данных о здоровье"

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in status command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка получения статуса: {e}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages from keyboard buttons."""
        text = update.message.text

        if text == "💰 Баланс":
            await self.balance(update, context)
        elif text == "📈 Статус":
            await self.status(update, context)
        elif text == "📊 Сделки":
            await self.trades(update, context)
        elif text == "📍 Позиция":
            await self.position(update, context)
        elif text == "🔄 Обновить":
            await self.balance(update, context)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button clicks."""
        query = update.callback_query

        # Create a fake update object with the original message for command handlers
        from telegram import Message
        fake_update = update
        if query.message:
            # Create a proper update with message
            fake_update = Update(
                update_id=update.update_id,
                message=query.message
            )

        if query.data == "cmd_balance":
            await query.answer()
            await self.balance(fake_update, context)
        elif query.data == "cmd_status":
            await query.answer()
            await self.status(fake_update, context)
        elif query.data == "cmd_trades":
            await query.answer()
            await self.trades(fake_update, context)
        elif query.data == "refresh_balance":
            await query.answer("Баланс обновлён!")
            await self.balance(fake_update, context)
        elif query.data.startswith("refresh_position_"):
            trade_id = int(query.data.split("_")[-1])
            await query.answer("Позиция обновлена!")
            # Create a fake update with message for position command
            fake_update = Update(
                update_id=update.update_id,
                message=query.message
            )
            await self.position(fake_update, context)

    def send_trade_notification(self, message: str):
        """Send trade notification to chat."""
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code != 200:
                logger.warning(f"Failed to send Telegram message: {response.text}")
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")

    def run(self):
        """Start the bot."""
        logger.info("Starting Telegram bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def create_bot(token: str, chat_id: str, db_path: str) -> TradingBot:
    """Create and return TradingBot instance."""
    return TradingBot(token=token, chat_id=chat_id, db_path=db_path)
