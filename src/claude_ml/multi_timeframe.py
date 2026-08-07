"""
Multi-Timeframe Analysis - Validate signals across multiple timeframes.

Instead of relying on single timeframe (15m), this module checks alignment across:
- 15m (entry timeframe)
- 1H (medium-term context)
- 4H (higher-term trend)

Only enters when there's alignment, avoiding counter-trend trades.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from .data_collector import OKXCollector

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TimeframeAnalysis:
    """Analysis for a single timeframe."""
    timeframe: str  # '15m', '1h', '4h'
    trend: str  # 'bullish', 'bearish', 'neutral'
    trend_strength: float  # 0-1
    rsi: float
    ema_fast_vs_slow: float  # EMA8 vs EMA21 difference
    momentum: str  # 'positive', 'negative', 'neutral'


@dataclass(slots=True)
class MultiTimeframeAlignment:
    """Result of multi-timeframe analysis."""
    aligned: bool  # Are timeframes aligned?
    alignment_score: float  # 0-1 (how strong is alignment)
    dominant_trend: str  # Overall trend direction
    entry_allowed: bool  # Should we allow entries?
    reasoning: str


class MultiTimeframeAnalyzer:
    """
    Analyzes market across multiple timeframes to validate signals.

    Usage:
        analyzer = MultiTimeframeAnalyzer(symbol="BTCUSDT")
        alignment = analyzer.check_alignment()
        if not alignment.entry_allowed:
            skip_trade()
    """

    def __init__(
        self,
        symbol: str,
        base_timeframe: str = "15",
        okx_base_url: str = "https://www.okx.com",
    ):
        self.symbol = symbol
        self.base_timeframe = base_timeframe
        self.collector = OKXCollector(base_url=okx_base_url, inst_id=f"{symbol.replace('USDT', '')}-USDT-SWAP")

        # Cache results to avoid excessive API calls
        self._cache: Dict[str, TimeframeAnalysis] = {}
        self._last_update_ts = None
        self._cache_ttl_seconds = 60  # Update every minute max

    def check_alignment(self) -> MultiTimeframeAlignment:
        """
        Check alignment across 15m, 1H, 4H timeframes.

        Returns:
            MultiTimeframeAlignment with decision
        """
        # Fetch data for each timeframe
        timeframes = {
            '15m': self._analyze_timeframe("15"),
            '1h': self._analyze_timeframe("60"),
            '4h': self._analyze_timeframe("240"),
        }

        # Filter out failed analyses
        valid_timeframes = {k: v for k, v in timeframes.items() if v is not None}

        if len(valid_timeframes) < 2:
            return MultiTimeframeAlignment(
                aligned=False,
                alignment_score=0.0,
                dominant_trend="unknown",
                entry_allowed=False,
                reasoning="Insufficient data across timeframes",
            )

        # Check alignment
        return self._calculate_alignment(valid_timeframes)

    def _analyze_timeframe(self, interval: str) -> Optional[TimeframeAnalysis]:
        """Analyze a single timeframe with timeout protection."""
        result = [None]
        error = [None]

        def fetch_with_timeout():
            try:
                df = self.collector.fetch_history(
                    symbol=self.symbol,
                    interval=interval,
                    lookback_bars=50,
                )
                result[0] = df
            except Exception as e:
                error[0] = e

        import threading
        thread = threading.Thread(target=fetch_with_timeout)
        thread.daemon = True
        thread.start()
        thread.join(timeout=15)  # 15 second timeout

        if thread.is_alive():
            logger.warning(f"Timeframe {interval} analysis timed out")
            return None

        if error[0]:
            logger.warning(f"Timeframe {interval} analysis failed: {error[0]}")
            return None

        df = result[0]

        if df.empty or len(df) < 30:
            return None

        # Calculate indicators
        close = df['close']
        high = df['high']
        low = df['low']

        # EMAs
        ema_8 = close.rolling(8).mean()
        ema_21 = close.rolling(21).mean()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        # Current values
        current_close = close.iloc[-1]
        ema_diff = float((ema_8.iloc[-1] - ema_21.iloc[-1]) / ema_21.iloc[-1] * 100)

        # Trend determination
        if ema_diff > 0.5:
            trend = "bullish"
            trend_strength = min(abs(ema_diff) / 2.0, 1.0)
        elif ema_diff < -0.5:
            trend = "bearish"
            trend_strength = min(abs(ema_diff) / 2.0, 1.0)
        else:
            trend = "neutral"
            trend_strength = 1.0 - abs(ema_diff) / 0.5

        # Momentum
        recent_ret = float((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100)
        if recent_ret > 1.0:
            momentum = "positive"
        elif recent_ret < -1.0:
            momentum = "negative"
        else:
            momentum = "neutral"

        return TimeframeAnalysis(
            timeframe=f"{interval}m",
            trend=trend,
            trend_strength=trend_strength,
            rsi=float(rsi),
            ema_fast_vs_slow=ema_diff,
            momentum=momentum,
        )

        except Exception as e:
            logger.warning(f"Failed to analyze {interval}m timeframe: {e}")
            return None

    def _calculate_alignment(
        self,
        analyses: Dict[str, TimeframeAnalysis],
    ) -> MultiTimeframeAlignment:
        """Calculate multi-timeframe alignment score."""
        trends = [a.trend for a in analyses.values()]
        strengths = [a.trend_strength for a in analyses.values()]

        # Count trend directions
        bullish_count = trends.count("bullish")
        bearish_count = trends.count("bearish")
        neutral_count = trends.count("neutral")

        total = len(trends)

        # Alignment scenarios
        if bullish_count >= 2 and bearish_count == 0:
            # Mostly bullish
            aligned = bullish_count == total  # All must agree for full alignment
            alignment_score = bullish_count / total
            dominant_trend = "bullish"
            entry_allowed = True
            reasoning = f"Bullish alignment ({bullish_count}/{total} TFs)"

        elif bearish_count >= 2 and bullish_count == 0:
            # Mostly bearish
            aligned = bearish_count == total
            alignment_score = bearish_count / total
            dominant_trend = "bearish"
            entry_allowed = True
            reasoning = f"Bearish alignment ({bearish_count}/{total} TFs)"

        elif neutral_count >= 2:
            # Mostly neutral - no clear direction
            aligned = False
            alignment_score = 0.3
            dominant_trend = "neutral"
            entry_allowed = False
            reasoning = f"Neutral/choppy across timeframes ({neutral_count}/{total} TFs)"

        else:
            # Mixed signals - conflicting timeframes
            aligned = False
            alignment_score = min(bullish_count, bearish_count) / total
            dominant_trend = "mixed"
            entry_allowed = False
            reasoning = f"Conflicting signals (bullish={bullish_count}, bearish={bearish_count})"

        # Reduce score if strengths are weak
        avg_strength = sum(strengths) / len(strengths) if strengths else 0.5
        if avg_strength < 0.5:
            alignment_score *= 0.7
            reasoning += " [weak strengths]"

        return MultiTimeframeAlignment(
            aligned=aligned,
            alignment_score=round(alignment_score, 2),
            dominant_trend=dominant_trend,
            entry_allowed=entry_allowed,
            reasoning=reasoning,
        )
