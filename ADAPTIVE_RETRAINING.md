# Adaptive Retraining System

## 🔄 Market-Responsive Model Updates

The system now automatically adjusts **how often** and **on what data** to retrain based on current market conditions.

---

## 🎯 Why Adaptive?

Crypto markets change rapidly:
- **High volatility periods** (ATR > 2%) → Need frequent updates with recent data
- **Low volatility periods** (ATR < 0.8%) → Can retrain less often with more history
- **Performance degradation** → Urgent retraining needed
- **Stable performance** → Normal schedule is fine

### **Old System (Fixed):**
```python
Retrain every: 100 trades (~25 hours)
Use last: 5000 bars (52 days)
```

**Problem:** Too slow for fast markets, too much historical bias.

### **New System (Adaptive):**
```python
High volatility (ATR > 2%):
  Retrain every: 20-30 trades (~5-8 hours)
  Use last: 500-800 bars (5-8 days)

Normal volatility (ATR 0.8-2%):
  Retrain every: 50-100 trades (~12-25 hours)
  Use last: 1000-2000 bars (10-21 days)

Low volatility (ATR < 0.8%):
  Retrain every: 150-200 trades (~37-50 hours)
  Use last: 3000-5000 bars (31-52 days)
```

---

## 📊 How It Works

### **1. Volatility Detection (ATR-based)**

System monitors ATR % to determine market state:

| ATR % | Market State | Action |
|-------|-------------|--------|
| > 2.0% | **High volatility** | Frequent retrain, short history |
| 1.5-2.0% | Elevated | More frequent retrain |
| 0.8-1.5% | **Normal** | Standard schedule |
| < 0.8% | Low volatility | Less frequent retrain |

### **2. Performance Monitoring**

Tracks win rate drop from baseline:

| WR Drop | Severity | Adjustment |
|---------|----------|------------|
| > 15% | **Critical** | Urgent retrain (0.3x interval) |
| 10-15% | High | Aggressive retrain (0.5x) |
| 5-10% | Moderate | Slight increase (0.8x) |
| < 5% | Normal | No change (1.0x) |

### **3. Adaptive Calculation**

Combines both factors:

```python
retrain_interval = base_interval × vol_multiplier × perf_multiplier
lookback_bars = base_lookback × vol_multiplier × perf_multiplier

# Example in high volatility + performance drop:
# base_interval = 100 trades
# vol_mult = 0.3 (high vol)
# perf_mult = 0.5 (WR drop 12%)
# Result: retrain every 15 trades, use 600 bars
```

---

## 🔧 Configuration

In `continuous_learning.py`:

```python
# Base values (normal market conditions)
self.base_retrain_interval_trades = 100
self.base_training_lookback_bars = 2000  # ~21 days on 15m

# Bounds
self.min_retrain_interval_trades = 20    # Never slower than this
self.max_retrain_interval_trades = 200   # Never faster than this
self.min_training_lookback_bars = 500    # At least 5 days
self.max_training_lookback_bars = 5000   # At most 52 days

# Volatility thresholds
self.high_volatility_atr_pct = 2.0       # What is "high"
self.low_volatility_atr_pct = 0.8        # What is "low"
```

---

## 💡 Real-World Examples

### **Scenario 1: BTC Flash Crash**

```
Market: BTC drops 10% in 2 hours
ATR spikes from 1.0% → 3.5%
Win rate drops from 52% → 35%

System response:
  - Detects high volatility (ATR 3.5%)
  - Detects WR drop (17%)
  - Calculates: retrain every 20 trades, use 500 bars
  - Retrains IMMEDIATELY with last 500 bars (most recent ~5 days)
  - Models adapt to new volatile regime
```

### **Scenario 2: Sideways Chop**

```
Market: BTC moves sideways for 3 days
ATR drops to 0.6%
Win rate stable at 48%

System response:
  - Detects low volatility (ATR 0.6%)
  - WR stable (no significant drop)
  - Calculates: retrain every 150 trades, use 3500 bars
  - Retrains less frequently with more history
  - Avoids overfitting to noise
```

### **Scenario 3: Gradual Trend Change**

```
Market: BTC slowly transitions from uptrend to downtrend over 2 weeks
ATR stays normal (1.2%)
Win rate gradually drops from 55% → 42%

System response:
  - Detects WR drop (13%)
  - Increases retrain frequency (0.5x multiplier)
  - Shortens lookback slightly (0.6x)
  - Models adapt to new trend without losing old knowledge
```

---

## 📈 Comparison: Fixed vs Adaptive

| Aspect | Fixed System | Adaptive System |
|--------|-------------|----------------|
| **Response to volatility** | None (always same) | Automatic adjustment |
| **Flash crash handling** | Uses 52-day history (too old) | Switches to 5-day history |
| **Choppy market** | Overfits to noise | Reduces frequency |
| **Performance degradation** | Waits 100 trades | Immediate retrain if severe |
| **Resource usage** | Constant | Efficient (less when stable) |

---

## 🎯 Expected Behavior

### **During High Volatility:**
```
[ADAPTIVE RETRAIN] ATR=3.20%, WR_drop=15.0%
[ADAPTIVE RETRAIN] Retrain every 20 trades, lookback 500 bars
[RETRAIN] Fetching recent data...
[RETRAIN] Fetched 500 candles (adaptive lookback: 500 bars)
```

### **During Stable Periods:**
```
[ADAPTIVE RETRAIN] ATR=0.90%, WR_drop=2.0%
[ADAPTIVE RETRAIN] Retrain every 120 trades, lookback 2500 bars
[RETRAIN] Fetching recent data...
[RETRAIN] Fetched 2500 candles (adaptive lookback: 2500 bars)
```

---

## 🚀 Benefits

✅ **Fast response to market changes** - retrains quickly in volatile periods  
✅ **Avoids overfitting** - uses appropriate amount of history  
✅ **Efficient resource usage** - doesn't waste compute when stable  
✅ **Always relevant** - models reflect current market regime  
✅ **Automatic tuning** - no manual parameter adjustment needed  

---

**System Version:** 0.5.0 (with Adaptive Retraining)  
**Last Updated:** 2026-07-25
