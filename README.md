# Claude ML Trading System

Production-grade adaptive ML trading system for crypto futures (BTC, ETH, XRP).

**Current Status:** Production Beta v0.8.0 with Automated Deployment ✅

## Quick Links

- 🚀 **[Deployment Guide](README_DEPLOY.md)** - Быстрый старт и деплой
- 📖 **[Server Setup](SERVER_SETUP_INSTRUCTIONS.md)** - Пошаговая настройка сервера
- ⚙️ **[Code Server Docs](CODE_SERVER.md)** - Полная документация по автоматизации
- 📊 **[Quick Start](QUICKSTART.md)** - Локальный запуск и тестирование

## Features

- **Multi-Symbol Support**: Trade BTC, ETH, XRP simultaneously
- **Multi-Model Ensemble**: Early signal + Confirmation + Momentum models
- **Continuous Learning**: Automatic retraining with drift detection
- **Dynamic Position Sizing**: Regime-aware risk management
- **Two-Stage Entry**: Early entry (30-50% size) + Confirmation entry (50-70% size)
- **Adaptive Risk Management**: 15% max drawdown protection
- **ATR Trailing Stops**: Volatility-based exit management ⭐ NEW
- **Automated Deployment**: Docker + CI/CD pipeline ⭐ NEW
- **Production Safety**: Health checks, audit trail, emergency controls

## Architecture

```
claude_ml_system/
├── src/claude_ml/          # Core modules
│   ├── config.py            # Configuration
│   ├── data_collector.py    # Multi-provider data
│   ├── feature_engineering.py # Enhanced features
│   ├── regime_detector.py   # Regime classification
│   ├── models/              # Model ensemble
│   │   ├── early_signal.py
│   │   ├── confirmation.py
│   │   ├── momentum.py
│   │   └── expert_router.py
│   ├── ensemble.py          # Model combination
│   ├── entry_system.py      # Two-stage entry
│   ├── risk_manager.py      # Dynamic sizing
│   ├── exit_system.py       # Trailing + soft exit
│   ├── continuous_learning.py # Retraining pipeline
│   ├── monitoring.py        # Health checks
│   └── runtime.py           # Main orchestrator
├── scripts/                 # Entry points
│   ├── train_models.py
│   ├── run_paper.py
│   ├── run_live.py
│   └── analyze_performance.py
├── models/                  # Saved models
├── data/                    # Runtime database
└── logs/                    # Audit trail
```

## Quick Start

### Option 1: Automated Deployment (Recommended)

```bash
# Setup Git repository (one time)
cd C:\Bot\claude_ml_system
git remote add origin https://github.com/masakazminova-creator/claude-ml-trading.git
git push -u origin main

# Deploy to server (every time you make changes)
./deploy.sh root@95.81.101.148
```

This automatically:
- ✅ Commits and pushes your code
- ✅ Copies files to server
- ✅ Rebuilds Docker containers
- ✅ Restarts the trading bot
- ✅ Shows deployment logs

### Option 2: Local Testing

```bash
# Setup locally
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env

# Train initial models
python scripts/train_models.py

# Run paper trading
python scripts/run_with_logging.py
```

See **[QUICKSTART.md](QUICKSTART.md)** for detailed local setup instructions.

## Configuration

Edit `.env` file with your settings:
- `MARKET_DATA_PROVIDER`: bybit or okx
- `SYMBOLS`: BTCUSDT,ETHUSDT,XRPUSDT
- `TIMEFRAME`: 15m
- `RISK_PER_TRADE_PCT`: 1.0 (1%)
- `MAX_DRAWDOWN_PCT`: 15.0 (15%)
- `TELEGRAM_BOT_TOKEN`: Your bot token for notifications
- `TELEGRAM_CHAT_ID`: Your chat ID for alerts

See **[CODE_SERVER.md](CODE_SERVER.md)** for complete configuration guide.

## Safety

- Start in paper mode (default)
- Manual switch to live mode required
- Emergency Telegram commands: /pause, /close_all, /status
- Auto-pause on 3+ consecutive errors
- Daily PnL limit configurable

## Success Criteria

Before going live:
- ✅ Win rate > 48%
- ✅ Profit factor > 1.3
- ✅ Avg PnL > 0.05% after costs
- ✅ Probability calibration > 0.5 correlation
- ✅ 200+ trades across all symbols
- ✅ Max drawdown < 15%

## License

Internal use only.
# Auto-deploy test
