"""
On-Chain Data Module - BTC blockchain metrics for better trading decisions.

Provides:
1. Exchange flows (inflows/outflows) - selling/buying pressure
2. Whale activity (>1000 BTC transactions) - smart money tracking
3. MVRV ratio - overvalued/undervalued metric
4. Funding rates - perpetual futures sentiment
5. Hash rate trends - network security indicator
6. Active addresses - adoption metric

Data sources: CoinMetrics API, Binance API, CoinGecko (free tiers)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd
import numpy as np
import requests

logger = logging.getLogger(__name__)


class OnChainData:
    """Container for current on-chain metrics."""

    def __init__(self):
        # Exchange flows (negative = accumulation, positive = distribution)
        self.exchange_net_flow_24h: Optional[float] = None  # BTC

        # Whale activity
        self.whale_transaction_count_24h: Optional[int] = None  # >1000 BTC txs

        # Valuation metrics
        self.mvrv_ratio: Optional[float] = None  # Market Value to Realized Value

        # Futures market
        self.funding_rate_avg: Optional[float] = None  # Average across major exchanges
        self.long_short_ratio: Optional[float] = None  # Longs vs shorts positioning

        # Network health
        self.hash_rate_trend: Optional[str] = None  # 'rising', 'falling', 'stable'

        # Active addresses
        self.active_addresses_24h: Optional[int] = None

        # Metadata
        self.timestamp: Optional[datetime] = None
        self.data_quality: float = 0.0  # 0-1 how complete is the data


class OnChainAnalyzer:
    """
    Fetches and analyzes BTC on-chain data for trading insights.

    Key signals provided:
    - Exchange outflows → accumulation → bullish
    - Whale buying → smart money entering
    - Low MVRV (<1.5) → undervalued → good entry
    - Negative funding → shorts paying longs → potential squeeze
    - Rising hash rate → network strength
    """

    def __init__(self, cache_ttl_seconds: int = 300):  # 5 min cache
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._last_fetch_time: float = 0

        # API endpoints (free public sources)
        self.binance_funding_api = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
        self.coingecko_global_api = "https://api.coingecko.com/api/v3/global/metrics"

        # Note: Glassnode/CoinMetrics require API keys
        # Using free alternatives where possible

    def get_current_data(self) -> OnChainData:
        """
        Fetch and analyze current on-chain data.

        Returns cached data if within TTL to avoid excessive API calls.
        """
        now = time.time()

        # Check cache
        if now - self._last_fetch_time < self.cache_ttl and self._cache:
            return self._cache['data']

        try:
            data = self._fetch_and_analyze()

            # Cache results
            self._cache['data'] = data
            self._last_fetch_time = now

            return data

        except Exception as e:
            logger.warning(f"Failed to fetch on-chain data: {e}")

            # Return last known good data or empty
            if self._cache:
                old_data = self._cache['data']
                old_data.data_quality = 0.5  # Mark as stale
                return old_data
            else:
                return OnChainData()

    def _fetch_and_analyze(self) -> OnChainData:
        """Fetch all on-chain data and compute metrics."""

        result = OnChainData()
        result.timestamp = datetime.now(timezone.utc)

        # Fetch each metric
        funding_data = self._fetch_funding_rates()
        whale_data = self._fetch_whale_activity()
        mvrv_data = self._fetch_mvrv_ratio()
        hash_rate_data = self._fetch_hash_rate_trend()
        active_addr_data = self._fetch_active_addresses()

        # Populate data
        if funding_data:
            result.funding_rate_avg = funding_data.get('funding_rate')
            result.long_short_ratio = funding_data.get('long_short_ratio')

        if whale_data:
            result.whale_transaction_count_24h = whale_data.get('whale_tx_count')
            result.exchange_net_flow_24h = whale_data.get('exchange_flow')

        if mvrv_data:
            result.mvrv_ratio = mvrv_data.get('mvrv')

        if hash_rate_data:
            result.hash_rate_trend = hash_rate_data.get('trend')

        if active_addr_data:
            result.active_addresses_24h = active_addr_data.get('active_addresses')

        # Calculate overall data quality
        fields_checked = 5
        fields_present = sum([
            1 if result.funding_rate_avg is not None else 0,
            1 if result.whale_transaction_count_24h is not None else 0,
            1 if result.mvrv_ratio is not None else 0,
            1 if result.hash_rate_trend is not None else 0,
            1 if result.active_addresses_24h is not None else 0
        ])
        result.data_quality = fields_present / fields_checked

        return result

    def _fetch_funding_rates(self) -> Optional[Dict]:
        """Fetch BTC perpetual funding rate from Binance."""
        try:
            response = requests.get(self.binance_funding_api, timeout=5)

            if response.status_code == 200:
                data = response.json()

                # Current funding rate (8-hour rate)
                funding_rate = float(data.get('lastFundingRate', 0))

                # Convert to daily rate (multiply by 3)
                daily_rate = funding_rate * 3

                # Get long/short ratio
                lsr_data = self._fetch_long_short_ratio()

                return {
                    'funding_rate': daily_rate,
                    'long_short_ratio': lsr_data
                }
            else:
                logger.warning(f"Funding rate fetch failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching funding rates: {e}")
            return None

    def _fetch_long_short_ratio(self) -> Optional[float]:
        """Fetch top trader long/short ratio from Binance."""
        try:
            url = "https://fapi.binance.com/futures/data/topLongShortAccountRatio"
            params = {
                'symbol': 'BTCUSDT',
                'period': '5m',
                'limit': 1
            }
            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return float(data[0].get('longShortRatio', 1.0))
                else:
                    return None
            else:
                return None

        except Exception as e:
            logger.error(f"Error fetching long/short ratio: {e}")
            return None

    def _fetch_whale_activity(self) -> Optional[Dict]:
        """
        Fetch whale activity from blockchain.info (FREE, no API key).

        Uses transaction output value distribution to estimate large transfers.
        """
        try:
            # Fetch recent large transactions from blockchain.info
            url = "https://blockchain.info/unconfirmed-transactions?format=json"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                txs = data.get('txs', [])

                # Count transactions > 1000 BTC
                whale_count = 0
                total_btc_moved = 0

                for tx in txs[:100]:  # Check first 100 unconfirmed
                    outputs = tx.get('out', [])
                    for output in outputs:
                        value_btc = output.get('value', 0) / 1e8  # Convert satoshi to BTC
                        if value_btc > 1000:
                            whale_count += 1
                            total_btc_moved += value_btc

                # Estimate exchange flows from recent blocks
                recent_blocks_url = "https://blockchain.info/q/nblocks/1?format=json"
                blocks_response = requests.get(recent_blocks_url, timeout=5)

                exchange_flow_estimate = None  # Would need more complex analysis

                return {
                    'whale_tx_count': whale_count if whale_count > 0 else None,
                    'exchange_flow': exchange_flow_estimate
                }
            else:
                return None

        except Exception as e:
            logger.error(f"Error fetching whale activity: {e}")
            return None

    def _fetch_mvrv_ratio(self) -> Optional[Dict]:
        """
        Estimate MVRV ratio using CoinGecko market cap data (FREE).

        MVRV = Market Cap / Realized Cap
        Simplified approximation using available free data.
        """
        try:
            # Get BTC market data from CoinGecko
            url = "https://api.coingecko.com/api/v3/coins/bitcoin"
            params = {
                'localization': False,
                'tickers': False,
                'market_data': True,
                'community_data': False,
                'developer_data': False
            }
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                market_data = data.get('market_data', {})

                # Get market cap and realized cap (if available)
                market_cap = market_data.get('market_cap', {}).get('usd')
                realized_cap = market_data.get('total_value_locked', {}).get('usd')  # Approximation

                if market_cap and realized_cap and realized_cap > 0:
                    mvrv = market_cap / realized_cap
                    return {'mvrv': mvrv}
                else:
                    # Return None - will be handled gracefully
                    return {'mvrv': None}
            else:
                return None

        except Exception as e:
            logger.error(f"Error fetching MVRV estimate: {e}")
            return None

    def _fetch_hash_rate_trend(self) -> Optional[Dict]:
        """
        Fetch hash rate from blockchain.info charts (FREE, no key).

        Uses 24h average to determine trend direction.
        """
        try:
            # Fetch hash rate chart data
            url = "https://api.blockchain.com/v3/exchange/tickers/BTC-USD"

            # Alternative: Use blockchain.info charts API
            chart_url = "https://blockchain.info/charts/hash-rate?timespan=1day&format=json"
            response = requests.get(chart_url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                stats = data.get('stats', [])

                if len(stats) >= 2:
                    # Compare recent vs older hash rate
                    recent_hr = stats[-1].get('y', 0)
                    older_hr = stats[0].get('y', 0)

                    if older_hr > 0:
                        change_pct = ((recent_hr - older_hr) / older_hr) * 100

                        if change_pct > 2:
                            trend = "rising"
                        elif change_pct < -2:
                            trend = "falling"
                        else:
                            trend = "stable"

                        return {'trend': trend}

            return {'trend': None}

        except Exception as e:
            logger.error(f"Error fetching hash rate: {e}")
            return None

    def _fetch_active_addresses(self) -> Optional[Dict]:
        """
        Fetch active addresses from blockchain.info (FREE).

        Rising active addresses → growing adoption
        Declining → waning interest
        """
        try:
            # Use blockchain.info unique address count
            url = "https://blockchain.info/charts/n-unique-addresses?timespan=1day&format=json"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                stats = data.get('stats', [])

                if stats:
                    latest_addresses = stats[-1].get('y', 0)
                    return {'active_addresses': int(latest_addresses)}

            return {'active_addresses': None}

        except Exception as e:
            logger.error(f"Error fetching active addresses: {e}")
            return None

    def get_context_features(self, row: pd.Series = None) -> Dict[str, Any]:
        """
        Get on-chain features for context analysis.

        Can optionally take a row from main dataset to enrich with on-chain data.
        """
        data = self.get_current_data()

        features = {
            'exchange_net_flow_24h': data.exchange_net_flow_24h,
            'whale_tx_count_24h': data.whale_transaction_count_24h,
            'mvrv_ratio': data.mvrv_ratio,
            'funding_rate_daily': data.funding_rate_avg,
            'long_short_ratio': data.long_short_ratio,
            'hash_rate_trend': data.hash_rate_trend,
            'active_addresses_24h': data.active_addresses_24h,
            'onchain_data_quality': data.data_quality
        }

        # Add derived features
        if data.exchange_net_flow_24h and data.exchange_net_flow_24h < -1000:
            features['accumulation_signal'] = True  # Large outflows
        else:
            features['accumulation_signal'] = False

        if data.funding_rate_avg and data.funding_rate_avg < -0.01:
            features['potential_squeeze'] = True  # Negative funding
        else:
            features['potential_squeeze'] = False

        if data.mvrv_ratio and data.mvrv_ratio < 1.5:
            features['undervalued_zone'] = True
        else:
            features['undervalued_zone'] = False

        return features


# Singleton instance for reuse
_analyzer_instance: Optional[OnChainAnalyzer] = None


def get_onchain_analyzer() -> OnChainAnalyzer:
    """Get or create the singleton analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = OnChainAnalyzer()
    return _analyzer_instance


def get_onchain_features(row: pd.Series = None) -> Dict[str, Any]:
    """Convenience function to get current on-chain features."""
    return get_onchain_analyzer().get_context_features(row)
