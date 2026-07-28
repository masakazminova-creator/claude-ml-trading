from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import time

import pandas as pd
import requests


def _large_trade_ratio(notionals: list[float]) -> float:
    if not notionals:
        return 0.0
    threshold = sorted(notionals)[max(0, int(len(notionals) * 0.9) - 1)]
    large_trades = sum(1 for notional in notionals if threshold > 0 and notional >= threshold)
    return large_trades / len(notionals)


@dataclass(slots=True)
class BybitCollector:
    base_url: str
    category: str = "linear"

    def _request(self, path: str, params: dict) -> dict:
        url = f"{self.base_url.rstrip('/')}{path}"
        last_error = None
        for attempt in range(1, 4):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers={"User-Agent": "xrp-futures-ml-signal-bot/1.0"},
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("retCode") != 0:
                    raise RuntimeError(f"Bybit error: {payload.get('retCode')} {payload.get('retMsg')}")
                return payload
            except (requests.RequestException, ValueError, RuntimeError) as err:
                last_error = err
                if attempt < 3:
                    time.sleep(attempt * 2)
        raise RuntimeError(f"Bybit request failed after retries: {last_error}") from last_error

    def fetch_klines(self, symbol: str, interval: str, limit: int = 1000, end: int | None = None) -> pd.DataFrame:
        params = {
            "category": self.category,
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if end is not None:
            params["end"] = int(end)
        payload = self._request("/v5/market/kline", params)
        rows: Iterable[list[str]] = payload.get("result", {}).get("list", [])
        if not rows:
            raise RuntimeError("Bybit returned empty kline set")

        frame = pd.DataFrame(
            rows,
            columns=["start_time", "open", "high", "low", "close", "volume", "turnover"],
        )
        frame = frame.iloc[::-1].reset_index(drop=True)
        frame["ts"] = pd.to_datetime(frame["start_time"].astype("int64"), unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        return frame[["ts", "open", "high", "low", "close", "volume", "turnover"]].dropna().reset_index(drop=True)

    def fetch_history(self, symbol: str, interval: str, lookback_bars: int) -> pd.DataFrame:
        chunks: list[pd.DataFrame] = []
        remaining = max(lookback_bars, 300)
        end = None
        while remaining > 0:
            batch_limit = min(remaining, 1000)
            chunk = self.fetch_klines(symbol=symbol, interval=interval, limit=batch_limit, end=end)
            if chunk.empty:
                break
            chunks.append(chunk)
            oldest_ts_ms = int(chunk["ts"].iloc[0].timestamp() * 1000)
            end = oldest_ts_ms - 1
            remaining -= len(chunk)
            if len(chunk) < batch_limit:
                break
            time.sleep(0.25)

        if not chunks:
            raise RuntimeError("Не удалось получить историю свечей")
        frame = pd.concat(chunks, ignore_index=True)
        frame = frame.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        if len(frame) > lookback_bars:
            frame = frame.iloc[-lookback_bars:].reset_index(drop=True)
        return frame

    def fetch_orderbook_snapshot(self, symbol: str, limit: int = 50) -> dict:
        payload = self._request(
            "/v5/market/orderbook",
            {"category": self.category, "symbol": symbol, "limit": min(limit, 200)},
        )
        result = payload.get("result", {})
        bids = result.get("b", []) or []
        asks = result.get("a", []) or []
        if not bids or not asks:
            raise RuntimeError("Orderbook snapshot empty")

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        bid_depth_10 = sum(float(level[1]) for level in bids[:10])
        ask_depth_10 = sum(float(level[1]) for level in asks[:10])
        total_top_10 = bid_depth_10 + ask_depth_10
        imbalance_top_10 = ((bid_depth_10 - ask_depth_10) / total_top_10) if total_top_10 else 0.0
        spread_bps = ((best_ask - best_bid) / ((best_ask + best_bid) / 2.0)) * 10000

        return {
            "ts": pd.Timestamp.utcnow(),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_bps": spread_bps,
            "bid_depth_10": bid_depth_10,
            "ask_depth_10": ask_depth_10,
            "imbalance_top_10": imbalance_top_10,
        }

    def fetch_recent_trades_snapshot(self, symbol: str, limit: int = 200) -> dict:
        payload = self._request(
            "/v5/market/recent-trade",
            {"category": self.category, "symbol": symbol, "limit": min(limit, 1000)},
        )
        trades = payload.get("result", {}).get("list", []) or []
        if not trades:
            raise RuntimeError("Recent trades snapshot empty")

        buy_volume = 0.0
        sell_volume = 0.0
        latest_ts = None
        notionals = []
        for trade in trades:
            size = float(trade.get("v", 0.0))
            price = float(trade.get("p", 0.0))
            notional = size * price
            notionals.append(notional)
            side = str(trade.get("S", "")).lower()
            if side == "buy":
                buy_volume += size
            else:
                sell_volume += size
            trade_ts = int(trade.get("T", 0))
            latest_ts = max(latest_ts or trade_ts, trade_ts)

        threshold = sorted(notionals)[max(0, int(len(notionals) * 0.9) - 1)] if notionals else 0.0
        large_trades = sum(1 for notional in notionals if threshold > 0 and notional >= threshold)
        total_volume = buy_volume + sell_volume
        buy_ratio = (buy_volume / total_volume) if total_volume else 0.5
        flow_imbalance = ((buy_volume - sell_volume) / total_volume) if total_volume else 0.0

        return {
            "ts": pd.to_datetime(latest_ts, unit="ms", utc=True) if latest_ts else pd.Timestamp.utcnow(),
            "trade_count": len(trades),
            "buy_ratio": buy_ratio,
            "flow_imbalance": flow_imbalance,
            "large_trade_ratio": _large_trade_ratio(notionals),
        }


@dataclass(slots=True)
class OKXCollector:
    base_url: str = "https://www.okx.com"
    inst_id: str = "XRP-USDT-SWAP"

    def _request(self, path: str, params: dict) -> dict:
        url = f"{self.base_url.rstrip('/')}{path}"
        last_error = None
        for attempt in range(1, 4):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers={"User-Agent": "xrp-futures-ml-signal-bot/1.0"},
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()
                if str(payload.get("code")) != "0":
                    raise RuntimeError(f"OKX error: {payload.get('code')} {payload.get('msg')}")
                return payload
            except (requests.RequestException, ValueError, RuntimeError) as err:
                last_error = err
                if attempt < 3:
                    time.sleep(attempt * 2)
        raise RuntimeError(f"OKX request failed after retries: {last_error}") from last_error

    def _bar(self, interval: str) -> str:
        mapping = {
            "1": "1m",
            "3": "3m",
            "5": "5m",
            "15": "15m",
            "30": "30m",
            "60": "1H",
            "120": "2H",
            "240": "4H",
            "360": "6H",
            "720": "12H",
            "D": "1D",
        }
        return mapping.get(str(interval).upper(), f"{interval}m")

    def fetch_klines(self, symbol: str, interval: str, limit: int = 100, after: int | None = None) -> pd.DataFrame:
        params = {
            "instId": self.inst_id,
            "bar": self._bar(interval),
            "limit": min(limit, 100),
        }
        if after is not None:
            params["after"] = str(int(after))
        payload = self._request("/api/v5/market/history-candles", params)
        rows = payload.get("data", []) or []
        if not rows:
            raise RuntimeError("OKX returned empty candle set")
        frame = pd.DataFrame(
            rows,
            columns=[
                "start_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "volume_ccy",
                "turnover",
                "confirm",
            ],
        )
        frame = frame.iloc[::-1].reset_index(drop=True)
        frame["ts"] = pd.to_datetime(frame["start_time"].astype("int64"), unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        return frame[["ts", "open", "high", "low", "close", "volume", "turnover"]].dropna().reset_index(drop=True)

    def fetch_history(self, symbol: str, interval: str, lookback_bars: int) -> pd.DataFrame:
        chunks: list[pd.DataFrame] = []
        remaining = max(lookback_bars, 300)
        after = None
        while remaining > 0:
            batch_limit = min(remaining, 100)
            chunk = self.fetch_klines(symbol=symbol, interval=interval, limit=batch_limit, after=after)
            if chunk.empty:
                break
            chunks.append(chunk)
            oldest_ts_ms = int(chunk["ts"].iloc[0].timestamp() * 1000)
            after = oldest_ts_ms
            remaining -= len(chunk)
            if len(chunk) < batch_limit:
                break
            time.sleep(0.15)
        if not chunks:
            raise RuntimeError("Не удалось получить историю свечей")
        frame = pd.concat(chunks, ignore_index=True)
        frame = frame.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        if len(frame) > lookback_bars:
            frame = frame.iloc[-lookback_bars:].reset_index(drop=True)
        return frame

    def fetch_orderbook_snapshot(self, symbol: str, limit: int = 50) -> dict:
        payload = self._request(
            "/api/v5/market/books",
            {"instId": self.inst_id, "sz": min(limit, 400)},
        )
        data = (payload.get("data") or [{}])[0]
        bids = data.get("bids", []) or []
        asks = data.get("asks", []) or []
        if not bids or not asks:
            raise RuntimeError("Orderbook snapshot empty")
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        bid_depth_10 = sum(float(level[1]) for level in bids[:10])
        ask_depth_10 = sum(float(level[1]) for level in asks[:10])
        total_top_10 = bid_depth_10 + ask_depth_10
        imbalance_top_10 = ((bid_depth_10 - ask_depth_10) / total_top_10) if total_top_10 else 0.0
        spread_bps = ((best_ask - best_bid) / ((best_ask + best_bid) / 2.0)) * 10000
        ts = pd.to_datetime(int(data.get("ts", 0)), unit="ms", utc=True) if data.get("ts") else pd.Timestamp.utcnow()
        return {
            "ts": ts,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_bps": spread_bps,
            "bid_depth_10": bid_depth_10,
            "ask_depth_10": ask_depth_10,
            "imbalance_top_10": imbalance_top_10,
        }

    def fetch_recent_trades_snapshot(self, symbol: str, limit: int = 200) -> dict:
        payload = self._request(
            "/api/v5/market/trades",
            {"instId": self.inst_id, "limit": min(limit, 500)},
        )
        trades = payload.get("data", []) or []
        if not trades:
            raise RuntimeError("Recent trades snapshot empty")
        buy_volume = 0.0
        sell_volume = 0.0
        latest_ts = None
        notionals = []
        for trade in trades:
            size = float(trade.get("sz", 0.0))
            price = float(trade.get("px", 0.0))
            notionals.append(size * price)
            if str(trade.get("side", "")).lower() == "buy":
                buy_volume += size
            else:
                sell_volume += size
            trade_ts = int(trade.get("ts", 0))
            latest_ts = max(latest_ts or trade_ts, trade_ts)
        total_volume = buy_volume + sell_volume
        buy_ratio = (buy_volume / total_volume) if total_volume else 0.5
        flow_imbalance = ((buy_volume - sell_volume) / total_volume) if total_volume else 0.0
        return {
            "ts": pd.to_datetime(latest_ts, unit="ms", utc=True) if latest_ts else pd.Timestamp.utcnow(),
            "trade_count": len(trades),
            "buy_ratio": buy_ratio,
            "flow_imbalance": flow_imbalance,
            "large_trade_ratio": _large_trade_ratio(notionals),
        }


def make_collector(settings):
    provider = str(getattr(settings, "market_data_provider", "bybit")).lower()
    if provider == "okx":
        return OKXCollector(getattr(settings, "okx_base_url", "https://www.okx.com"), getattr(settings, "okx_inst_id", "XRP-USDT-SWAP"))
    if provider == "bybit":
        return BybitCollector(settings.bybit_base_url, settings.market_category)
    raise ValueError(f"Unsupported MARKET_DATA_PROVIDER={provider}")
