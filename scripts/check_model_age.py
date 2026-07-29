#!/usr/bin/env python
"""Check when models were last trained."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

import joblib
from datetime import datetime, timezone

model_dir = Path(__file__).parent.parent / "models"

print("=" * 80)
print("MODEL AGE CHECK")
print("=" * 80)

for model_file in ["early_signal.joblib", "confirmation.joblib", "momentum.joblib"]:
    path = model_dir / model_file

    if not path.exists():
        print(f"\n{model_file}: NOT FOUND (only on server)")
        continue

    # Get file modification time
    mtime = path.stat().st_mtime
    mod_time = datetime.fromtimestamp(mtime, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)

    age_hours = (now - mod_time).total_seconds() / 3600
    age_days = age_hours / 24

    print(f"\n{model_file}:")
    print(f"  Last modified: {mod_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Age: {age_hours:.1f} hours ({age_days:.1f} days)")

    if age_days > 2:
        print(f"  ⚠️  WARNING: Model is {age_days:.1f} days old - may be stale!")
    elif age_days > 1:
        print(f"  ⚡ Model is reasonably fresh")
    else:
        print(f"  ✓ Model is very fresh")

print("\n" + "=" * 80)
