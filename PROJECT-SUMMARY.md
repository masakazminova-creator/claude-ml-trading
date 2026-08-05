# Claude ML Trading System - Project Summary

**Quick Reference for AI Assistant**

---

## 🎯 What is this?
AI-powered BTC futures trading bot with multi-model ensemble (Early Signal + Confirmation + Momentum) and continuous learning.

**Current Status:** Production on server, paper trading mode

---

## 📁 Project Structure

```
C:\Bot\claude_ml_system\           # Local development
├── src/claude_ml/                 # Core system
│   ├── runtime.py                # Main orchestrator
│   ├── ensemble.py               # Multi-model engine
│   ├── adaptive_thresholds.py    # Dynamic thresholds
│   ├── models/                   # Early, Confirm, Momentum models
│   └── trailing_stop.py          # Exit strategy
├── scripts/                      # Utilities
│   ├── monitor_decisions.py      # CLI dashboard
│   ├── run_paper.py              # Entry point
│   └── backtest.py               # Strategy testing
└── .claude/                      # Assistant skills & config
```

```
/opt/claude-ml-trading/            # Production server
├── docker-compose.yml             # Container orchestration
├── data/runtime.sqlite            # Database (decisions, trades)
├── models/*.joblib                # Trained models
└── logs/runtime.log               # Application logs
```

---

## 🔧 Quick Commands

### Check System Status
```bash
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose ps"
```

### View Recent Logs
```bash
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose logs --tail=50 claude-ml-trading"
```

### Analyze Decisions
```bash
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 24"
```

### Deploy Changes
```bash
cd "C:\Bot\claude_ml_system"
git add . && git commit -m "fix: description" && git push origin main
# GitHub Actions auto-deploys (~2-3 min)
```

---

## 🗄️ Database Schema

**Key Tables:**
- `signal_audit_log` - ALL decisions (ENTER/SKIP/WAIT) with full context
- `paper_trades` - Actual trade executions
- `model_decisions` - Legacy table (ENTER only)
- `runtime_state` - Adaptive thresholds state

---

## 🤖 Available Skills

**Project-Specific:**
- `/deploy` - Deploy to production
- `/analyze-signals` - Analyze model decisions
- `/check-models` - Verify model health
- `/monitor-decisions` - Real-time monitoring
- `/backtest` - Test strategies on historical data

**Universal:**
- Code Review, Debug, Documentation, Testing, Performance, Security, Data Analysis, Git

---

## 📊 Current Configuration

- **Symbol:** BTCUSDT only
- **Timeframe:** 15m candles
- **Mode:** Paper trading (not live money)
- **Server:** root@95.81.101.148
- **Models:** 3-model ensemble (early + confirmation + momentum)
- **Retraining:** Every 48h automatic
- **Thresholds:** Adaptive (base: 0.58/0.70/0.52)

---

## 🚨 Common Issues

**No signals generated:**
- Check if confidence scores are below adaptive thresholds
- Verify market regime detection isn't returning "unknown"
- Look at recent model retraining status

**Container unhealthy:**
- Check Docker logs for errors
- Verify database file isn't locked
- Ensure models loaded successfully

**Deployment failed:**
- Check GitHub Actions build logs
- Verify Docker image builds locally
- Test SSH connection to server

---

## 💡 Key Insights

1. **SKIP/WAIT decisions now logged** - Since Aug 5, all decisions saved to signal_audit_log
2. **Adaptive thresholds** - System adjusts based on market regime automatically
3. **Continuous learning** - Models retrain every 48h or when performance drops
4. **Trailing stop exit** - No fixed TP/SL, uses dynamic trailing mechanism

---

**Last Updated:** 2026-08-05
**Version:** 2.0.0
