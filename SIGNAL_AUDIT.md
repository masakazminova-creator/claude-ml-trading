# Signal Audit System - Understanding Missed Opportunities

## 🔍 Problem Solved

**Scenario:** You see a clear price movement on chart (e.g., BTC drops 2%), but the model didn't enter. Why?

The Signal Audit System logs **every decision point** with full context so you can analyze WHY the model skipped an opportunity.

---

## 📊 What Gets Logged

Every bar (every 15 seconds by default), the system logs:

### **Market State**
- Timestamp
- Close price
- ATR % (volatility)
- Market regime (trend/chop/expansion/etc.)

### **Model Predictions**
- Early signal probability
- Confirmation probability
- Momentum score

### **Adaptive Thresholds**
- Current early threshold
- Current confirmation threshold
- Current momentum threshold

### **Decision & Reasoning**
- Action taken (enter/skip/wait)
- Reason why (e.g., "Confirm prob 0.37 < threshold 0.70")

### **Feature Snapshot**
- Key feature values at that moment
- RSI, EMA gap, volume z-score, etc.

### **Future Outcome** (for post-hoc analysis)
- What happened in next 1/3/6 bars
- High/low after the decision

---

## 🛠️ How to Use

### **1. Query by Time Period**

When you see a missed signal on chart, note the timestamp and query:

```python
from claude_ml.signal_audit import SignalAuditEngine
from claude_ml.config import Settings

settings = Settings()
audit = SignalAuditEngine(settings)

# Query specific time period
records = audit.query_by_time(
    start_ts="2026-07-25T14:00:00",
    end_ts="2026-07-25T15:00:00",
    symbol="BTCUSDT"
)

for r in records:
    print(f"{r['ts']}: {r['action']} | Confirm: {r['confirmation_probability']:.3f} | Regime: {r['regime']}")
```

### **2. Find Missed Opportunities**

Find times when model skipped but price moved significantly:

```python
missed = audit.find_missed_signals(min_future_return=1.0, limit=10)

for m in missed:
    print(f"\n{m['ts']}:")
    print(f"  Skipped, but price moved +{m['next_6bar_return']:.2f}%")
    print(f"  Reason: {m['action_reason']}")
    print(f"  Confirm prob: {m['confirmation_probability']:.3f} vs threshold: {m['adaptive_confirmation_threshold']:.3f}")
```

### **3. Detailed Analysis of Specific Signal**

Get full breakdown of why a specific signal was skipped:

```python
analysis = audit.analyze_missed_signal(
    ts="2026-07-25T14:32:15+00:00",
    symbol="BTCUSDT"
)

print(f"\nWhy signal was skipped:")
for reason in analysis['why_skipped']:
    print(f"  - {reason}")

print(f"\nProbabilities vs Thresholds:")
print(f"  Early: {analysis['probabilities']['early']:.3f} vs {analysis['thresholds']['early']:.3f}")
print(f"  Confirm: {analysis['probabilities']['confirmation']:.3f} vs {analysis['thresholds']['confirmation']:.3f}")
print(f"  Momentum: {analysis['probabilities']['momentum']:.3f} vs {analysis['thresholds']['momentum']:.3f}")

print(f"\nOutcome:")
print(f"  Next 6 bars: {analysis['outcome']['next_6bar_return']:.2f}%")
```

### **4. Generate Report**

Generate human-readable report for a time period:

```python
report = audit.generate_report(
    start_ts="2026-07-25T12:00:00",
    end_ts="2026-07-25T18:00:00",
    symbol="BTCUSDT"
)

print(report)
```

Output example:
```
================================================================================
SIGNAL AUDIT REPORT: BTCUSDT
Period: 2026-07-25T12:00:00 to 2026-07-25T18:00:00
Total bars analyzed: 240
================================================================================

Action Distribution:
  skip: 198 bars
  wait: 32 bars
  enter_full: 10 bars

Top 5 Missed Opportunities:
  2026-07-25T14:32:15+00:00: Skipped, but price moved +1.85%
    Reason: Confirm prob too low
    Confirm prob: 0.423 vs threshold: 0.700
  ...
```

---

## 💡 Common Scenarios

### **Scenario 1: "Why did we miss this drop?"**

You see BTC dropped 3% at 14:30 but model didn't short.

**Solution:**
```python
analysis = audit.analyze_missed_signal("2026-07-25T14:30:00+00:00", "BTCUSDT")
```

Possible results:
- `Confirmation prob (0.38) < threshold (0.70)` → Model wasn't confident enough
- `Regime: chop (thresholds raised 25%)` → Market was choppy, system was cautious
- `Momentum against us (0.28 < 0.55)` → Momentum model said no

### **Scenario 2: "Are thresholds too high?"**

You see many missed opportunities where confirm prob was 0.50-0.65 but threshold is 0.70.

**Solution:** Lower base threshold in `adaptive_thresholds.py`:
```python
"BTCUSDT": AdaptiveThreshold(
    confirmation_threshold=0.60,  # Was 0.70
    ...
)
```

### **Scenario 3: "Model works in trends but not chop"**

Analysis shows most misses happen in `chop` regime.

**Solution:** Adjust regime multiplier:
```python
regime_multipliers = {
    "chop": 1.15,  # Was 1.25 - less penalty
    ...
}
```

---

## 📈 Database Schema

```sql
CREATE TABLE signal_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    close_price REAL NOT NULL,
    atr_pct REAL,
    regime TEXT,
    early_probability REAL,
    confirmation_probability REAL,
    momentum_score REAL,
    adaptive_early_threshold REAL,
    adaptive_confirmation_threshold REAL,
    adaptive_momentum_threshold REAL,
    action TEXT NOT NULL,
    action_reason TEXT,
    features_json TEXT,
    next_1bar_return REAL,
    next_3bar_return REAL,
    next_6bar_return REAL,
    next_high REAL,
    next_low REAL,
    payload_json TEXT
)
```

---

## 🎯 Benefits

✅ **Full transparency** - see exactly why model made each decision  
✅ **Post-hoc analysis** - understand missed opportunities  
✅ **Parameter tuning** - adjust thresholds based on real data  
✅ **Debugging tool** - identify systematic issues  
✅ **Performance improvement** - learn from mistakes  

---

## 🚀 Quick Start

After running paper trading for a while:

```bash
cd C:\Bot\claude_ml_system
.venv\Scripts\activate

# Query recent decisions
python -c "
from claude_ml.signal_audit import SignalAuditEngine
from claude_ml.config import Settings
from datetime import datetime, timedelta

settings = Settings()
audit = SignalAuditEngine(settings)

# Last hour
end = datetime.now()
start = end - timedelta(hours=1)

report = audit.generate_report(
    start.isoformat(),
    end.isoformat(),
    'BTCUSDT'
)
print(report)
"
```

---

**Now you can always answer: "Why did the model miss that signal?"** 🔍
