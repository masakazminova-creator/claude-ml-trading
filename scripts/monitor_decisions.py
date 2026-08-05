#!/usr/bin/env python
"""
Monitor and analyze all model decisions (ENTER, SKIP, WAIT) from signal_audit_log.

Usage:
    python scripts/monitor_decisions.py [--hours N] [--symbol SYMBOL]

Shows decision distribution, missed opportunities, and threshold analysis.
"""

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def connect_db():
    """Connect to runtime database."""
    db_path = Path(__file__).parent.parent / "data" / "runtime.sqlite"
    return sqlite3.connect(db_path)


def get_recent_decisions(cursor, hours=24, symbol="BTCUSDT"):
    """Get recent decisions with full details."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    cursor.execute("""
        SELECT ts, action, early_probability, confirmation_probability, momentum_score,
               adaptive_early_threshold, adaptive_confirmation_threshold,
               adaptive_momentum_threshold, regime, close_price, atr_pct,
               json_extract(payload_json, '$.confidence_pct') as confidence_pct,
               json_extract(payload_json, '$.position_size_pct') as position_size_pct
        FROM signal_audit_log
        WHERE ts >= ? AND symbol = ?
        ORDER BY ts DESC
    """, (since.isoformat(), symbol))
    return cursor.fetchall()


def analyze_decisions(decisions):
    """Analyze decision distribution and statistics."""
    if not decisions:
        print("No decisions found in the specified time period")
        return

    # Count by action type
    action_counts = {}
    action_scores = {
        'enter': {'early': [], 'confirm': [], 'momentum': []},
        'skip': {'early': [], 'confirm': [], 'momentum': []},
        'wait': {'early': [], 'confirm': [], 'momentum': []}
    }

    for row in decisions:
        action = row[1].lower()
        action_counts[action] = action_counts.get(action, 0) + 1

        # Collect scores by action type
        if action in action_scores:
            action_scores[action]['early'].append(row[2])
            action_scores[action]['confirm'].append(row[3])
            action_scores[action]['momentum'].append(row[4])

    # Print summary
    print("=" * 80)
    print(f"DECISION MONITORING REPORT (Last {len(decisions)} decisions)")
    print("=" * 80)

    print("\n📊 Decision Distribution:")
    total = len(decisions)
    for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total * 100) if total > 0 else 0
        print(f"  {action.upper():10}: {count:3d} ({pct:.1f}%)")

    print(f"\n  Total: {total}")

    # Print score statistics by action type
    print("\n📈 Average Scores by Action Type:")
    for action in ['enter', 'skip', 'wait']:
        scores = action_scores[action]
        if scores['early']:
            avg_early = sum(scores['early']) / len(scores['early'])
            avg_confirm = sum(scores['confirm']) / len(scores['confirm'])
            avg_momentum = sum(scores['momentum']) / len(scores['momentum'])
            print(f"\n  {action.upper()}:")
            print(f"    Early Signal:  {avg_early:.3f} (avg)")
            print(f"    Confirmation:  {avg_confirm:.3f} (avg)")
            print(f"    Momentum:      {avg_momentum:.3f} (avg)")

    # Show latest 5 decisions with details
    print("\n🔍 Latest 5 Decisions:")
    for i, row in enumerate(decisions[:5]):
        ts, action, early, confirm, momentum, thresh_early, thresh_confirm, \
        thresh_momentum, regime, price, atr, conf_pct, pos_size = row

        dt = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
        print(f"\n  {i+1}. {dt.strftime('%Y-%m-%d %H:%M')} - {action.upper()}")
        print(f"     Scores: early={early:.3f}, confirm={confirm:.3f}, momentum={momentum:.3f}")
        print(f"     Thresholds: early={thresh_early:.3f}, confirm={thresh_confirm:.3f}, momentum={thresh_momentum:.3f}")
        print(f"     Regime: {regime}, Price: ${price:.2f}, ATR: {atr:.2f}%")
        if conf_pct:
            print(f"     Confidence: {conf_pct:.0f}%, Position Size: {pos_size*100:.0f}%")


def find_missed_opportunities(cursor, min_return=1.0, limit=10):
    """Find skipped signals where price moved significantly."""
    cursor.execute("""
        SELECT ts, early_probability, confirmation_probability, momentum_score,
               adaptive_confirmation_threshold, regime, close_price,
               json_extract(payload_json, '$.confidence_pct') as confidence_pct
        FROM signal_audit_log
        WHERE action IN ('skip', 'wait')
          AND confirmation_probability >= ?
        ORDER BY confirmation_probability DESC
        LIMIT ?
    """, (min_return, limit))

    rows = cursor.fetchall()
    if rows:
        print("\n" + "=" * 80)
        print("⚠️  MISSED OPPORTUNITIES (Skipped but had decent scores)")
        print("=" * 80)
        for row in rows:
            ts, early, confirm, momentum, thresh, regime, price, conf = row
            dt = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
            print(f"\n  {dt.strftime('%Y-%m-%d %H:%M')} | Confirm: {confirm:.3f} (thresh: {thresh:.3f}) | "
                  f"Confidence: {conf:.0f}% | Regime: {regime} | Price: ${price:.2f}")
            print(f"    Why skipped: confirm < threshold OR bad regime")


def main():
    parser = argparse.ArgumentParser(description="Monitor Claude ML trading decisions")
    parser.add_argument("--hours", type=int, default=24, help="Time window in hours (default: 24)")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Trading symbol (default: BTCUSDT)")
    args = parser.parse_args()

    conn = connect_db()
    cursor = conn.cursor()

    # Get recent decisions
    decisions = get_recent_decisions(cursor, args.hours, args.symbol)

    # Analyze and display
    analyze_decisions(decisions)

    # Find missed opportunities
    find_missed_opportunities(cursor)

    conn.close()


if __name__ == "__main__":
    main()
