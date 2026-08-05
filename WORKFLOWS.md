# Common Workflows - Claude ML Trading System

**Step-by-step guides for typical operations**

---

## 1. Deploy New Feature/Change

### Scenario: You've made code changes and want to deploy

```bash
# Step 1: Verify changes locally
cd "C:\Bot\claude_ml_system"
git status

# Step 2: Commit with descriptive message
git add .
git commit -m "feat: Add adaptive threshold monitoring"

# Step 3: Push to trigger auto-deploy
git push origin main

# Step 4: Wait 2-3 minutes for GitHub Actions build

# Step 5: Verify deployment
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose ps"

# Step 6: Check logs for errors
ssh root@95.81.101.148 "docker-compose logs --tail=50"

# Step 7: Test functionality
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 1"
```

**If deployment fails:**
- Check GitHub Actions logs
- Try manual rebuild on server
- Rollback if critical: `git revert HEAD && git push`

---

## 2. Analyze Why Signal Was Missed

### Scenario: User asks "Why didn't we enter this trade?"

```bash
# Step 1: Get decision history
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 24"

# Step 2: Look for SKIP/WAIT decisions around that time
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c \"
import sqlite3
conn = sqlite3.connect('data/runtime.sqlite')
cursor = conn.cursor()
cursor.execute('''
    SELECT ts, action, early_probability, confirmation_probability, 
           adaptive_confirmation_threshold, regime
    FROM signal_audit_log 
    WHERE ts LIKE \"2026-08-05 14:%\"
    ORDER BY ts
''')
for row in cursor.fetchall():
    print(row)
conn.close()
\""

# Step 3: Analyze scores vs thresholds
# - If confirm_score < threshold → correctly skipped
# - If confirm_score > threshold but still skipped → check regime/momentum

# Step 4: Check market conditions at that time
ssh root@95.81.101.148 "docker-compose logs | grep '14:XX' | grep BTCUSDT"
```

---

## 3. Debug Container Issues

### Scenario: Container is unhealthy or not responding

```bash
# Step 1: Check container status
ssh root@95.81.101.148 "docker-compose ps"

# Step 2: View recent logs
ssh root@95.81.101.148 "docker-compose logs --tail=100 claude-ml-trading"

# Step 3: Check for specific errors
ssh root@95.81.101.148 "docker-compose logs | grep -i error"
ssh root@95.81.101.148 "docker-compose logs | grep -i exception"
ssh root@95.81.101.148 "docker-compose logs | grep -i fatal"

# Step 4: Enter container for debugging
ssh root@95.81.101.148 "docker exec -it claude-ml-bot bash"

# Inside container:
ls -la /app/src/claude_ml/
python -c "from claude_ml.runtime import RuntimeEngine; print('Import OK')"
ls -lh /app/models/*.joblib

# Step 5: Restart if needed
ssh root@95.81.101.148 "docker-compose restart claude-ml-trading"

# Step 6: If still failing, check database integrity
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c \"
import sqlite3
try:
    conn = sqlite3.connect('data/runtime.sqlite')
    cursor = conn.cursor()
    cursor.execute('PRAGMA integrity_check')
    result = cursor.fetchone()
    print(f'Database integrity: {result[0]}')
    conn.close()
except Exception as e:
    print(f'Database error: {e}')
\""
```

---

## 4. Model Retraining Check

### Scenario: Suspect models need retraining

```bash
# Step 1: Check model age
ssh root@95.81.101.148 "docker exec claude-ml-bot bash -c 'ls -lh models/*.joblib'"

# Step 2: Check continuous learning status
ssh root@95.81.101.148 "docker-compose logs | grep -i 'retrain\|learn'"

# Step 3: Check model performance metrics
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/diagnose_model_quality.py"

# Step 4: Manual retraining if needed
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/train_models.py"

# Step 5: Verify new models loaded
ssh root@95.81.101.148 "docker-compose logs | grep 'Models reloaded'"
```

---

## 5. Threshold Tuning Workflow

### Scenario: Want to optimize entry/exit thresholds

```bash
# Step 1: Run backtest with current thresholds
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/backtest.py --days 30"

# Step 2: Test different threshold combinations
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/backtest.py \
  --early-thresh 0.60 \
  --confirm-thresh 0.72 \
  --momentum-thresh 0.55"

# Step 3: Compare results (win rate, profit factor, drawdown)

# Step 4: If improvement confirmed, update base thresholds in code
# Edit: src/claude_ml/adaptive_thresholds.py
# Change: base_thresholds values

# Step 5: Commit and deploy changes
git add . && git commit -m "tune: Adjust base thresholds to 0.60/0.72/0.55" && git push

# Step 6: Monitor real-world performance after change
```

---

## 6. Emergency Stop Procedure

### Scenario: Need to halt trading immediately

```bash
# Step 1: Stop the trading bot (keep data intact)
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose stop claude-ml-trading"

# Step 2: Verify stopped
ssh root@95.81.101.148 "docker-compose ps"

# Step 3: To restart when ready
ssh root@95.81.101.148 "docker-compose start claude-ml-trading"

# For complete shutdown (stops all services):
ssh root@95.81.101.148 "docker-compose down"
# To bring back up:
ssh root@95.81.101.148 "docker-compose up -d"
```

---

## 7. Code Review Session

### Scenario: Review new implementation before merge

```bash
# Step 1: Read changed files
git diff HEAD~1..HEAD --name-only

# Step 2: Apply Code Review skill dimensions
# - Correctness: Edge cases, error handling?
# - Efficiency: Unnecessary loops, optimal algorithms?
# - Tests: Coverage adequate?
# - Security: Input validation, no hardcoded secrets?

# Step 3: Run tests if they exist
cd "C:\Bot\claude_ml_system"
python -m pytest tests/ -v

# Step 4: Check for common issues
grep -r "TODO\|FIXME\|HACK" src/

# Step 5: Provide structured feedback
# Use Code Review skill output format
```

---

## 8. Data Analysis Request

### Scenario: Analyze trading patterns from database

```bash
# Step 1: Extract data
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c \"
import sqlite3
import pandas as pd

conn = sqlite3.connect('data/runtime.sqlite')
df = pd.read_sql_query('''
    SELECT ts, action, confidence_pct, regime, 
           json_extract(payload_json, \"$.close_price\") as price
    FROM signal_audit_log
    WHERE ts >= datetime(\"now\", \"-7 days\")
''', conn)

print(df.describe())
print(df.groupby('action').size())
print(df.groupby('regime').size())

conn.close()
\""

# Step 2: Visualize patterns (if matplotlib available)
# Or export to CSV and analyze locally

# Step 3: Generate insights report
# - Decision distribution
# - Confidence trends
# - Regime effectiveness
# - Missed opportunities
```

---

## Tips for All Workflows

1. **Document what you do** - Add comments to memory files
2. **Verify each step** - Don't assume, check actual state
3. **Keep notes** - Record what worked/didn't work
4. **Ask for clarification** - If user request is ambiguous
5. **Test before deploying** - Especially threshold changes

---

**Last Updated:** 2026-08-05
**Total Workflows:** 8 common scenarios
