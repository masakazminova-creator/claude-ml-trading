---
name: monitor-decisions
description: Real-time monitoring of model decisions using CLI dashboard
---

# Decision Monitoring Skill

Monitor live trading decisions and system health.

## When to use
- Checking current system activity
- Reviewing recent trading decisions
- Analyzing signal patterns in real-time
- Debugging why certain actions were taken

## Commands

```bash
# Latest decisions (last hour)
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 1"

# Full day analysis
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 24"

# Specific symbol
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/monitor_decisions.py --symbol BTCUSDT --hours 6"

# Direct database query for quick check
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c \"import sqlite3; conn = sqlite3.connect('data/runtime.sqlite'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM signal_audit_log WHERE ts >= datetime(\"now\", \"-1 hour\")'); print(f'Last hour decisions:', cursor.fetchone()[0]); conn.close()\""
```

## Output interpretation

**Decision Distribution:**
- High ENTER % (>70%) → System is aggressive, thresholds may be low
- High SKIP % (>50%) → System is conservative, thresholds may be high
- Balanced mix → Normal operation

**Score Analysis:**
- Early > 0.65 + Confirm > 0.75 → Strong signals
- Momentum near 0.50 → Neutral/no clear trend
- Compare scores vs thresholds to see decision logic

**Missed Opportunities:**
- Look for SKIP with confirm_score close to threshold
- Check if regime was unfavorable
- Analyze if thresholds need adjustment

## Tips

- Run every few hours during active trading
- Compare different time windows to spot patterns
- Use alongside `/analyze-signals` for deeper insights
- Watch for regime changes affecting decision patterns
