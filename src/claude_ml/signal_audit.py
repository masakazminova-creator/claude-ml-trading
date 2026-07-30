"""
Signal Audit System - Track ALL signals (including skipped ones) and their potential outcomes.

Purpose: Log every signal the system generates with:
- Model probabilities/scores
- Thresholds at that time
- What would have happened if we entered
- Actual outcome when trade is closed

This helps analyze:
- How many signals were missed
- What thresholds were used
- Win rate of signals above/below threshold
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class SignalAuditEngine:
    """Logs all trading signals for post-hoc analysis."""

    def __init__(self, settings):
        self.settings = settings
        self.conn = sqlite3.connect(settings.runtime_db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create audit logging tables."""
        # Log all signals (even skipped ones)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                decision TEXT NOT NULL,
                early_score REAL,
                confirm_score REAL,
                momentum_score REAL,
                early_threshold REAL,
                confirm_threshold REAL,
                momentum_threshold REAL,
                regime TEXT,
                atr_pct REAL,
                confidence_pct REAL,
                position_size_pct REAL,
                entry_price REAL,
                exit_price REAL,
                pnl_pct REAL,
                exit_reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def log_signal(
        self,
        ts: str,
        symbol: str,
        side: str,
        decision: str,  # 'ENTER' or 'SKIP'
        early_score: float,
        confirm_score: float,
        momentum_score: float,
        early_threshold: float,
        confirm_threshold: float,
        momentum_threshold: float,
        regime: str,
        atr_pct: float,
        confidence_pct: float,
        position_size_pct: float,
        entry_price: Optional[float] = None,
    ) -> None:
        """Log a signal with full context."""
        self.conn.execute("""
            INSERT INTO signal_log (
                ts, symbol, side, decision,
                early_score, confirm_score, momentum_score,
                early_threshold, confirm_threshold, momentum_threshold,
                regime, atr_pct, confidence_pct, position_size_pct,
                entry_price
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts, symbol, side, decision,
            early_score, confirm_score, momentum_score,
            early_threshold, confirm_threshold, momentum_threshold,
            regime, atr_pct, confidence_pct, position_size_pct,
            entry_price
        ))
        self.conn.commit()

    def update_signal_outcome(
        self,
        signal_id: int,
        exit_price: float,
        pnl_pct: float,
        exit_reason: str,
    ) -> None:
        """Update a logged signal with actual outcome."""
        self.conn.execute("""
            UPDATE signal_log
            SET exit_price = ?, pnl_pct = ?, exit_reason = ?
            WHERE id = ?
        """, (exit_price, pnl_pct, exit_reason, signal_id))
        self.conn.commit()

    def get_missed_signals(
        self,
        symbol: str = "BTCUSDT",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent signals that were skipped."""
        rows = self.conn.execute("""
            SELECT * FROM signal_log
            WHERE symbol = ? AND decision = 'SKIP'
            ORDER BY ts DESC
            LIMIT ?
        """, (symbol, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_signal_stats(self) -> Dict[str, Any]:
        """Get statistics on all logged signals."""
        stats = {}

        # Total signals by decision
        row = self.conn.execute("""
            SELECT decision, COUNT(*) as count, AVG(confidence_pct) as avg_conf
            FROM signal_log
            GROUP BY decision
        """).fetchone()
        stats['by_decision'] = dict(row) if row else {}

        # Signals by regime
        row = self.conn.execute("""
            SELECT regime, COUNT(*) as count
            FROM signal_log
            GROUP BY regime
        """).fetchone()
        stats['by_regime'] = dict(row) if row else {}

        return stats

    def close(self):
        """Close database connection."""
        self.conn.close()
                adaptive_confirmation_threshold REAL,
                adaptive_momentum_threshold REAL,

                -- Decision
                action TEXT NOT NULL,  -- 'enter', 'skip', 'wait'
                action_reason TEXT,    -- Why this action was taken

                -- Features snapshot (JSON)
                features_json TEXT,

                -- What would have happened
                next_1bar_return REAL,
                next_3bar_return REAL,
                next_6bar_return REAL,
                next_high REAL,
                next_low REAL,

                payload_json TEXT
            )
        """)
        self.conn.commit()

    def log_decision(
        self,
        ts: str,
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
        action_reason: str,
        features_dict: Dict[str, float],
        future_data: Dict[str, Any],
    ) -> None:
        """
        Log one decision point with full context.

        Args:
            ts: Timestamp
            symbol: Trading symbol
            close_price: Current close price
            atr_pct: ATR as percentage
            regime: Current market regime
            early_prob: Early signal probability
            confirm_prob: Confirmation probability
            momentum_score: Momentum model score
            adaptive_early_thresh: Current adaptive threshold
            adaptive_confirm_thresh: Current adaptive confirmation threshold
            adaptive_momentum_thresh: Current adaptive momentum threshold
            action: 'enter', 'skip', or 'wait'
            action_reason: Why this action was taken
            features_dict: Key features at this moment
            future_data: What happened next (for analysis)
        """
        self.conn.execute("""
            INSERT INTO signal_audit_log (
                ts, symbol, close_price, atr_pct, regime,
                early_probability, confirmation_probability, momentum_score,
                adaptive_early_threshold, adaptive_confirmation_threshold, adaptive_momentum_threshold,
                action, action_reason,
                features_json,
                next_1bar_return, next_3bar_return, next_6bar_return,
                next_high, next_low,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts,
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
            action_reason,
            json.dumps(features_dict),
            future_data.get('next_1bar_return'),
            future_data.get('next_3bar_return'),
            future_data.get('next_6bar_return'),
            future_data.get('next_high'),
            future_data.get('next_low'),
            json.dumps(future_data),
        ))
        self.conn.commit()

    def query_by_time(self, start_ts: str, end_ts: str, symbol: str = "BTCUSDT") -> List[Dict]:
        """
        Query audit log for a specific time period.

        Args:
            start_ts: Start timestamp (ISO format)
            end_ts: End timestamp (ISO format)
            symbol: Symbol to query

        Returns:
            List of audit records
        """
        rows = self.conn.execute("""
            SELECT * FROM signal_audit_log
            WHERE ts >= ? AND ts <= ? AND symbol = ?
            ORDER BY ts
        """, (start_ts, end_ts, symbol)).fetchall()

        return [dict(r) for r in rows]

    def find_missed_signals(
        self,
        min_future_return: float = 1.0,
        limit: int = 20
    ) -> List[Dict]:
        """
        Find times when model skipped but price moved significantly.

        Args:
            min_future_return: Minimum future return % to consider as "missed"
            limit: Max results to return

        Returns:
            List of missed opportunities
        """
        # Look for skips where price moved up after
        rows = self.conn.execute("""
            SELECT * FROM signal_audit_log
            WHERE action IN ('skip', 'wait')
              AND next_6bar_return >= ?
            ORDER BY next_6bar_return DESC
            LIMIT ?
        """, (min_future_return, limit)).fetchall()

        return [dict(r) for r in rows]

    def analyze_missed_signal(self, ts: str, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """
        Get detailed analysis of why a specific signal was missed.

        Args:
            ts: Timestamp of interest
            symbol: Symbol

        Returns:
            Detailed analysis dict
        """
        row = self.conn.execute("""
            SELECT * FROM signal_audit_log
            WHERE ts = ? AND symbol = ?
        """, (ts, symbol)).fetchone()

        if not row:
            return {"error": "No data found for this timestamp"}

        record = dict(row)

        # Parse features
        features = json.loads(record['features_json'])
        payload = json.loads(record['payload_json'])

        # Analyze why signal was skipped
        analysis = {
            "timestamp": ts,
            "symbol": symbol,
            "action_taken": record['action'],
            "reason": record['action_reason'],

            # Thresholds vs probabilities
            "probabilities": {
                "early": record['early_probability'],
                "confirmation": record['confirmation_probability'],
                "momentum": record['momentum_score'],
            },
            "thresholds": {
                "early": record['adaptive_early_threshold'],
                "confirmation": record['adaptive_confirmation_threshold'],
                "momentum": record['adaptive_momentum_threshold'],
            },
            "why_skipped": [],

            # Market context
            "market_context": {
                "regime": record['regime'],
                "close_price": record['close_price'],
                "atr_pct": record['atr_pct'],
            },

            # What happened after
            "outcome": {
                "next_1bar_return": record['next_1bar_return'],
                "next_3bar_return": record['next_3bar_return'],
                "next_6bar_return": record['next_6bar_return'],
                "next_high": record['next_high'],
                "next_low": record['next_low'],
            },

            # Feature values
            "features": features,
        }

        # Determine why signal was skipped
        if record['confirmation_probability'] < record['adaptive_confirmation_threshold']:
            analysis["why_skipped"].append(
                f"Confirmation prob ({record['confirmation_probability']:.3f}) < threshold ({record['adaptive_confirmation_threshold']:.3f})"
            )

        if record['early_probability'] < record['adaptive_early_threshold']:
            analysis["why_skipped"].append(
                f"Early signal too weak ({record['early_probability']:.3f} < {record['adaptive_early_threshold']:.3f})"
            )

        if record['momentum_score'] < record['adaptive_momentum_threshold']:
            analysis["why_skipped"].append(
                f"Momentum against us ({record['momentum_score']:.3f} < {record['adaptive_momentum_threshold']:.3f})"
            )

        if record['regime'] in ['chop', 'flat']:
            analysis["why_skipped"].append(
                f"Bad regime: {record['regime']} (thresholds raised)"
            )

        return analysis

    def generate_report(self, start_ts: str, end_ts: str, symbol: str = "BTCUSDT") -> str:
        """
        Generate human-readable report for a time period.

        Args:
            start_ts: Start timestamp
            end_ts: End timestamp
            symbol: Symbol

        Returns:
            Formatted report string
        """
        records = self.query_by_time(start_ts, end_ts, symbol)

        if not records:
            return f"No audit data found for {start_ts} to {end_ts}"

        report = []
        report.append(f"\n{'='*80}")
        report.append(f"SIGNAL AUDIT REPORT: {symbol}")
        report.append(f"Period: {start_ts} to {end_ts}")
        report.append(f"Total bars analyzed: {len(records)}")
        report.append(f"{'='*80}\n")

        # Summary stats
        actions = {}
        for r in records:
            action = r['action']
            actions[action] = actions.get(action, 0) + 1

        report.append("Action Distribution:")
        for action, count in actions.items():
            report.append(f"  {action}: {count} bars")

        # Show skipped signals that had good outcomes
        missed = self.find_missed_signals(min_future_return=1.0, limit=5)
        if missed:
            report.append(f"\nTop 5 Missed Opportunities:")
            for m in missed:
                report.append(f"  {m['ts']}: Skipped, but price moved +{m['next_6bar_return']:.2f}%")
                report.append(f"    Reason: {m['action_reason']}")
                report.append(f"    Confirm prob: {m['confirmation_probability']:.3f} vs threshold: {m['adaptive_confirmation_threshold']:.3f}")

        return "\n".join(report)

    def close(self):
        """Close database connection."""
        self.conn.close()
