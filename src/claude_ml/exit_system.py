from __future__ import annotations

from typing import Any

import pandas as pd


def evaluate_soft_exit_decision(
    side: str,
    current_pnl_pct: float,
    progress_ratio: float,
    probability: float,
    threshold: float,
    micro: dict[str, float],
    min_unrealized_pnl_pct: float,
    max_progress_ratio: float,
) -> dict[str, Any]:
    spread_bps = float(micro.get("ob_spread_bps", 0.0) or 0.0)
    imbalance = float(micro.get("ob_imbalance_top_10", 0.5) or 0.5)
    buy_ratio = float(micro.get("trade_buy_ratio", 0.5) or 0.5)
    flow = float(micro.get("trade_flow_imbalance", 0.0) or 0.0)
    trade_count_norm = float(micro.get("trade_count_norm", 0.3) or 0.3)

    adverse_flags: list[str] = []
    if side == "long":
        if imbalance < 0.48:
            adverse_flags.append("orderbook_imbalance")
        if buy_ratio < 0.48:
            adverse_flags.append("buy_ratio")
        if flow < -0.05:
            adverse_flags.append("trade_flow")
    else:
        if imbalance > 0.52:
            adverse_flags.append("orderbook_imbalance")
        if buy_ratio > 0.52:
            adverse_flags.append("buy_ratio")
        if flow > 0.05:
            adverse_flags.append("trade_flow")
    if trade_count_norm < 0.22:
        adverse_flags.append("thin_activity")
    if spread_bps > 2.5:
        adverse_flags.append("wide_spread")

    if side == "long":
        min_unrealized_pnl_pct = min_unrealized_pnl_pct - 0.03
        max_progress_ratio = max_progress_ratio - 0.03
        adverse_micro = len(adverse_flags) >= 2
        strong_probability_break = probability < threshold * 0.68 or (threshold - probability) >= 0.42
        pending_probability_break = probability < threshold * 0.74 or (threshold - probability) >= 0.32
    else:
        adverse_micro = len(adverse_flags) >= 1
        strong_probability_break = probability < threshold * 0.72 or (threshold - probability) >= 0.38
        pending_probability_break = probability < threshold * 0.78 or (threshold - probability) >= 0.28

    stalled_trade = current_pnl_pct <= min_unrealized_pnl_pct and progress_ratio <= max_progress_ratio
    weak_probability = probability < threshold * 0.75
    threshold_gap = threshold - probability
    immediate_exit = stalled_trade and adverse_micro and strong_probability_break
    pending_exit = stalled_trade and adverse_micro and pending_probability_break and not immediate_exit
    return {
        "should_exit": immediate_exit,
        "should_arm": pending_exit,
        "stalled_trade": stalled_trade,
        "weak_probability": weak_probability,
        "adverse_micro": adverse_micro,
        "adverse_flags": adverse_flags,
        "threshold_gap": threshold_gap,
        "strong_probability_break": strong_probability_break,
        "pending_probability_break": pending_probability_break,
        "current_pnl_pct": current_pnl_pct,
        "progress_ratio": progress_ratio,
        "probability": probability,
        "threshold": threshold,
        "micro": {
            "ob_spread_bps": spread_bps,
            "ob_imbalance_top_10": imbalance,
            "trade_buy_ratio": buy_ratio,
            "trade_flow_imbalance": flow,
            "trade_count_norm": trade_count_norm,
        },
    }


def review_soft_exit_window(
    side: str,
    entry_price: float,
    exit_pnl_pct: float,
    active_take_profit_price: float,
    active_stop_price: float,
    future_bars: pd.DataFrame,
) -> dict[str, Any]:
    bars = future_bars.reset_index(drop=True)
    if bars.empty:
        return {"finalized": False, "bars_seen": 0}

    first_event = None
    would_hit_tp = False
    would_hit_stop = False

    for _, row in bars.iterrows():
        high_price = float(row["high"])
        low_price = float(row["low"])
        if side == "long":
            tp_hit = high_price >= active_take_profit_price
            stop_hit = low_price <= active_stop_price
        else:
            tp_hit = low_price <= active_take_profit_price
            stop_hit = high_price >= active_stop_price
        would_hit_tp = would_hit_tp or tp_hit
        would_hit_stop = would_hit_stop or stop_hit
        if first_event is None:
            if tp_hit and stop_hit:
                first_event = "ambiguous"
            elif tp_hit:
                first_event = "take_profit"
            elif stop_hit:
                first_event = "stop_loss"

    highs = bars["high"].astype(float)
    lows = bars["low"].astype(float)
    if side == "long":
        best_price = float(highs.max())
        worst_price = float(lows.min())
        best_future_pnl_pct = ((best_price / entry_price) - 1.0) * 100
        worst_future_pnl_pct = ((worst_price / entry_price) - 1.0) * 100
    else:
        best_price = float(lows.min())
        worst_price = float(highs.max())
        best_future_pnl_pct = ((entry_price / best_price) - 1.0) * 100
        worst_future_pnl_pct = ((entry_price / worst_price) - 1.0) * 100

    improvement_pct = best_future_pnl_pct - exit_pnl_pct
    avoided_loss_pct = exit_pnl_pct - worst_future_pnl_pct
    if first_event == "take_profit" and improvement_pct >= 0.10:
        verdict = "premature"
    elif first_event == "stop_loss" and avoided_loss_pct >= 0.10:
        verdict = "justified"
    elif would_hit_tp and improvement_pct >= 0.15 and not would_hit_stop:
        verdict = "premature"
    elif would_hit_stop and avoided_loss_pct >= 0.15 and not would_hit_tp:
        verdict = "justified"
    else:
        verdict = "neutral"

    return {
        "finalized": True,
        "bars_seen": len(bars),
        "first_event": first_event or "none",
        "would_hit_take_profit": would_hit_tp,
        "would_hit_stop_loss": would_hit_stop,
        "best_future_pnl_pct": best_future_pnl_pct,
        "worst_future_pnl_pct": worst_future_pnl_pct,
        "improvement_pct": improvement_pct,
        "avoided_loss_pct": avoided_loss_pct,
        "verdict": verdict,
        "active_take_profit_price": active_take_profit_price,
        "active_stop_price": active_stop_price,
    }
