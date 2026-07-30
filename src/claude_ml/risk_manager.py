"""
Risk Manager - Dynamic position sizing and portfolio risk management.

Features:
- Dynamic position sizing based on regime/performance/DD
- Multi-symbol portfolio allocation
- Drawdown protection circuit breaker
- ATR-based TP/SL (instead of fixed %)
- Per-trade risk limits
- Daily loss limits
- Correlation-adjusted sizing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass(slots=True)
class PositionSizeResult:
    """Result from position size calculation."""
    base_size_pct: float  # Base position size as % of balance
    adjusted_size_pct: float  # After all adjustments
    take_profit_price: float
    stop_loss_price: float
    trailing_trigger_price: float
    risk_amount: float  # Actual $ at risk
    max_loss_pct: float  # Max possible loss
    reasoning: List[str] = field(default_factory=list)


class RiskManager:
    """Dynamic risk management for multi-symbol trading."""

    def __init__(self, settings):
        self.settings = settings

        # Runtime state
        self.current_balance = settings.paper_start_balance
        self.peak_balance = settings.paper_start_balance  # Track peak balance for drawdown
        self.daily_pnl = 0.0
        self.drawdown_pct = 0.0
        self.recent_trades: List[Dict[str, Any]] = []
        self.symbol_positions: Dict[str, float] = {}  # symbol -> current position %
        self.total_portfolio_risk = 0.0

        # Performance tracking
        self.win_count = 0
        self.loss_count = 0
        self.recent_win_rate = 0.5

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        atr: float,
        regime: str,
        model_confidence: float,
        side: str = "long",
    ) -> PositionSizeResult:
        """
        Calculate dynamic position size with multiple adjustments.

        Args:
            symbol: Trading symbol
            entry_price: Current price
            atr: ATR value for TP/SL calculation
            regime: Current market regime
            model_confidence: Ensemble confidence (0-1)
            side: 'long' or 'short'

        Returns:
            PositionSizeResult with sizes and levels
        """
        reasoning = []

        # 1. Base position size (risk_per_trade % of balance)
        base_size_pct = self.settings.risk_per_trade_pct
        reasoning.append(f"Base: {base_size_pct}%")

        # 2. Regime adjustment
        regime_multiplier = self._get_regime_multiplier(regime)
        if regime_multiplier != 1.0:
            reasoning.append(f"Regime ({regime}): x{regime_multiplier:.2f}")

        # 3. Performance adjustment (based on recent win rate)
        performance_multiplier = self._get_performance_multiplier()
        if performance_multiplier != 1.0:
            reasoning.append(f"Performance (WR {self.recent_win_rate:.0%}): x{performance_multiplier:.2f}")

        # 4. Drawdown adjustment
        dd_multiplier = self._get_drawdown_multiplier()
        if dd_multiplier != 1.0:
            reasoning.append(f"Drawdown ({self.drawdown_pct:.1f}%): x{dd_multiplier:.2f}")

        # 5. Model confidence adjustment
        confidence_multiplier = 0.5 + (model_confidence * 0.5)  # Scale 0.5-1.0
        if abs(confidence_multiplier - 1.0) > 0.05:
            reasoning.append(f"Confidence ({model_confidence:.0%}): x{confidence_multiplier:.2f}")

        # 6. Portfolio correlation check
        portfolio_multiplier = self._check_portfolio_limit(symbol)
        if portfolio_multiplier != 1.0:
            reasoning.append(f"Portfolio limit: x{portfolio_multiplier:.2f}")

        # Calculate final size
        adjusted_size_pct = (
            base_size_pct
            * regime_multiplier
            * performance_multiplier
            * dd_multiplier
            * confidence_multiplier
            * portfolio_multiplier
        )

        # Cap at max position size
        adjusted_size_pct = min(adjusted_size_pct, self.settings.max_position_size_pct)

        # NO FIXED TP/SL - Use only trailing stop for maximum profit potential
        # Trailing stop will be created in runtime.py after position is opened
        take_profit_price = None  # Not used - trailing stop handles exit
        stop_loss_price = None    # Not used - trailing stop protects capital
        trailing_trigger_price = entry_price + (atr * self.settings.trailing_trigger_atr_multiplier) if side == "long" else entry_price - (atr * self.settings.trailing_trigger_atr_multiplier)

        # Calculate actual risk amount (based on trailing stop distance)
        trailing_stop_distance = atr * self.settings.trailing_step_atr_multiplier
        risk_per_unit = trailing_stop_distance
        position_units = (self.current_balance * adjusted_size_pct / 100) / entry_price
        risk_amount = position_units * risk_per_unit
        max_loss_pct = (risk_amount / self.current_balance) * 100

        return PositionSizeResult(
            base_size_pct=base_size_pct,
            adjusted_size_pct=round(adjusted_size_pct, 2),
            take_profit_price=None,  # No fixed TP
            stop_loss_price=None,    # No fixed SL
            trailing_trigger_price=round(trailing_trigger_price, 6),
            risk_amount=round(risk_amount, 2),
            max_loss_pct=round(max_loss_pct, 2),
            reasoning=reasoning,
        )

    def _get_regime_multiplier(self, regime: str) -> float:
        """Get position size multiplier based on market regime."""
        multipliers = {
            "chop": self.settings.size_multiplier_chop,
            "flat": self.settings.size_multiplier_chop * 0.8,
            "expansion": self.settings.size_multiplier_expansion,
            "trend_up": self.settings.size_multiplier_trend,
            "trend_down": self.settings.size_multiplier_trend,
            "compression_pre_breakout": 0.7,
            "trend_initiation": 0.9,
            "trend_continuation": 1.0,
            "trend_exhaustion": 0.6,
        }
        return multipliers.get(regime, 1.0)

    def _get_performance_multiplier(self) -> float:
        """Adjust size based on recent win rate."""
        if self.win_count + self.loss_count < 10:
            return 1.0  # Not enough data

        if self.recent_win_rate >= 0.60:
            return 1.2  # Hot streak - increase size
        elif self.recent_win_rate >= 0.50:
            return 1.0  # Normal
        elif self.recent_win_rate >= 0.40:
            return 0.8  # Cold - reduce size
        else:
            return 0.6  # Very cold - significantly reduce

    def _get_drawdown_multiplier(self) -> float:
        """Reduce size during drawdown."""
        if self.drawdown_pct >= self.settings.pause_at_dd_pct:
            return 0.0  # Should be paused
        elif self.drawdown_pct >= self.settings.reduce_size_at_dd_pct:
            return 0.5  # Half size
        elif self.drawdown_pct >= 5.0:
            return 0.7  # Reduced
        else:
            return 1.0  # Normal

    def _check_portfolio_limit(self, symbol: str) -> float:
        """Check if adding this position exceeds portfolio limits."""
        current_symbol_risk = self.symbol_positions.get(symbol, 0.0)
        new_total_risk = self.total_portfolio_risk + (self.settings.risk_per_trade_pct - current_symbol_risk)

        if new_total_risk > self.settings.max_portfolio_risk_pct:
            return 0.0  # Reject trade

        if current_symbol_risk >= self.settings.max_position_size_pct:
            return 0.0  # Already at max for this symbol

        return 1.0

    def update_performance(self, pnl_pct: float, symbol: str) -> None:
        """Update performance metrics after a trade closes."""
        self.current_balance *= (1 + pnl_pct / 100)

        if pnl_pct > 0:
            self.win_count += 1
        else:
            self.loss_count += 1

        total_trades = self.win_count + self.loss_count
        self.recent_win_rate = self.win_count / total_trades if total_trades > 0 else 0.5

        # Update daily PnL
        self.daily_pnl += pnl_pct

        # Remove from symbol positions
        if symbol in self.symbol_positions:
            del self.symbol_positions[symbol]

        # Recalculate total portfolio risk
        self.total_portfolio_risk = sum(self.symbol_positions.values())

        # Update drawdown with proper peak tracking
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        self.drawdown_pct = ((self.peak_balance - self.current_balance) / self.peak_balance) * 100

    def add_open_position(self, symbol: str, size_pct: float) -> None:
        """Track an opened position."""
        self.symbol_positions[symbol] = size_pct
        self.total_portfolio_risk = sum(self.symbol_positions.values())

    def check_circuit_breakers(self) -> tuple[bool, str]:
        """
        Check if trading should be paused due to risk limits.

        Returns:
            (allowed, reason) tuple
        """
        # 1. Drawdown circuit breaker
        if self.drawdown_pct >= self.settings.pause_at_dd_pct:
            return False, f"Drawdown limit reached: {self.drawdown_pct:.1f}% >= {self.settings.pause_at_dd_pct}%"

        # 2. Daily loss limit
        if self.daily_pnl <= -self.settings.daily_pnl_limit_pct:
            return False, f"Daily loss limit hit: {self.daily_pnl:.2f}% <= -{self.settings.daily_pnl_limit_pct}%"

        # 3. Error streak
        # (Handled by runtime engine)

        # 4. Portfolio risk limit
        if self.total_portfolio_risk >= self.settings.max_portfolio_risk_pct:
            return False, f"Portfolio risk limit: {self.total_portfolio_risk:.1f}% >= {self.settings.max_portfolio_risk_pct}%"

        return True, "OK"

    def get_risk_summary(self) -> Dict[str, Any]:
        """Get current risk status summary."""
        return {
            "balance": round(self.current_balance, 2),
            "daily_pnl_pct": round(self.daily_pnl, 2),
            "drawdown_pct": round(self.drawdown_pct, 2),
            "recent_win_rate": round(self.recent_win_rate, 2),
            "total_trades": self.win_count + self.loss_count,
            "open_positions": len(self.symbol_positions),
            "portfolio_risk_pct": round(self.total_portfolio_risk, 2),
            "circuit_breaker_status": self.check_circuit_breakers()[1],
        }

    def reset_daily(self) -> None:
        """Reset daily counters at start of new trading day."""
        self.daily_pnl = 0.0
