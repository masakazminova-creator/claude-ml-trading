# Next Session Start Guide - Claude ML Trading System

**Read this FIRST when user says "продолжи работу над Claude ML"**

---

## 🚀 Quick Start (Do This First!)

### Step 1: Read Project Context
```
READ: PROJECT-SUMMARY.md (in project root)
```
This gives you instant context about:
- What the system does (BTC trading bot)
- Current status (production, paper trading)
- Server details (root@95.81.101.148)
- Available skills and commands

### Step 2: Check Recent Memory
```
READ: ~/.claude/projects/C--Users-User/memory/session-august-5-complete-status.md
```
This tells you:
- What was done in last session (Aug 5)
- New features added (decision logging, monitoring)
- Current issues being worked on

### Step 3: Verify System Status
```bash
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose ps"
```

---

## 📚 Available Documentation

**For Quick Reference:**
- `QUICK-REFERENCE.md` - Common commands and troubleshooting
- `WORKFLOWS.md` - Step-by-step guides for 8 common scenarios
- `.claude/universal-skills.md` - 8 core competencies I can apply

**For Specific Tasks:**
- Use `/deploy` skill for deployment
- Use `/analyze-signals` for decision analysis
- Use `/check-models` for model health
- Use `/monitor-decisions` for real-time monitoring
- Use `/backtest` for strategy testing

---

## 🎯 What User Might Ask

### Common Requests:

**"Почему нет сигналов?"**
→ Use `/analyze-signals` skill
→ Check monitor_decisions.py output
→ Look at confidence vs thresholds

**"Задеплой изменения"**
→ Use `/deploy` skill
→ Follow deploy workflow from WORKFLOWS.md

**"Проверь модели"**
→ Use `/check-models` skill
→ Run diagnose_model_quality.py
→ Check model file ages

**"Оптимизируй пороги"**
→ Use `/backtest` skill
→ Test different threshold combinations
→ Compare win rates

**"Посмотри логи"**
→ Check QUICK-REFERENCE.md for log commands
→ ssh to server and view docker-compose logs

---

## 🔧 Essential Commands

### Check System Health
```bash
ssh root@95.81.101.148 "docker-compose ps"
```

### View Recent Decisions
```bash
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 1"
```

### Check Database
```bash
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c \"import sqlite3; conn = sqlite3.connect('data/runtime.sqlite'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM signal_audit_log'); print('Total decisions:', cursor.fetchone()[0]); conn.close()\""
```

---

## 💡 Key Things to Remember

1. **System logs ALL decisions now** (since Aug 5) - check signal_audit_log table
2. **Adaptive thresholds** adjust automatically based on market regime
3. **Paper trading mode** - no real money involved
4. **Auto-deploy via GitHub Actions** - just push to main branch
5. **Continuous learning** - models retrain every 48 hours

---

## 🆘 If Something Doesn't Work

1. **Check documentation first** - most answers are in the markdown files
2. **Verify system status** - docker-compose ps
3. **Check logs** - docker-compose logs --tail=50
4. **Ask user for clarification** if context is unclear
5. **Don't guess** - verify assumptions with evidence

---

## 📞 Useful Resources

- **Git Repo:** https://github.com/masakazminova-creator/claude-ml-trading
- **Server:** root@95.81.101.148
- **Local Path:** C:\Bot\claude_ml_system
- **Server Path:** /opt/claude-ml-trading

---

**Last Updated:** 2026-08-05
**Version:** 2.0.0
**Status:** Ready for next session! 🚀
