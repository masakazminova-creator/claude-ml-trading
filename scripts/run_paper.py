#!/usr/bin/env python
"""
Paper trading entry point for Claude ML Trading System.

Runs the runtime engine in paper mode with continuous learning
and performance monitoring.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_ml.config import Settings
from claude_ml.runtime import RuntimeEngine


def main():
    """Initialize and run paper trading."""
    print("=" * 80)
    print("Claude ML Trading System - Paper Trading")
    print("=" * 80)

    settings = Settings()

    # Force paper mode
    if settings.mode != "paper":
        print(f"WARNING: Forcing MODE=paper (was {settings.mode})")
        settings.mode = "paper"

    try:
        engine = RuntimeEngine(settings)
        engine.run()
    except KeyboardInterrupt:
        print("\nPaper trading stopped by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
