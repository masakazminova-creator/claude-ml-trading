---
name: analyze-signals
description: Analyze model signals, decisions, and missed opportunities from database
---

# Signal Analysis Skill

Analyze trading signals and model decisions from the database.

## When to use
- User asks about signal quality or missed opportunities
- Need to check model performance
- Analyzing why certain trades were/weren't taken
- Reviewing threshold effectiveness

## Commands

```bash
# Quick overview (last 24h)
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 24"

# Detailed analysis (custom window)
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 48 --symbol BTCUSDT"

# Check database directly
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c \"import sqlite3; conn = sqlite3.connect('data/runtime.sqlite'); cursor = conn.cursor(); cursor.execute('SELECT action, COUNT(*) FROM signal_audit_log GROUP BY action'); [print(f'{r[0]}: {r[1]}') for r in cursor.fetchall()]; conn.close()\""
```

## What to look for

1. **Decision Distribution**: Are there too many SKIP? Too aggressive ENTER?
2. **Score vs Threshold**: Are thresholds appropriately set?
3. **Regime Analysis**: Performance in different market regimes
4. **Missed Opportunities**: Skipped signals with good subsequent returns

## Database tables

- `signal_audit_log` - ALL decisions with full context
- `model_decisions` - Legacy table (ENTER only)
- `paper_trades` - Actual trade executions

## Tips

- Compare scores against adaptive thresholds
- Look for patterns in regime column
- Use json_extract() to get confidence from payload_json
- Recent data is more relevant than old data
