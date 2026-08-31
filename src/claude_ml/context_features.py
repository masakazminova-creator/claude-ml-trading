"""
Cross-market context features for adaptive decision making.

Collects real-time data from:
- ETH-USDT-SWAP (crypto correlation)
- DXY / SPX proxy (macro context)
- OKX funding rate & open interest (derivatives sentiment)

Returns a dict of features to merge with the main feature set.
"""

import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ContextFeatureCollector:
    """Collects cross-market context features."""

    def __init__(self):
        self.okx_base = "https://www.okx.com"
        # Use free proxies for macro data (fallback to static defaults)
        self.dxy_proxy_url = None  # Could be set to a lightweight API if available

    def get_all_context(self) -> Dict[str, float]:
        """Return all context features as a flat dict."""
        features = {}

        # 1. ETH/BTC ratio (crypto risk-on/off)
        eth_btc_ratio = self._get_eth_btc_ratio()
        features["eth_btc_ratio"] = eth_btc_ratio if eth_btc_ratio else 0.055  # default ~0.055

        # 2. ETH trend (15m return %)
        eth_return = self._get_symbol_return("ETH-USDT-SWAP")
        features["eth_15m_return_pct"] = eth_return if eth_return else 0.0

        # 3. BTC funding rate (OKX perpetual)
        funding_rate = self._get_funding_rate("BTC-USDT-SWAP")
        features["btc_funding_rate"] = funding_rate if funding_rate else 0.0

        # 4. BTC open interest change (%)
        oi_change = self._get_oi_change("BTC-USDT-SWAP")
        features["btc_oi_change_pct"] = oi_change if oi_change else 0.0

        # 5. Macro risk proxy (SPX 15m return if available, else 0)
        spx_return = self._get_spx_proxy_return()
        features["spx_15m_return_pct"] = spx_return if spx_return else 0.0

        return features

    def _get_eth_btc_ratio(self) -> Optional[float]:
        """Get current ETH/BTC price ratio."""
        try:
            r = requests.get(
                f"{self.okx_base}/api/v5/market/ticker?instId=ETH-BTC",
                timeout=5
            )
            if r.status_code == 200:
                data = r.json()
                return float(data["data"][0]["last"])
        except Exception as e:
            logger.warning(f"Failed to fetch ETH/BTC ratio: {e}")
        return None

    def _get_symbol_return(self, inst_id: str) -> Optional[float]:
        """Get 15m return % for a symbol."""
        try:
            r = requests.get(
                f"{self.okx_base}/api/v5/market/history-candles",
                params={"instId": inst_id, "bar": "15m", "limit": "2"},
                timeout=5
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                if len(data) >= 2:
                    close_now = float(data[0][4])  # close of latest candle
                    close_prev = float(data[1][4])  # close of previous candle
                    if close_prev > 0:
                        return ((close_now - close_prev) / close_prev) * 100
        except Exception as e:
            logger.warning(f"Failed to fetch {inst_id} return: {e}")
        return None

    def _get_funding_rate(self, inst_id: str) -> Optional[float]:
        """Get current funding rate (annualized, as decimal)."""
        try:
            r = requests.get(
                f"{self.okx_base}/api/v5/public/funding-rate",
                params={"instId": inst_id},
                timeout=5
            )
            if r.status_code == 200:
                data = r.json()
                return float(data["data"][0]["fundingRate"])
        except Exception as e:
            logger.warning(f"Failed to fetch funding rate: {e}")
        return None

    def _get_oi_change(self, inst_id: str) -> Optional[float]:
        """Get open interest change % (last vs previous candle)."""
        try:
            r = requests.get(
                f"{self.okx_base}/api/v5/rubik/stat/contracts/open-interest-history",
                params={"instId": inst_id, "period": "15m", "limit": "2"},
                timeout=5
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                # API returns rows as arrays: [ts, oi, oiCcy, oiCcyQuote] —
                # indexing with ["oi"] raised TypeError every cycle.
                if len(data) >= 2 and isinstance(data[0], (list, tuple)):
                    oi_now = float(data[0][1])
                    oi_prev = float(data[1][1])
                    if oi_prev > 0:
                        return ((oi_now - oi_prev) / oi_prev) * 100
        except Exception as e:
            logger.warning(f"Failed to fetch OI change: {e}")
        return None

    def _get_spx_proxy_return(self) -> Optional[float]:
        """Get SPX 15m return via a free proxy (or fallback to 0)."""
        # For now, return None — can be replaced with a real API later
        return None
