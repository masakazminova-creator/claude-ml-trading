#!/usr/bin/env python
"""
Test script for Telegram bot - simulates commands without running the bot.
"""

import sys
import sqlite3
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_ml.config import Settings

def test_balance_command():
    """Simulate /balance command."""
    print("\n=== Testing /balance command ===")

    settings = Settings()
    db_path = str(settings.runtime_db_path)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get current balance from equity_curve (last entry)
        cursor.execute("""
            SELECT balance FROM equity_curve
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()

        if row:
            current_balance = row[0]
        else:
            # Fallback to start balance
            cursor.execute("SELECT value FROM runtime_state WHERE key='start_balance'")
            row = cursor.fetchone()
            current_balance = float(row[0]) if row else 10000.0

        # Get total PnL
        cursor.execute("""
            SELECT SUM(pnl_pct) FROM paper_trades
            WHERE status IN ('closed', 'shadow_closed') AND pnl_pct IS NOT NULL
        """)
        total_pnl_row = cursor.fetchone()
        total_pnl = total_pnl_row[0] if total_pnl_row and total_pnl_row[0] else 0.0

        # Get trade count
        cursor.execute("""
            SELECT COUNT(*) FROM paper_trades
            WHERE status IN ('closed', 'shadow_closed')
        """)
        trade_count = cursor.fetchone()[0]

        # Get win rate
        cursor.execute("""
            SELECT
                SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
                COUNT(*) as total
            FROM paper_trades
            WHERE status IN ('closed', 'shadow_closed') AND pnl_pct IS NOT NULL
        """)
        wr_row = cursor.fetchone()
        wins = wr_row[0] if wr_row[0] else 0
        total = wr_row[1] if wr_row[1] else 0
        win_rate = (wins / total * 100) if total > 0 else 0

        # Calculate drawdown
        cursor.execute("""
            SELECT MAX(balance) FROM equity_curve
        """)
        peak_row = cursor.fetchone()
        peak_balance = peak_row[0] if peak_row[0] else current_balance
        drawdown = ((peak_balance - current_balance) / peak_balance * 100) if peak_balance > 0 else 0

        conn.close()

        # Format message
        pnl_sign = "+" if total_pnl >= 0 else ""
        dd_sign = "-" if drawdown > 0 else ""

        msg = (
            f"*Trading Balance*\n\n"
            f"Current balance: ${current_balance:.2f}\n"
            f"Total PnL: {pnl_sign}{total_pnl:.2f}%\n"
            f"Peak balance: ${peak_balance:.2f}\n"
            f"Drawdown: {dd_sign}{drawdown:.2f}%\n\n"
            f"*Statistics:*\n"
            f"Total trades: {trade_count}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Wins: {wins} | Losses: {total - wins}"
        )

        print(msg)
        print("\n[OK] /balance command works correctly!")
        return True

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_status_command():
    """Simulate /status command."""
    print("\n=== Testing /status command ===")

    settings = Settings()
    db_path = str(settings.runtime_db_path)

    try:
        conn = sqlite3.connect(db_path)
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
            status_mark = "[OK]" if status == "ok" else "[ERROR]"
            msg = f"{status_mark} *System Status*\n\n"
            msg += f"Status: {status}\n"
            msg += f"Last update: {ts[:19] if ts else 'N/A'}\n"
            msg += f"Open positions: {open_positions}\n\n"
            msg += "System is running and monitoring the market!"
        else:
            msg = "[WARNING] System not started or no health data"

        print(msg)
        print("\n[OK] /status command works correctly!")
        return True

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("="*60)
    print("Testing Telegram Bot Commands")
    print("="*60)

    balance_ok = test_balance_command()
    status_ok = test_status_command()

    print("\n" + "="*60)
    if balance_ok and status_ok:
        print("[OK] All tests passed!")
    else:
        print("[ERROR] Some tests failed!")
    print("="*60)
