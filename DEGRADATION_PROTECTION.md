# Claude ML - Degradation Protection System

## 🛡️ Multi-Layer Safety Mechanisms

The system now includes **comprehensive protection** against model degradation and market regime changes.

---

## 🔒 Protection Layers

### **Layer 1: Performance Monitoring (Continuous)**
- Tracks win rate, profit factor, drawdown in real-time
- Monitors recent performance (last 10/50 trades)
- Logs all metrics to database for analysis

### **Layer 2: Drift Detection (Every 50 Trades)**
Detects when model predictions diverge from reality:
- Win rate drop > 10% from baseline
- Profit factor < 1.0 (losing money)
- Recent performance much worse than overall
- Calibration loss (predicted probability vs actual outcomes)

### **Layer 3: Circuit Breaker (Every Poll Cycle)**
**EMERGENCY STOP** triggered if ANY of these conditions met:

| Condition | Threshold | Action |
|-----------|-----------|--------|
| **Win Rate** | < 35% | Alert & retrain |
| **Critical Win Rate** | < 30% | **EMERGENCY STOP** |
| **Max Drawdown** | > 20% | **EMERGENCY STOP** |
| **Profit Factor** | < 0.8 (with 30+ trades) | Alert & retrain |
| **Recent WR (10 trades)** | < 30% | **EMERGENCY STOP** |
| **Consecutive Losses** | 8+ losses | **EMERGENCY STOP** |

### **Layer 4: Automatic Retraining**
When degradation detected:
1. Fetches last 5000 bars (recent market data)
2. Retrains all 3 models (Early, Confirmation, Momentum)
3. Walk-forward validation (5 folds)
4. A/B tests against current models
5. Promotes ONLY if new is better
6. Automatically reloads models (no restart needed)

### **Layer 5: Trading Pause**
When emergency stop triggered:
- **Trading HALTED** immediately
- System attempts automatic retrain
- Checks if retrain fixed the issue
- Resumes only if metrics improve
- Stays paused if problem persists

---

## 🚨 Emergency Stop Conditions

### **Example Scenario:**

```
Market suddenly becomes very choppy
↓
Model starts making wrong predictions
↓
Win rate drops from 50% → 28%
↓
Last 10 trades: ALL LOSSES
↓
🛑 CIRCUIT BREAKER TRIGGERS
↓
Trading PAUSED
↓
System attempts emergency retrain
↓
If retrain fixes → resume trading
If not → stay paused until manual intervention
```

---

## 📊 Real-Time Metrics Tracked

```python
PerformanceMetrics:
  total_trades: int                # Total completed trades
  win_rate: float                  # Overall win rate %
  avg_pnl: float                   # Average PnL per trade
  profit_factor: float             # Gross profit / gross loss
  recent_win_rate_10: float        # Last 10 trades WR %
  recent_win_rate_50: float        # Last 50 trades WR %
  max_drawdown: float              # Maximum peak-to-trough DD %
```

---

## ⚙️ Configuration Thresholds

In `continuous_learning.py`:

```python
# Warning thresholds
self.win_rate_drop_threshold = 0.10      # Alert if WR drops 10%
self.min_acceptable_wr = 35.0            # Min acceptable WR 35%
self.min_acceptable_pf = 0.8             # Min acceptable PF 0.8
self.max_acceptable_dd = 20.0            # Max drawdown 20%

# Emergency stop thresholds
self.emergency_stop_wr = 30.0            # STOP if WR < 30%
self.consecutive_losses_threshold = 8    # STOP after 8 consecutive losses
```

---

## 🔄 Auto-Retraining Triggers

| Trigger | Severity | Action |
|---------|----------|--------|
| Every 100 trades | Low | Periodic refresh |
| Drift detected | Medium | Diagnostic retrain |
| PF < 1.0 with 50+ trades | Medium | Performance retrain |
| Win rate < 35% | High | Urgent retrain |
| Emergency stop | Critical | **IMMEDIATE retrain + pause** |

---

## 🛡️ Circuit Breaker Workflow

```
1. Check metrics every poll cycle
   ↓
2. EMERGENCY CHECK:
   - Win rate catastrophic? (< 30%)
   - Drawdown too high? (> 20%)
   - 10+ consecutive losses?
   ↓
3. If YES → TRIGGER CIRCUIT BREAKER:
   - PAUSE all trading
   - Log reason to database
   - Attempt emergency retrain
   ↓
4. After retrain:
   - Check metrics again
   - If improved → RESUME trading
   - If not → STAY PAUSED
   ↓
5. Manual intervention may be required
```

---

## 📝 Logs & Monitoring

### **Console Output:**
```
[CIRCUIT BREAKER] TRADING PAUSED: CRITICAL: Win rate 28.5% below minimum 35%
[CIRCUIT BREAKER] Checking performance and attempting retrain...

[AUTO-LEARN] === AUTOMATIC LEARNING CHECK ===
[AUTO-LEARN] Trades: 127, WR: 28.5%, PF: 0.72
[AUTO-LEARN] EMERGENCY STOP TRIGGERED!
[AUTO-LEARN] Reason: CRITICAL: Win rate 28.5% below minimum 35%
[AUTO-LEARN] Attempting emergency retrain...

[RETRAIN] STARTING MODEL RETRAINING
[RETRAIN] Fetching recent data...
[RETRAIN] Training new models...
[RETRAIN] Models saved and promoted

[AUTO-LEARN] ✓ Emergency retrain completed, models updated
[AUTO-LEARN] ✓ Issue resolved! Resuming trading
```

### **Database Queries:**
```sql
-- Check performance history
SELECT ts, note FROM health_log
WHERE note LIKE '%performance_check%'
ORDER BY id DESC LIMIT 20;

-- Check emergency stops
SELECT * FROM health_log
WHERE note LIKE '%CRITICAL%' OR note LIKE '%emergency%';

-- Check retraining events
SELECT * FROM health_log
WHERE note LIKE '%retrain%' OR note LIKE '%drift%';
```

---

## 💡 Best Practices

### **1. Monitor Regularly**
Check console logs and database for:
- Warning signs (WR dropping, PF declining)
- Circuit breaker activations
- Retraining events

### **2. Adjust Thresholds**
If too sensitive (too many false alarms):
- Increase `min_acceptable_wr` to 38%
- Increase `max_acceptable_dd` to 25%

If not sensitive enough (missing problems):
- Decrease `emergency_stop_wr` to 28%
- Decrease `consecutive_losses_threshold` to 6

### **3. Manual Intervention**
If system stays paused after multiple retrains:
- Market regime may have fundamentally changed
- Consider switching to different strategy
- Review recent trades for patterns

---

## 🎯 Expected Behavior

### **Normal Operation:**
- Win rate: 45-55%
- Profit factor: 1.2-1.5
- Drawdown: < 10%
- No circuit breaker triggers

### **Warning Signs:**
- Win rate: 35-45%
- Profit factor: 0.8-1.0
- Drawdown: 10-15%
- Retraining every 100-200 trades

### **Emergency Stop:**
- Win rate: < 30%
- Profit factor: < 0.8
- Drawdown: > 20%
- 8+ consecutive losses
- Circuit breaker ACTIVE

---

## 🚀 Summary

✅ **Continuous monitoring** - checks every poll cycle  
✅ **Multi-layer protection** - drift → retrain → emergency stop  
✅ **Automatic recovery** - attempts retrain before pausing  
✅ **Safe resumption** - only resumes if metrics improve  
✅ **Full transparency** - all events logged to database  

**Your capital is protected by automated risk management!** 🛡️

---

**System Version:** 0.3.0 (with Degradation Protection)  
**Last Updated:** 2026-07-25
