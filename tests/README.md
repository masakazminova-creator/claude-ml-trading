# Claude ML Trading System - Tests

## 🧪 Running Tests

### Run All Tests
```bash
cd C:\Bot\claude_ml_system
.venv\Scripts\activate
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_risk_manager.py -v
```

### Run with Coverage
```bash
pytest tests/ --cov=src/claude_ml --cov-report=html
```

---

## 📋 Test Files

| File | Tests | Purpose |
|------|-------|---------|
| `test_risk_manager.py` | Position sizing, drawdown tracking | Risk management logic |
| `test_trailing_stop.py` | ATR trailing stop creation/updates | Trailing stop system |
| `test_feature_engineering.py` | Feature calculation correctness | Feature engineering |

---

## ✅ Current Coverage

- **Risk Manager**: 8 tests
- **Trailing Stop**: 10 tests
- **Feature Engineering**: 7 tests

**Total:** 25 tests

---

## 🔜 Next Steps

1. Add more test files for other modules:
   - `test_ensemble.py`
   - `test_adaptive_thresholds.py`
   - `test_continuous_learning.py`

2. Add integration tests:
   - Full pipeline test (fetch → features → decision)
   - Database operations test

3. Setup CI/CD:
   - GitHub Actions to run tests on push
   - Coverage reports

---

**Test Status:** ✅ Basic tests implemented
**Last Updated:** 2026-07-28
