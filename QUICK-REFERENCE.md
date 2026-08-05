# Quick Reference Card - Claude ML Trading System

**Common Operations & Troubleshooting**

---

## 🚀 Most Common Commands

### 1. Check if system is running
```bash
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose ps"
```

### 2. View latest decisions
```bash
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 1"
```

### 3. Deploy code changes
```bash
cd "C:\Bot\claude_ml_system"
git add . && git commit -m "fix: your description" && git push origin main
# Wait 2-3 minutes for auto-deploy
```

### 4. Check deployment status
```bash
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose logs --tail=20"
```

---

## 🔍 Troubleshooting Flowchart

### Problem: No trades happening

**Step 1:** Check recent decisions
```bash
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 6"
```
- If all SKIP → Confidence below thresholds (normal)
- If errors → Check error messages

**Step 2:** Check model health
```bash
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/diagnose_model_quality.py"
```

**Step 3:** Verify containers healthy
```bash
ssh root@95.81.101.148 "docker-compose ps"
# All should show "healthy"
```

---

### Problem: System not responding

**Step 1:** Check container status
```bash
ssh root@95.81.101.148 "docker-compose ps"
```

**Step 2:** Restart if needed
```bash
ssh root@95.81.101.148 "docker-compose restart claude-ml-trading"
```

**Step 3:** Check logs for errors
```bash
ssh root@95.81.101.148 "docker-compose logs --tail=100 | grep -i error"
```

---

### Problem: Deployment failed

**Step 1:** Check GitHub Actions
- Go to: https://github.com/masakazminova-creator/claude-ml-trading/actions
- Look for failed workflow

**Step 2:** Build locally to test
```bash
cd "C:\Bot\claude_ml_system"
docker build -t test-build .
# If fails, fix Dockerfile issues
```

**Step 3:** Manual deploy if auto fails
```bash
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && git pull && docker-compose up -d --build"
```

---

## 📊 Database Queries Cheat Sheet

### Count decisions by type
```bash
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c \"
import sqlite3
conn = sqlite3.connect('data/runtime.sqlite')
cursor = conn.cursor()
cursor.execute('SELECT action, COUNT(*) FROM signal_audit_log GROUP BY action')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]}')
conn.close()
\""
```

### View recent trades
```bash
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c \"
import sqlite3
conn = sqlite3.connect('data/runtime.sqlite')
cursor = conn.cursor()
cursor.execute('SELECT * FROM paper_trades ORDER BY id DESC LIMIT 5')
for row in cursor.fetchall():
    print(row)
conn.close()
\""
```

---

## 🎯 Skill Invocation

When user asks about:

**"Deploy/Push to production"** → Use `/deploy` skill
**"Why no signals?"** → Use `/analyze-signals` skill  
**"Check models"** → Use `/check-models` skill
**"Monitor activity"** → Use `/monitor-decisions` skill
**"Test strategy"** → Use `/backtest` skill
**"Review this code"** → Use Code Review universal skill
**"Fix this bug"** → Use Debug universal skill
**"Write tests"** → Use Testing universal skill

---

## ⚡ Performance Tips

1. **SSH Connection Reuse:**
   ```bash
   # Add to ~/.ssh/config
   Host server
     ControlMaster auto
     ControlPath ~/.ssh/connections/%r@%h:%p
     ControlPersist 600
   ```

2. **Faster Git Operations:**
   ```bash
   git config --global credential.helper store  # Cache credentials
   ```

3. **Docker Cleanup:**
   ```bash
   docker system prune -a  # Remove unused images/containers
   ```

---

## 📞 When Stuck

1. Check PROJECT-SUMMARY.md for context
2. Read relevant skill documentation
3. Search logs for error patterns
4. Ask user for clarification if needed
5. Don't guess - verify assumptions with evidence

---

**Remember:** Always verify current state before making changes!
