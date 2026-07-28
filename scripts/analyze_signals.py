#!/usr/bin/env python
"""
Analyze all trading signals (including skipped ones) to understand system behavior.

Shows:
- Total signals generated
- Signals by decision (ENTER vs SKIP)
- Average confidence for each decision type
- Signals by market regime
- Recent missed opportunities

Usage:
    python scripts/analyze_signals.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import sqlite3
from claude_ml.config import Settings


def analyze_signals():
    """Analyze signal history from database."""
    settings = Settings()
    conn = sqlite3.connect(settings.runtime_db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("SIGNAL ANALYSIS REPORT")
    print("=" * 80)

    # Check if signal_log table exists
    cursor.execute("""
        SELECT count(*) FROM sqlite_master WHERE type='table' AND name='signal_log'
    """)
    if cursor.fetchone()[0] == 0:
        print("\nNo signal log data found.")
        print("Signal logging will be enabled in next runtime restart.")
        conn.close()
        return

    # Total signals
    cursor.execute("SELECT COUNT(*) FROM signal_log")
    total = cursor.fetchone()[0]
    print(f"\nTotal signals logged: {total}")

    if total == 0:
        print("No signals recorded yet. System is waiting for market conditions.")
        conn.close()
        return

    # By decision
    print("\n--- SIGNALS BY DECISION ---")
    cursor.execute("""
        SELECT
            decision,
            COUNT(*) as count,
            AVG(confidence_pct) as avg_confidence,
            AVG(confirm_score) as avg_confirm_score
        FROM signal_log
        GROUP BY decision
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]:6} | Count: {row[1]:4} | Avg Confidence: {row[2]:5.1f}% | Avg Confirm Score: {row[3]:5.2f}")

    # By regime
    print("\n--- SIGNALS BY REGIME ---")
    cursor.execute("""
        SELECT
            regime,
            COUNT(*) as count,
            SUM(CASE WHEN decision='ENTER' THEN 1 ELSE 0 END) as enters,
            SUM(CASE WHEN decision='SKIP' THEN 1 ELSE 0 END) as skips
        FROM signal_log
        GROUP BY regime
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]:12} | Total: {row[1]:4} | Enters: {row[2]:3} | Skips: {row[3]:3}")

    # Recent missed signals (high confidence but skipped)
    print("\n--- RECENT HIGH-CONFIDENCE SKIPS (>50%) ---")
    cursor.execute("""
        SELECT ts, symbol, side, confirm_score, confirm_threshold, confidence_pct
        FROM signal_log
        WHERE decision='SKIP' AND confidence_pct > 50
        ORDER BY ts DESC
        LIMIT 10
    """)
    signals = cursor.fetchall()
    if signals:
        for sig in signals:
            print(f"  {sig[0][:19]} | {sig[1]} | {sig[2]:4} | Score: {sig[3]:.2f} | Threshold: {sig[4]:.2f} | Conf: {sig[5]:.1f}%")
    else:
        print("  No high-confidence skips found.")

    # Actual trades
    print("\n--- ACTUAL TRADES ---")
    cursor.execute("""
        SELECT entry_ts, symbol, side, entry_price, pnl_pct, exit_reason
        FROM paper_trades
        WHERE status IN ('closed', 'shadow_closed') AND pnl_pct IS NOT NULL
        ORDER BY id DESC
        LIMIT 10
    """)
    trades = cursor.fetchall()
    if trades:
        for trade in trades:
            pnl_sign = "+" if trade[4] >= 0 else ""
            print(f"  {trade[0][:19]} | {trade[1]} | {trade[2]:4} | ${trade[3]:>10.2f} | PnL: {pnl_sign}{trade[4]:.2f}% | {trade[5]}")
    else:
        print("  No closed trades yet.")

    print("\n" + "=" * 80)
    conn.close()


if __name__ == "__main__":
    analyze_signals()
