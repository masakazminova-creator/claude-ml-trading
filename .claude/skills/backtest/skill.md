---
name: backtest
description: Run backtesting analysis on historical data with current models
---

# Backtesting Skill

Test trading strategies on historical data.

## When to use
- User wants to test strategy changes
- Before deploying new threshold configurations
- Analyzing potential profitability
- Comparing different parameter sets

## Commands

```bash
# Basic backtest (last 30 days)
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker exec claude-ml-bot python scripts/backtest.py --days 30"

# Custom parameters
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/backtest.py --days 60 --symbol BTCUSDT --timeframe 15m"

# Test specific thresholds
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/backtest.py --early-thresh 0.60 --confirm-thresh 0.72 --momentum-thresh 0.55"

# Compare strategies
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/backtest.py --compare-strategies"
```

## Output metrics

- **Total Trades**: Number of signals generated
- **Win Rate**: % of profitable trades (target: 50-60%)
- **Profit Factor**: Gross profit / Gross loss (target: >1.5)
- **Max Drawdown**: Largest peak-to-trough decline
- **Sharpe Ratio**: Risk-adjusted returns
- **Avg Trade**: Average profit per trade

## Strategy comparison

Use `--compare-strategies` to test multiple threshold sets:
```bash
# Tests conservative vs aggressive vs current
python scripts/backtest.py --compare-strategies
```

## Important notes

- Backtests use historical OHLCV data from database
- Results are indicative, not guaranteed future performance
- Market regime changes can affect strategy effectiveness
- Always paper-trade new strategies before live deployment
- Trading costs (0.16% per round trip) are included in calculations

## Common scenarios

1. **Threshold tuning**: Find optimal entry/exit points
2. **Regime testing**: See how strategy performs in trend vs chop
3. **Risk analysis**: Understand drawdown patterns
4. **Model comparison**: Test different model versions
