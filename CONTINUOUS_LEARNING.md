# Claude ML - Continuous Learning System

## 🧠 Automatic Model Adaptation

The system now includes **automatic model retraining** that works without manual intervention.

---

## 🔄 How It Works

### **1. Performance Monitoring (Every Poll Cycle)**
- Tracks win rate, profit factor, drawdown
- Monitors recent performance (last 10/50 trades)
- Logs metrics to database

### **2. Drift Detection (Every 50 Trades)**
Checks if model performance has degraded:
- Win rate drop > 10% from baseline
- Profit factor < 1.0
- Recent performance much worse than overall
- Calibration loss (predicted vs actual probability)

### **3. Automatic Retraining Trigger**
Retrains when ANY of these conditions met:
- Every 100 trades (periodic refresh)
- Performance drift detected
- Profit factor too low (< 1.0 with 50+ trades)
- No trades yet (initial training)

### **4. A/B Testing & Promotion**
- Trains new models on fresh data (last 5000 bars)
- Walk-forward validation
- Compares with current models
- Promotes ONLY if new is better

### **5. Model Reload**
- Automatically loads new models into runtime
- No restart needed
- Seamless transition

---

## 📊 Retraining Triggers

| Trigger | Condition | Action |
|---------|-----------|--------|
| **Periodic** | Every 100 trades | Refresh with recent data |
| **Drift** | WR drop > 10%, PF < 1.0 | Immediate retrain |
| **Low Performance** | PF < 1.0 with 50+ trades | Diagnostic retrain |
| **Initial** | 0 trades | First training |

---

## 🔍 What Gets Retrained

1. **Early Signal Model** - Pre-breakout detection
2. **Confirmation Model** - With Platt scaling calibration
3. **Momentum Model** - Short-term direction

All models use:
- Last 5000 bars (recent market conditions)
- Walk-forward validation (5 folds)
- Same features and architecture

---

## 📈 Performance Metrics Tracked

```python
PerformanceMetrics:
  total_trades: int
  win_rate: float              # Overall win rate
  avg_pnl: float               # Average PnL per trade
  profit_factor: float         # Gross profit / gross loss
  recent_win_rate_10: float    # Last 10 trades WR
  recent_win_rate_50: float    # Last 50 trades WR
  max_drawdown: float          # Maximum drawdown %
```

---

## 🛡️ Safety Features

### **Model Promotion Gate**
New models promoted ONLY if:
- ✅ Training completes successfully
- ✅ Walk-forward validation passes
- ✅ Better than current metrics
- ✅ Calibration improved

### **Fallback**
If new model fails:
- Old models kept
- No interruption to trading
- Error logged to database

---

## 📝 Logs & Monitoring

### **Database Logs**
```sql
-- Check performance history
SELECT * FROM health_log
WHERE note LIKE '%performance_check%'
ORDER BY id DESC LIMIT 10;

-- Check retraining events
SELECT * FROM health_log
WHERE note LIKE '%retrain%' OR note LIKE '%drift%';
```

### **Console Output**
```
[AUTO-LEARN] === AUTOMATIC LEARNING CHECK ===
[AUTO-LEARN] Trades: 127, WR: 48.5%, PF: 1.23
[AUTO-LEARN] Drift detected: False (drop: 1.5%)
[AUTO-LEARN] Should retrain: False (No criteria met)
[AUTO-LEARN] Cycle complete
```

---

## ⚙️ Configuration

In `continuous_learning.py`, adjust thresholds:

```python
self.win_rate_drop_threshold = 0.10   # Alert if WR drops 10%
self.calibration_threshold = 0.3      # Min correlation for calibration
self.min_trades_for_check = 50        # Need 50+ trades to check
self.retrain_interval_trades = 100    # Retrain every 100 trades
self.training_lookback_bars = 5000    # Use last 5000 bars
```

---

## 🚀 Usage

Just run the system normally:

```bash
python scripts/run_with_logging.py
```

**Automatic learning happens in background:**
- No manual intervention needed
- No restart required
- Models update seamlessly
- You'll see logs when retraining occurs

---

## 📊 Example Retraining Scenario

**Scenario**: Market regime changed from trending to choppy

1. **Detection** (after 50 trades):
   - Win rate dropped from 52% → 38%
   - Profit factor dropped from 1.4 → 0.8
   - Drift flag: TRUE

2. **Retraining** (immediate):
   - Fetches last 5000 bars
   - Retrains all 3 models
   - Validates with walk-forward

3. **Promotion** (if better):
   - New models show WR 45%, PF 1.1
   - Old models: WR 38%, PF 0.8
   - ✓ PROMOTE new models

4. **Result**:
   - System adapts to new regime
   - Performance improves
   - No downtime

---

## 🎯 Benefits

✅ **No manual monitoring** - system self-checks  
✅ **Adapts to market changes** - always uses recent patterns  
✅ **Safe updates** - old models kept until proven better  
✅ **Zero downtime** - seamless model swaps  
✅ **Transparent** - full logging and metrics  

---

**System Version:** 0.2.0 (with Continuous Learning)  
**Last Updated:** 2026-07-25
