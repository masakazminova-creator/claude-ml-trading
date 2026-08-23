"""
Tests for the shared position-close logic (RuntimeEngine._close_position).

Covers:
- Close fills at the given exit level (not bar close).
- Idempotency: a second close attempt (race between main cycle and fast
  stop-checker) returns False and does NOT double-close / re-alert.
"""

import sqlite3
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_ml.runtime import RuntimeEngine
from claude_ml.trailing_stop import create_trailing_stop


def _no_network(*_args, **_kwargs):
    """Stub for requests.post so _close_position doesn't hit Telegram in tests."""
    return SimpleNamespace(status_code=200, text="ok")


requests.post = _no_network


class _FakeRuntime:
    """Minimal stand-in exposing the attributes _close_position touches."""

    def __init__(self, conn, trailing_stops):
        self.conn = conn
        self.trailing_stops = trailing_stops
        self._stop_lock = threading.Lock()
        self.settings = SimpleNamespace(
            fee_bps=5,
            slippage_bps=2,
            telegram_bot_token="test",
            telegram_chat_id="1",
        )


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, entry_ts TEXT, entry_price REAL,
            stage TEXT, signal_probability REAL, take_profit_pct REAL,
            stop_loss_pct REAL, payload_json TEXT, status TEXT,
            exit_ts TEXT, exit_price REAL, exit_reason TEXT, pnl_pct REAL,
            hold_bars INTEGER
        )
    """)
    return conn


def test_close_position_fills_at_level_and_closes():
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (symbol, side, entry_ts, entry_price, status) VALUES (?,?,?,?,?)",
        ("BTCUSDT", "long", "2026-01-01T00:00:00+00:00", 50000.0, "open"),
    )
    conn.commit()

    state = create_trailing_stop("BTCUSDT", "long", 50000.0, 500.0)
    state.initial_sl = 49500.0
    trailing_stops = {"BTCUSDT": state}
    rt = _FakeRuntime(conn, trailing_stops)

    ok = RuntimeEngine._close_position(
        rt, "BTCUSDT", state, 49500.0,
        exit_reason="fixed_stop_loss", title="STOP LOSS HIT",
        reason_label="Fixed Stop Loss", level_label="SL Level",
    )

    assert ok is True
    assert "BTCUSDT" not in trailing_stops

    row = conn.execute("SELECT * FROM paper_trades WHERE symbol='BTCUSDT'").fetchone()
    assert row["status"] == "closed"
    assert row["exit_reason"] == "fixed_stop_loss"
    assert row["exit_price"] == 49500.0
    # loss: (49500-50000)/50000 = -1.0% gross, minus ~0.07% cost -> slightly below -1%
    assert row["pnl_pct"] < -0.9


def test_close_position_is_idempotent_no_double_close():
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (symbol, side, entry_ts, entry_price, status) VALUES (?,?,?,?,?)",
        ("BTCUSDT", "long", "2026-01-01T00:00:00+00:00", 50000.0, "open"),
    )
    conn.commit()

    state = create_trailing_stop("BTCUSDT", "long", 50000.0, 500.0)
    state.initial_sl = 49500.0
    trailing_stops = {"BTCUSDT": state}
    rt = _FakeRuntime(conn, trailing_stops)

    first = RuntimeEngine._close_position(
        rt, "BTCUSDT", state, 49500.0,
        exit_reason="fixed_stop_loss", title="STOP LOSS HIT",
        reason_label="Fixed Stop Loss", level_label="SL Level",
    )
    second = RuntimeEngine._close_position(
        rt, "BTCUSDT", state, 49500.0,
        exit_reason="fixed_stop_loss", title="STOP LOSS HIT",
        reason_label="Fixed Stop Loss", level_label="SL Level",
    )

    assert first is True
    assert second is False  # already closed -> no double-close/alerts

    # Exactly one closed row
    rows = conn.execute("SELECT COUNT(*) AS n FROM paper_trades WHERE status='closed'").fetchone()
    assert rows["n"] == 1
