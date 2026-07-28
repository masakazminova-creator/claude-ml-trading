from __future__ import annotations

import math

import pandas as pd


FEATURE_COLUMNS = [
    # Returns
    "ret_1",
    "ret_2",
    "ret_3",
    "ret_6",
    "ret_12",
    # Range/Body
    "range_pct",
    "body_pct",
    # Volatility
    "atr_pct_14",
    "realized_vol_12",
    # Volume
    "vol_zscore",
    "turnover_zscore",
    # EMAs
    "close_vs_ema_8",
    "close_vs_ema_21",
    "ema_8_vs_21",
    "ema_slope_8",
    # RSI
    "rsi_14",
    # Position in range
    "dist_from_rolling_high_20",
    "dist_from_rolling_low_20",
    "recent_range_progress_6",
    # Momentum
    "impulse_1_vs_3",
    "range_expansion_vs_atr",
    "ema_gap_change_3",
    "bar_close_position",
    # Multi-timeframe
    "close_vs_tf5_close",
    "close_vs_tf60_close",
    "tf60_ret_3",
    "tf60_rsi_14",
    # Time features
    "hour_sin",
    "hour_cos",
    "dow",
    "session_asia",
    "session_eu",
    "session_us",
    # Microstructure
    "ob_spread_bps",
    "ob_imbalance_top_10",
    "ob_bid_depth_ratio",
    "trade_buy_ratio",
    "trade_flow_imbalance",
    "trade_large_ratio",
    "trade_count_norm",
    # === EARLY DETECTION FEATURES (NEW) ===
    # Range compression
    "atr_slope_3",
    "atr_slope_6",
    "range_compression",
    # Volume trends
    "volume_slope_3",
    "volume_slope_6",
    "volume_drying",
    # Order book accumulation
    "ob_imbalance_trend_3",
    "ob_imbalance_trend_6",
    "ob_accumulation_score",
    # MTF alignment forming
    "mtf_alignment_forming",
    "ema_convergence_ratio",
    # Momentum divergence
    "rsi_divergence_score",
    "price_momentum_vs_rsi",
    # Extreme positions
    "extreme_close_position",
    "distance_from_vwap",
    # Breakout potential
    "bollinger_width_pct",
    "keltner_position",
    "donchian_breakout_score",
]

FEATURE_DEFAULTS = {
    # Returns
    "ret_1": 0.0,
    "ret_2": 0.0,
    "ret_3": 0.0,
    "ret_6": 0.0,
    "ret_12": 0.0,
    # Range/Body
    "range_pct": 0.0,
    "body_pct": 0.0,
    # Volatility
    "atr_pct_14": 0.0,
    "realized_vol_12": 0.0,
    # Volume
    "vol_zscore": 0.0,
    "turnover_zscore": 0.0,
    # EMAs
    "close_vs_ema_8": 0.0,
    "close_vs_ema_21": 0.0,
    "ema_8_vs_21": 0.0,
    "ema_slope_8": 0.0,
    # RSI
    "rsi_14": 50.0,
    # Position in range
    "dist_from_rolling_high_20": 0.0,
    "dist_from_rolling_low_20": 0.0,
    "recent_range_progress_6": 0.5,
    # Momentum
    "impulse_1_vs_3": 0.0,
    "range_expansion_vs_atr": 0.0,
    "ema_gap_change_3": 0.0,
    "bar_close_position": 0.5,
    # Multi-timeframe
    "close_vs_tf5_close": 0.0,
    "close_vs_tf60_close": 0.0,
    "tf60_ret_3": 0.0,
    "tf60_rsi_14": 50.0,
    # Time features
    "hour_sin": 0.0,
    "hour_cos": 1.0,
    "dow": 0.0,
    "session_asia": 0.0,
    "session_eu": 0.0,
    "session_us": 0.0,
    # Microstructure
    "ob_spread_bps": 5.0,
    "ob_imbalance_top_10": 0.0,
    "ob_bid_depth_ratio": 0.5,
    "trade_buy_ratio": 0.5,
    "trade_flow_imbalance": 0.0,
    "trade_large_ratio": 0.0,
    "trade_count_norm": 0.0,
    # === EARLY DETECTION DEFAULTS (NEW) ===
    "atr_slope_3": 0.0,
    "atr_slope_6": 0.0,
    "range_compression": 0.0,
    "volume_slope_3": 0.0,
    "volume_slope_6": 0.0,
    "volume_drying": 0.0,
    "ob_imbalance_trend_3": 0.0,
    "ob_imbalance_trend_6": 0.0,
    "ob_accumulation_score": 0.0,
    "mtf_alignment_forming": 0.0,
    "ema_convergence_ratio": 1.0,
    "rsi_divergence_score": 0.0,
    "price_momentum_vs_rsi": 0.0,
    "extreme_close_position": 0.0,
    "distance_from_vwap": 0.0,
    "bollinger_width_pct": 0.0,
    "keltner_position": 0.5,
    "donchian_breakout_score": 0.0,
}


def _calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0).rolling(period).mean()
    losses = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gains / losses.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def _prepare_tf_features(frame: pd.DataFrame, suffix: str) -> pd.DataFrame:
    tf = frame.copy().sort_values("ts").reset_index(drop=True)
    tf[f"tf{suffix}_close"] = tf["close"]
    tf[f"tf{suffix}_ret_3"] = tf["close"].pct_change(3)
    tf[f"tf{suffix}_rsi_14"] = _calc_rsi(tf["close"], 14)
    return tf[["ts", f"tf{suffix}_close", f"tf{suffix}_ret_3", f"tf{suffix}_rsi_14"]]


def build_features(
    raw: pd.DataFrame,
    mtf_frames: dict[str, pd.DataFrame] | None = None,
    microstructure_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    # Handle empty dataframe
    if raw.empty:
        return pd.DataFrame()

    df = raw.copy().sort_values("ts").reset_index(drop=True)
    df["ret_1"] = df["close"].pct_change(1)
    df["ret_2"] = df["close"].pct_change(2)
    df["ret_3"] = df["close"].pct_change(3)
    df["ret_6"] = df["close"].pct_change(6)
    df["ret_12"] = df["close"].pct_change(12)
    df["range_pct"] = (df["high"] - df["low"]) / df["close"]
    df["body_pct"] = (df["close"] - df["open"]) / df["open"]
    df["bar_close_position"] = ((df["close"] - df["low"]) / (df["high"] - df["low"]).replace(0, pd.NA)).fillna(0.5)

    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()
    df["atr_pct_14"] = df["atr_14"] / df["close"]
    df["realized_vol_12"] = df["ret_1"].rolling(12).std() * math.sqrt(12)

    df["vol_mean_20"] = df["volume"].rolling(20).mean()
    df["vol_std_20"] = df["volume"].rolling(20).std()
    df["vol_zscore"] = (df["volume"] - df["vol_mean_20"]) / df["vol_std_20"].replace(0, pd.NA)
    df["turnover_mean_20"] = df["turnover"].rolling(20).mean()
    df["turnover_std_20"] = df["turnover"].rolling(20).std()
    df["turnover_zscore"] = (df["turnover"] - df["turnover_mean_20"]) / df["turnover_std_20"].replace(0, pd.NA)

    df["ema_8"] = df["close"].ewm(span=8, adjust=False).mean()
    df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["close_vs_ema_8"] = df["close"] / df["ema_8"] - 1.0
    df["close_vs_ema_21"] = df["close"] / df["ema_21"] - 1.0
    df["ema_8_vs_21"] = df["ema_8"] / df["ema_21"] - 1.0
    df["ema_slope_8"] = df["ema_8"].pct_change(3)
    df["ema_gap_change_3"] = df["ema_8_vs_21"] - df["ema_8_vs_21"].shift(3)
    df["rsi_14"] = _calc_rsi(df["close"], 14)

    df["rolling_high_20"] = df["high"].rolling(20).max()
    df["rolling_low_20"] = df["low"].rolling(20).min()
    df["dist_from_rolling_high_20"] = df["close"] / df["rolling_high_20"] - 1.0
    df["dist_from_rolling_low_20"] = df["close"] / df["rolling_low_20"] - 1.0
    df["recent_low_6"] = df["low"].rolling(6).min()
    df["recent_high_6"] = df["high"].rolling(6).max()
    recent_range_6 = (df["recent_high_6"] - df["recent_low_6"]).replace(0, pd.NA)
    df["recent_range_progress_6"] = ((df["close"] - df["recent_low_6"]) / recent_range_6).fillna(0.5)
    df["impulse_1_vs_3"] = df["ret_1"] - (df["ret_3"] / 3.0)
    df["range_expansion_vs_atr"] = (df["range_pct"] / df["atr_pct_14"].replace(0, pd.NA)).fillna(0.0)

    hours = df["ts"].dt.hour
    df["hour_sin"] = hours.apply(lambda h: math.sin(2 * math.pi * h / 24))
    df["hour_cos"] = hours.apply(lambda h: math.cos(2 * math.pi * h / 24))
    df["dow"] = df["ts"].dt.dayofweek
    df["session_asia"] = ((hours >= 0) & (hours < 8)).astype(int)
    df["session_eu"] = ((hours >= 7) & (hours < 16)).astype(int)
    df["session_us"] = ((hours >= 13) & (hours < 22)).astype(int)

    if mtf_frames:
        if "5" in mtf_frames:
            tf5 = _prepare_tf_features(mtf_frames["5"], "5")
            df = pd.merge_asof(df.sort_values("ts"), tf5.sort_values("ts"), on="ts", direction="backward")
            df["close_vs_tf5_close"] = df["close"] / df["tf5_close"] - 1.0
        if "60" in mtf_frames:
            tf60 = _prepare_tf_features(mtf_frames["60"], "60")
            df = pd.merge_asof(df.sort_values("ts"), tf60.sort_values("ts"), on="ts", direction="backward")
            df["close_vs_tf60_close"] = df["close"] / df["tf60_close"] - 1.0
        if "240" in mtf_frames:
            tf240 = _prepare_tf_features(mtf_frames["240"], "240")
            df = pd.merge_asof(df.sort_values("ts"), tf240.sort_values("ts"), on="ts", direction="backward")
            df["close_vs_tf240_close"] = df["close"] / df["tf240_close"] - 1.0

    if microstructure_frame is not None and not microstructure_frame.empty:
        micro = microstructure_frame.copy().sort_values("ts").reset_index(drop=True)
        df = pd.merge_asof(df.sort_values("ts"), micro.sort_values("ts"), on="ts", direction="backward")

    # === EARLY DETECTION FEATURES (NEW) ===

    # 1. Range compression indicators
    df["atr_slope_3"] = df["atr_pct_14"].pct_change(3)
    df["atr_slope_6"] = df["atr_pct_14"].pct_change(6)
    df["range_compression"] = ((df["atr_slope_3"] < -0.1) & (df["range_pct"] < df["range_pct"].rolling(20).mean())).astype(int)

    # 2. Volume trend detection
    df["volume_slope_3"] = df["volume"].rolling(3).apply(lambda x: (x.iloc[-1] - x.iloc[0]) / max(x.iloc[0], 1e-10), raw=False)
    df["volume_slope_6"] = df["volume"].rolling(6).apply(lambda x: (x.iloc[-1] - x.iloc[0]) / max(x.iloc[0], 1e-10), raw=False)
    df["volume_drying"] = ((df["volume_slope_3"] < -0.2) & (df["volume"] < df["volume"].rolling(20).mean())).astype(int)

    # 3. Order book accumulation (if microstructure data available)
    if "ob_imbalance_top_10" in df.columns:
        df["ob_imbalance_trend_3"] = df["ob_imbalance_top_10"].diff(3)
        df["ob_imbalance_trend_6"] = df["ob_imbalance_top_10"].diff(6)
        df["ob_accumulation_score"] = (
            (df["ob_imbalance_top_10"].abs() > 0.3).astype(int) *
            (df["ob_imbalance_trend_3"].abs() > 0.1).astype(int)
        )
    else:
        df["ob_imbalance_trend_3"] = 0.0
        df["ob_imbalance_trend_6"] = 0.0
        df["ob_accumulation_score"] = 0.0

    # 4. MTF alignment forming (weaker than full alignment)
    df["mtf_alignment_forming"] = (
        (df["ema_8_vs_21"].abs() < 0.005) &  # EMAs close together
        (df["ema_slope_8"].abs() < 0.002) &   # Low slope
        (df["range_pct"] < df["range_pct"].rolling(20).quantile(0.3))  # Low volatility
    ).astype(int)
    df["ema_convergence_ratio"] = df["ema_8_vs_21"].abs() / df["ema_8_vs_21"].rolling(50).mean().replace(0, pd.NA)

    # 5. Momentum divergence
    rsi_window = 14
    price_momentum = df["close"].pct_change(rsi_window)
    rsi_momentum = df["rsi_14"].pct_change(rsi_window)
    df["rsi_divergence_score"] = (price_momentum - rsi_momentum).rolling(5).mean()
    df["price_momentum_vs_rsi"] = price_momentum - rsi_momentum

    # 6. Extreme close positions
    df["extreme_close_position"] = (
        (df["bar_close_position"] > 0.9).astype(int) |
        (df["bar_close_position"] < 0.1).astype(int)
    )

    # 7. Distance from VWAP (approximation using typical price)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (typical_price * df["volume"]).rolling(20).sum() / df["volume"].rolling(20).sum().replace(0, pd.NA)
    df["distance_from_vwap"] = (df["close"] - vwap) / vwap.replace(0, pd.NA)

    # 8. Bollinger Band width (volatility squeeze detection)
    bb_middle = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    bb_upper = bb_middle + 2 * bb_std
    bb_lower = bb_middle - 2 * bb_std
    df["bollinger_width_pct"] = (bb_upper - bb_lower) / bb_middle

    # 9. Keltner Channel position
    keltner_atr = df["atr_14"] * 2
    keltner_upper = df["ema_21"] + keltner_atr
    keltner_lower = df["ema_21"] - keltner_atr
    df["keltner_position"] = (df["close"] - keltner_lower) / (keltner_upper - keltner_lower).replace(0, pd.NA)

    # 10. Donchian Channel breakout score
    donchian_high = df["high"].rolling(20).max()
    donchian_low = df["low"].rolling(20).min()
    donchian_mid = (donchian_high + donchian_low) / 2
    df["donchian_breakout_score"] = (
        ((df["close"] > donchian_high.shift(1)).astype(int) * 2) +  # Strong breakout
        ((df["close"] > donchian_mid.shift(1)).astype(int))  # Weak breakout
    )

    for column in FEATURE_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    for column, default in FEATURE_DEFAULTS.items():
        series = df[column]
        if str(series.dtype) == "object":
            series = series.infer_objects(copy=False)
        series = series.where(series.notna(), default)
        df[column] = series
    return df


def attach_labels(
    df: pd.DataFrame,
    horizon_bars: int,
    min_return_pct: float,
    take_profit_pct: float,
    stop_loss_pct: float,
    max_hold_bars: int,
    short_min_return_pct: float | None = None,
    short_max_adverse_up_pct: float | None = None,
) -> pd.DataFrame:
    labeled = df.copy().reset_index(drop=True)
    future_close = labeled["close"].shift(-horizon_bars)
    labeled["future_return_pct"] = ((future_close / labeled["close"]) - 1.0) * 100

    best_returns: list[float | None] = []
    worst_returns: list[float | None] = []
    long_targets: list[int | None] = []
    short_targets: list[int | None] = []

    for idx in range(len(labeled)):
        entry_price = float(labeled.at[idx, "close"])
        future_slice = labeled.iloc[idx + 1 : idx + 1 + max_hold_bars]
        if future_slice.empty:
            best_returns.append(None)
            worst_returns.append(None)
            long_targets.append(None)
            short_targets.append(None)
            continue

        best_return = ((future_slice["high"].max() / entry_price) - 1.0) * 100
        worst_return = ((future_slice["low"].min() / entry_price) - 1.0) * 100
        best_returns.append(float(best_return))
        worst_returns.append(float(worst_return))

        long_hit = best_return >= min_return_pct and worst_return > -(stop_loss_pct * 1.4)
        short_min_return = min_return_pct if short_min_return_pct is None else short_min_return_pct
        short_max_adverse = (take_profit_pct * 0.8) if short_max_adverse_up_pct is None else short_max_adverse_up_pct
        short_hit = worst_return <= -short_min_return and best_return < short_max_adverse
        long_targets.append(int(long_hit))
        short_targets.append(int(short_hit))

    labeled["future_best_return_pct"] = best_returns
    labeled["future_worst_return_pct"] = worst_returns
    labeled["long_target"] = pd.Series(long_targets, dtype="float").astype("Int64")
    labeled["short_target"] = pd.Series(short_targets, dtype="float").astype("Int64")
    return labeled
