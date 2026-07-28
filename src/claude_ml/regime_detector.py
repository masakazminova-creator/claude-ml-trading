from __future__ import annotations


def classify_regime(row) -> dict:
    trend_strength = float(row.get("ema_8_vs_21", 0.0) or 0.0)
    ema_slope = float(row.get("ema_slope_8", 0.0) or 0.0)
    realized_vol = float(row.get("realized_vol_12", 0.0) or 0.0)
    spread_bps = float(row.get("ob_spread_bps", 0.0) or 0.0)
    imbalance = float(row.get("ob_imbalance_top_10", 0.0) or 0.0)
    flow = float(row.get("trade_flow_imbalance", 0.0) or 0.0)
    range_pct = float(row.get("range_pct", 0.0) or 0.0)

    if realized_vol < 0.003:
        volatility_regime = "низкая_волатильность"
    elif realized_vol > 0.015 or range_pct > 0.012:
        volatility_regime = "высокая_волатильность"
    else:
        volatility_regime = "нормальная_волатильность"

    if realized_vol < 0.002 and abs(trend_strength) < 0.0015:
        structure_regime = "squeeze"
    elif abs(trend_strength) < 0.0025 and abs(ema_slope) < 0.0007:
        structure_regime = "chop"
    elif trend_strength > 0.004 and ema_slope > 0:
        structure_regime = "trend_up"
    elif trend_strength < -0.004 and ema_slope < 0:
        structure_regime = "trend_down"
    elif volatility_regime == "высокая_волатильность":
        structure_regime = "expansion"
    else:
        structure_regime = "flat"

    if spread_bps > 12:
        liquidity_regime = "широкий_спред"
    else:
        liquidity_regime = "нормальный_спред"

    if imbalance > 0.05 and flow > 0.03:
        direction_bias = "лонг_поддержка"
    elif imbalance < -0.05 and flow < -0.03:
        direction_bias = "шорт_давление"
    else:
        direction_bias = "нейтрально"

    # For 5m live trading, blocking every low-volatility bar starves the
    # strategy. Keep the spread and squeeze protections, but allow chop/flat
    # low-vol bars through so the model can actually emit signals.
    allow_entries = liquidity_regime == "нормальный_спред" and structure_regime not in {"squeeze"}

    return {
        "volatility_regime": volatility_regime,
        "structure_regime": structure_regime,
        "liquidity_regime": liquidity_regime,
        "direction_bias": direction_bias,
        "allow_entries": allow_entries,
    }
