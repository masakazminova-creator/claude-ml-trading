---
name: check-models
description: Check model health, versions, training status, and performance metrics
---

# Model Health Check Skill

Verify the state of ML models in the trading system.

## When to use
- User asks about model quality or performance
- Checking if models need retraining
- After deployment to verify models loaded correctly
- Before making threshold changes

## Commands

```bash
# Check model files exist and age
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker exec claude-ml-bot bash -c 'ls -lh models/*.joblib'"

# Check continuous learning status
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose logs | grep -i 'retrain\|learn\|model.*load'"

# Test model predictions
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c \"from claude_ml.models import EarlySignalModel; m = EarlySignalModel.load('models/early_signal_btc.joblib'); print('Model loaded OK')\""

# Check model decision quality
ssh root@95.81.101.148 "docker exec claude-ml-bot python scripts/diagnose_model_quality.py"
```

## What to check

1. **Model Age**: Models older than 2-3 days may need retraining
2. **File Size**: Should be ~100-500KB each (not empty)
3. **Loading**: No errors when importing models
4. **Performance**: Win rate should be 50-60% for good models

## Expected output

```
-rw-r--r-- 1 root root 245K Jul 29 14:30 models/early_signal_btc.joblib
-rw-r--r-- 1 root root 312K Jul 29 14:30 models/confirmation_btc.joblib
-rw-r--r-- 1 root root 198K Jul 29 14:30 models/momentum_btc.joblib
```

## Retraining triggers

- Automatic: Every 48 hours OR when performance drops
- Manual: If win rate < 45% or too many false signals
- After major market regime changes

## Notes

- Models are stored in `models/` directory (persisted volume)
- Continuous learning engine handles auto-retraining
- Don't retrain manually unless debugging - let the system handle it
