"""
Cross-Market Correlation Analyzer - Real-time inter-market analysis.

Provides:
1. DXY (Dollar Index) correlation with BTC
2. ETH/BTC ratio and momentum comparison
3. S&P 500 / Nasdaq correlation for risk sentiment
4. USDT Dominance for flight-to-safety signals

All data fetched from public APIs with caching and fallback handling.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import requests

logger = logging.getLogger(__name__)


class CrossMarketData:
    """Container for current cross-market data."""

    def __init__(self):
        # DXY data
        self.dxy_price: Optional[float] = None
        self.dxy_change_pct: Optional[float] = None
        self.dxy_trend: Optional[str] = None  # 'rising', 'falling', 'neutral'

        # ETH/BTC data
        self.eth_btc_ratio: Optional[float] = None
        self.eth_momentum_vs_btc: Optional[float] = None  # ETH momentum - BTC momentum
        self.eth_leading: Optional[bool] = None

        # S&P 500 data
        self.spx_price: Optional[float] = None
        self.spx_change_pct: Optional[float] = None
        self.spx_correlation_with_btc: Optional[float] = None

        # USDT Dominance
        self.usdt_dominance: Optional[float] = None
        self.usdt_dominance_change: Optional[float] = None

        # Metadata
        self.timestamp: Optional[datetime] = None
        self.data_quality: float = 1.0  # 0-1 how complete is the data


class CrossMarketAnalyzer:
    """
    Analyzes inter-market relationships to improve BTC trading decisions.

    Key insights provided:
    - Is BTC moving with or against traditional markets?
    - Are there leading indicators from other markets?
    - Is money flowing into or out of crypto?
    """

    def __init__(self, cache_ttl_seconds: int = 60):
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._last_fetch_time: float = 0

        # API endpoints (using free public sources)
        self.dxy_api = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
        self.spx_api = "https://query1.finance.yahoo.com/v8/finance/chart/SPY"
        self.ethbtc_api = "https://api.binance.com/api/v3/klines?symbol=ETHBTC&interval=15m&limit=96"
        self.btc_api = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=96"
        self.usdt_api = "https://api.coingecko.com/api/v3/global/metrics"

    def get_current_data(self) -> CrossMarketData:
        """
        Fetch and analyze current cross-market data.

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
            logger.warning(f"Failed to fetch cross-market data: {e}")

            # Return last known good data only if it is still recent. Serving
            # days-old cached data forever (e.g. during a long Yahoo 429
            # streak) fed the model a stale market snapshot with no staleness
            # signal — downstream never checks data_quality.
            if self._cache and (now - self._last_fetch_time) < self.cache_ttl * 10:
                old_data = self._cache['data']
                old_data.data_quality = 0.3  # Mark as degraded
                return old_data
            else:
                return CrossMarketData()

    def _fetch_and_analyze(self) -> CrossMarketData:
        """Fetch all market data and compute correlations."""

        result = CrossMarketData()
        result.timestamp = datetime.now(timezone.utc)

        # Fetch each market data
        dxy_data = self._fetch_dxy()
        ethbtc_data = self._fetch_ethbtc()
        btc_data = self._fetch_btc()
        spx_data = self._fetch_spx()
        usdt_data = self._fetch_usdt_dominance()

        # Calculate metrics
        if dxy_data is not None and len(dxy_data) > 10:
            result.dxy_price = float(dxy_data['close'].iloc[-1])
            result.dxy_change_pct = self._calculate_change_pct(dxy_data)
            result.dxy_trend = self._determine_trend(dxy_data)

        if ethbtc_data is not None and len(ethbtc_data) > 10 and btc_data is not None:
            result.eth_btc_ratio = float(ethbtc_data['close'].iloc[-1])
            result.eth_momentum_vs_btc = self._calculate_relative_momentum(ethbtc_data, btc_data)
            result.eth_leading = self._is_eth_leading(ethbtc_data, btc_data)

        if spx_data is not None and len(spx_data) > 10 and btc_data is not None:
            result.spx_price = float(spx_data['close'].iloc[-1])
            result.spx_change_pct = self._calculate_change_pct(spx_data)
            result.spx_correlation_with_btc = self._calculate_correlation(
                spx_data['close'],
                btc_data['close']
            )

        if usdt_data is not None:
            result.usdt_dominance = usdt_data.get('usdt_dominance')
            result.usdt_dominance_change = usdt_data.get('change_24h')

        # Calculate overall data quality
        fields_checked = 5
        fields_present = sum([
            1 if result.dxy_price else 0,
            1 if result.eth_btc_ratio else 0,
            1 if result.spx_price else 0,
            1 if result.usdt_dominance else 0,
            1 if btc_data is not None else 0
        ])
        result.data_quality = fields_present / fields_checked

        return result

    def _fetch_dxy(self, interval='15m', period='5d') -> Optional[pd.DataFrame]:
        """Fetch Dollar Index data from Yahoo Finance."""
        try:
            params = {'range': period, 'interval': interval}
            response = requests.get(self.dxy_api, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                quotes = data['chart']['result'][0]['indicators']['quote'][0]
                timestamps = data['chart']['result'][0]['timestamp']

                df = pd.DataFrame({
                    'open': quotes['open'],
                    'high': quotes['high'],
                    'low': quotes['low'],
                    'close': quotes['close'],
                    'volume': quotes.get('volume', [0] * len(timestamps))
                }, index=pd.to_datetime(timestamps, unit='s'))

                df = df.dropna()
                return df
            else:
                logger.warning(f"DXY fetch failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching DXY: {e}")
            return None

    def _fetch_spx(self, interval='15m', period='5d') -> Optional[pd.DataFrame]:
        """Fetch S&P 500 ETF data from Yahoo Finance."""
        try:
            params = {'range': period, 'interval': interval}
            response = requests.get(self.spx_api, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                quotes = data['chart']['result'][0]['indicators']['quote'][0]
                timestamps = data['chart']['result'][0]['timestamp']

                df = pd.DataFrame({
                    'open': quotes['open'],
                    'high': quotes['high'],
                    'low': quotes['low'],
                    'close': quotes['close'],
                    'volume': quotes.get('volume', [0] * len(timestamps))
                }, index=pd.to_datetime(timestamps, unit='s'))

                df = df.dropna()
                return df
            else:
                logger.warning(f"SPX fetch failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching SPX: {e}")
            return None

    def _fetch_ethbtc(self) -> Optional[pd.DataFrame]:
        """Fetch ETH/BTC ratio from Binance."""
        try:
            response = requests.get(self.ethbtc_api, timeout=5)

            if response.status_code == 200:
                data = response.json()

                df = pd.DataFrame(data, columns=[
                    'time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_vol', 'trades', 'taker_buy',
                    'taker_quote', 'ignore'
                ])

                df['close'] = pd.to_numeric(df['close'])
                df['time'] = pd.to_datetime(df['time'], unit='ms')
                df = df.set_index('time')

                return df[['open', 'high', 'low', 'close', 'volume']]
            else:
                logger.warning(f"ETHBTC fetch failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching ETHBTC: {e}")
            return None

    def _fetch_btc(self) -> Optional[pd.DataFrame]:
        """Fetch BTC/USDT data from Binance."""
        try:
            response = requests.get(self.btc_api, timeout=5)

            if response.status_code == 200:
                data = response.json()

                df = pd.DataFrame(data, columns=[
                    'time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_vol', 'trades', 'taker_buy',
                    'taker_quote', 'ignore'
                ])

                df['close'] = pd.to_numeric(df['close'])
                df['time'] = pd.to_datetime(df['time'], unit='ms')
                df = df.set_index('time')

                return df[['open', 'high', 'low', 'close', 'volume']]
            else:
                logger.warning(f"BTC fetch failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching BTC: {e}")
            return None

    def _fetch_usdt_dominance(self) -> Optional[Dict]:
        """Fetch USDT Dominance from CoinGecko."""
        try:
            response = requests.get(self.usdt_api, timeout=5)

            if response.status_code == 200:
                data = response.json()

                # CoinGecko returns total market cap data
                # We need to calculate USDT dominance
                total_market_cap = data.get('data', {}).get('total_market_cap', {}).get('usd')
                total_volume = data.get('data', {}).get('total_volume', {}).get('usd')

                # This is approximate - would be better with actual USDT dom data
                # For now, return what we can get
                return {
                    'usdt_dominance': None,  # Not directly available
                    'change_24h': None
                }
            else:
                return None

        except Exception as e:
            logger.error(f"Error fetching USDT dominance: {e}")
            return None

    def _calculate_change_pct(self, df: pd.DataFrame, periods: int = 3) -> float:
        """Calculate percentage change over N periods."""
        close = df['close']
        change = ((close.iloc[-1] - close.iloc[-periods-1]) / close.iloc[-periods-1]) * 100
        return float(change)

    def _determine_trend(self, df: pd.DataFrame, window: int = 20) -> str:
        """Determine if price is rising, falling, or neutral."""
        close = df['close']
        sma_short = close.rolling(window=5).mean()
        sma_long = close.rolling(window=window).mean()

        current_short = sma_short.iloc[-1]
        current_long = sma_long.iloc[-1]

        if current_short > current_long * 1.002:
            return "rising"
        elif current_short < current_long * 0.998:
            return "falling"
        else:
            return "neutral"

    def _calculate_relative_momentum(self, eth_df: pd.DataFrame, btc_df: pd.DataFrame) -> float:
        """Calculate ETH momentum minus BTC momentum."""
        # Calculate RSI-like momentum for both
        eth_returns = eth_df['close'].pct_change().dropna()
        btc_returns = btc_df['close'].pct_change().dropna()

        # Align lengths
        min_len = min(len(eth_returns), len(btc_returns))
        eth_returns = eth_returns.iloc[-min_len:]
        btc_returns = btc_returns.iloc[-min_len:]

        # Momentum = average return over recent periods
        eth_momentum = eth_returns.mean() * 100
        btc_momentum = btc_returns.mean() * 100

        return float(eth_momentum - btc_momentum)

    def _is_eth_leading(self, eth_df: pd.DataFrame, btc_df: pd.DataFrame, lag_periods: int = 2) -> bool:
        """Check if ETH movements precede BTC movements."""
        eth_returns = eth_df['close'].pct_change().dropna()
        btc_returns = btc_df['close'].pct_change().dropna()

        # Calculate cross-correlation with lag
        min_len = min(len(eth_returns), len(btc_returns))
        eth_returns = eth_returns.iloc[-min_len:]
        btc_returns = btc_returns.iloc[-min_len:]

        # Shift ETH returns forward to see if they lead BTC
        correlation = eth_returns.shift(lag_periods).corr(btc_returns)

        # If correlation is positive and significant, ETH is leading
        return bool(correlation > 0.3)

    def _calculate_correlation(self, series1: pd.Series, series2: pd.Series, window: int = 24) -> float:
        """Calculate rolling correlation between two price series."""
        # Convert to returns
        returns1 = series1.pct_change().dropna()
        returns2 = series2.pct_change().dropna()

        # Align
        min_len = min(len(returns1), len(returns2))
        returns1 = returns1.iloc[-min_len:]
        returns2 = returns2.iloc[-min_len:]

        # Calculate correlation
        corr = returns1.corr(returns2)

        return float(corr) if not np.isnan(corr) else 0.0

    def get_context_features(self, row: pd.Series = None) -> Dict[str, Any]:
        """
        Get cross-market features for context analysis.

        Can optionally take a row from main dataset to enrich with cross-market data.
        """
        data = self.get_current_data()

        features = {
            'dxy_price': data.dxy_price,
            'dxy_change_pct': data.dxy_change_pct,
            'dxy_trend': data.dxy_trend,
            'eth_btc_ratio': data.eth_btc_ratio,
            'eth_momentum_vs_btc': data.eth_momentum_vs_btc,
            'eth_leading': data.eth_leading,
            'spx_price': data.spx_price,
            'spx_change_pct': data.spx_change_pct,
            'spx_btc_correlation': data.spx_correlation_with_btc,
            'usdt_dominance': data.usdt_dominance,
            'usdt_dominance_change': data.usdt_dominance_change,
            'data_quality': data.data_quality
        }

        # Add derived features
        if data.dxy_trend == "falling" and data.dxy_change_pct and data.dxy_change_pct < -0.3:
            features['dxy_bullish_for_btc'] = True
        else:
            features['dxy_bullish_for_btc'] = False

        if data.eth_leading and data.eth_momentum_vs_btc and data.eth_momentum_vs_btc > 0:
            features['crypto_strength_signal'] = True
        else:
            features['crypto_strength_signal'] = False

        if data.spx_correlation_with_btc and abs(data.spx_correlation_with_btc) > 0.5:
            features['risk_on_off_relevant'] = True
        else:
            features['risk_on_off_relevant'] = False

        return features


# Singleton instance for reuse
_analyzer_instance: Optional[CrossMarketAnalyzer] = None


def get_cross_market_analyzer() -> CrossMarketAnalyzer:
    """Get or create the singleton analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = CrossMarketAnalyzer()
    return _analyzer_instance


def get_cross_market_features(row: pd.Series = None) -> Dict[str, Any]:
    """Convenience function to get current cross-market features."""
    return get_cross_market_analyzer().get_context_features(row)
