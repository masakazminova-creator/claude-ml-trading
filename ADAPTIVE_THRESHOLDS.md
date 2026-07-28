# Adaptive Thresholds System

## 🎯 Per-Symbol Dynamic Threshold Adjustment

The system now automatically adjusts entry thresholds for each symbol (BTC, ETH, XRP) based on their unique characteristics and current market conditions.

---

## 🔍 Why Different Thresholds Per Symbol?

| Symbol | Characteristics | Typical Behavior | Threshold Strategy |
|--------|----------------|------------------|-------------------|
| **BTCUSDT** | Lower volatility, more stable | Trends well, less noise | **Lower thresholds** (0.70 confirm) |
| **ETHUSDT** | Medium volatility | Balanced behavior | **Medium thresholds** (0.75 confirm) |
| **XRPUSDT** | Higher volatility, whipsaws | More choppy, false breakouts | **Higher thresholds** (0.78 confirm) |

---

## 📊 How It Works

### **1. Base Thresholds (Starting Point)**
```python
BTCUSDT:  early=0.58, confirm=0.70, momentum=0.52
ETHUSDT:  early=0.60, confirm=0.75, momentum=0.55
XRPUSDT:  early=0.62, confirm=0.78, momentum=0.58
```

### **2. Regime Adjustment**
Multiplies threshold based on market regime:

| Regime | Multiplier | Effect |
|--------|-----------|--------|
| trend_up | 0.85 | **Easier** to enter (strong trend) |
| expansion | 0.88 | Easier to enter |
| flat | 1.15 | **Harder** to enter (choppy) |
| chop | 1.25 | Much harder to enter |

**Example:**
```
BTC in trend_up: 0.70 × 0.85 = 0.595 (easier)
BTC in chop:     0.70 × 1.25 = 0.875 (harder)
```

### **3. Performance Adjustment**
Adjusts based on recent win rate and profit factor:

```python
If WR < target (50%):
    → Lower threshold (be less selective)

If WR > target:
    → Raise threshold (can be more selective)

If PF < 1.0:
    → Lower threshold (need to try different signals)
```

### **4. Volatility Adjustment**
Based on ATR percentage:

| ATR % | Multiplier | Reason |
|-------|-----------|--------|
| > 2.0% | 1.15 | High vol → need more confidence |
| 1.5-2.0% | 1.08 | Elevated vol |
| 1.0-1.5% | 1.00 | Normal vol |
| 0.7-1.0% | 0.95 | Low vol → can enter easier |
| < 0.7% | 0.90 | Very low vol |

### **5. Smooth Transition**
New thresholds blend with old (70% old + 30% new) to prevent sudden jumps.

---

## 💡 Example Calculation

**Scenario: BTC in uptrend with good performance**

```
Base threshold:           0.70
Regime (trend_up):        × 0.85 = 0.595
Performance (WR 55%):     × 0.95 = 0.565
Volatility (ATR 1.2%):    × 1.00 = 0.565
Smooth transition:        0.7×0.70 + 0.3×0.565 = 0.660

Final threshold: 0.660 (vs original 0.70)
```

**Result:** System becomes **more aggressive** in favorable conditions!

---

## 🔄 Real-Time Adaptation

Thresholds update **every poll cycle** (every 15 seconds by default):

1. Check current regime for symbol
2. Calculate regime adjustment
3. Check recent performance
4. Calculate performance adjustment
5. Get current ATR
6. Calculate volatility adjustment
7. Apply all adjustments with smoothing
8. Use new threshold for decisions

---

## 📈 Expected Behavior

### **Favorable Conditions** (trending, good performance):
- Thresholds drop from 0.75 → 0.60-0.65
- More signals generated
- Easier to enter trades

### **Unfavorable Conditions** (chop, poor performance):
- Thresholds rise from 0.75 → 0.85-0.90
- Fewer signals generated
- Harder to enter trades

### **Different Symbols:**
- BTC: Always slightly lower (more stable)
- XRP: Always slightly higher (more volatile)
- ETH: In between

---

## 🛡️ Safety Bounds

Thresholds cannot go below/above these limits:

| Type | Min | Max |
|------|-----|-----|
| Early Signal | 0.45 | 0.75 |
| Confirmation | 0.55 | 0.90 |
| Momentum | 0.40 | 0.70 |

This prevents:
- Too low → entering every signal
- Too high → never entering

---

## 📝 Monitoring & Logs

Console output shows adaptive adjustments:

```
[ADAPTIVE] BTCUSDT: regime=trend_up, multiplier=0.85
[ADAPTIVE] BTCUSDT: WR=55.2%, PF=1.35, perf_multiplier=0.92
[ADAPTIVE] BTCUSDT: ATR=1.23%, vol_multiplier=1.00
[ADAPTIVE] BTCUSDT confirmation: final_threshold=0.660

[ADAPTIVE] XRPUSDT: regime=chop, multiplier=1.25
[ADAPTIVE] XRPUSDT: WR=42.1%, PF=0.89, perf_multiplier=1.08
[ADAPTIVE] XRPUSDT: ATR=2.15%, vol_multiplier=1.15
[ADAPTIVE] XRPUSDT confirmation: final_threshold=0.892
```

Notice:
- **BTC** has lower threshold (0.660) in uptrend
- **XRP** has higher threshold (0.892) in chop

---

## ⚙️ Configuration

In `adaptive_thresholds.py`, adjust base values:

```python
self.base_thresholds = {
    "BTCUSDT": AdaptiveThreshold(
        early_signal_threshold=0.58,   # Adjust per symbol
        confirmation_threshold=0.70,
        momentum_threshold=0.52,
    ),
    ...
}
```

Or adjust regime multipliers:

```python
regime_multipliers = {
    "trend_up": 0.85,      # More aggressive in trends
    "chop": 1.25,          # More cautious in chop
    ...
}
```

---

## 🎯 Benefits

✅ **Per-symbol optimization** - each asset has appropriate thresholds  
✅ **Market-aware** - adapts to current regime automatically  
✅ **Performance-tuned** - adjusts based on recent results  
✅ **Volatility-aware** - accounts for symbol characteristics  
✅ **Smooth transitions** - no sudden changes  
✅ **Safe bounds** - prevents extreme values  

---

## 🚀 Usage

Just run normally - adaptive thresholds work automatically:

```bash
python scripts/run_with_logging.py
```

You'll see logs like:
```
[ADAPTIVE] BTCUSDT thresholds: early=0.621, confirm=0.660, momentum=0.548
[ADAPTIVE] ETHUSDT thresholds: early=0.635, confirm=0.712, momentum=0.571
[ADAPTIVE] XRPUSDT thresholds: early=0.687, confirm=0.823, momentum=0.612
```

Each symbol now has **custom thresholds** optimized for its behavior!

---

**System Version:** 0.4.0 (with Adaptive Thresholds)  
**Last Updated:** 2026-07-25
