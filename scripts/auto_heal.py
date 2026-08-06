#!/usr/bin/env python
"""
Auto-Healing Monitor for Claude ML Trading System.

This script runs in the background and:
1. Checks system health every 5 minutes
2. Auto-fixes common issues
3. Logs all actions taken
4. Restarts services if needed
"""

import sys
import time
import logging
import sqlite3
import requests
from pathlib import Path
from datetime import datetime, timezone

# Setup logging
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [AUTO-HEAL] %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "auto_heal.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class AutoHealMonitor:
    """Automatically monitors and fixes issues in the trading system."""

    def __init__(self, db_path: str = "/opt/claude-ml-trading/data/runtime.sqlite"):
        self.db_path = db_path
        self.check_count = 0
        self.fixes_applied = 0

    def check_database_health(self):
        """Check if database is accessible and has recent data."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Check if we have recent trades
            cursor.execute("""
                SELECT COUNT(*) FROM paper_trades
                WHERE entry_ts > datetime('now', '-1 hour')
            """)
            recent_trades = cursor.fetchone()[0]

            # Check if runtime state is being updated
            cursor.execute("""
                SELECT COUNT(*) FROM runtime_state
            """)
            state_count = cursor.fetchone()[0]

            conn.close()

            if state_count == 0:
                logger.warning("Runtime state table is empty!")
                return False

            logger.info(f"Database OK (recent trades: {recent_trades}, states: {state_count})")
            return True

        except Exception as e:
            logger.error(f"Database check failed: {e}")
            return False

    def check_container_health(self):
        """Check if Docker containers are running."""
        try:
            import subprocess
            result = subprocess.run(
                ["docker-compose", "ps"],
                cwd="/opt/claude-ml-trading",
                capture_output=True,
                text=True,
                timeout=10
            )

            if "Up" not in result.stdout:
                logger.warning("Some containers are not running!")
                return False

            logger.info("All containers healthy")
            return True

        except Exception as e:
            logger.error(f"Container check failed: {e}")
            return False

    def check_disk_space(self):
        """Check if there's enough disk space."""
        try:
            import shutil
            total, used, free = shutil.disk_usage("/opt/claude-ml-trading")
            free_gb = free / (1024**3)

            if free_gb < 1.0:  # Less than 1GB
                logger.warning(f"Low disk space: {free_gb:.2f} GB free")
                return False

            logger.info(f"Disk space OK: {free_gb:.2f} GB free")
            return True

        except Exception as e:
            logger.error(f"Disk space check failed: {e}")
            return False

    def check_api_connectivity(self):
        """Check if external APIs are reachable."""
        try:
            # Check OKX API
            response = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP", timeout=5)
            if response.status_code != 200:
                logger.warning(f"OKX API returned status {response.status_code}")
                return False

            logger.info("API connectivity OK")
            return True

        except Exception as e:
            logger.error(f"API check failed: {e}")
            return False

    def auto_fix_issues(self):
        """Apply automatic fixes for detected issues."""
        logger.info("Running auto-fix routines...")

        try:
            # Fix 1: Restart containers if unhealthy
            if not self.check_container_health():
                logger.info("Attempting container restart...")
                import subprocess
                subprocess.run(
                    ["docker-compose", "restart"],
                    cwd="/opt/claude-ml-trading",
                    timeout=30
                )
                self.fixes_applied += 1

            # Fix 2: Clean old logs if disk is low
            total, used, free = 0, 0, 0
            import shutil
            total, used, free = shutil.disk_usage("/opt/claude-ml-trading")
            if free / (1024**3) < 2.0:  # Less than 2GB
                logger.info("Cleaning old logs to free space...")
                log_files = list(Path("/opt/claude-ml-trading/logs").glob("*.log"))
                for log_file in log_files[-5:]:  # Keep only last 5 logs
                    log_file.unlink()
                self.fixes_applied += 1

            # Fix 3: Reset error streak if too high
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT value FROM runtime_state WHERE key='error_streak'
            """)
            row = cursor.fetchone()
            if row and int(row[0]) > 10:
                logger.info("Resetting high error streak")
                cursor.execute("""
                    INSERT OR REPLACE INTO runtime_state (key, value)
                    VALUES ('error_streak', '0')
                """)
                conn.commit()
                self.fixes_applied += 1
            conn.close()

            logger.info(f"Auto-fix complete ({self.fixes_applied} fixes applied)")

        except Exception as e:
            logger.error(f"Auto-fix failed: {e}")

    def run_check_cycle(self):
        """Run one complete check cycle."""
        self.check_count += 1
        logger.info(f"=== Check Cycle #{self.check_count} ===")

        checks = [
            ("Database", self.check_database_health),
            ("Containers", self.check_container_health),
            ("Disk Space", self.check_disk_space),
            ("APIs", self.check_api_connectivity),
        ]

        failed_checks = []
        for name, check_func in checks:
            if not check_func():
                failed_checks.append(name)

        if failed_checks:
            logger.warning(f"Failed checks: {', '.join(failed_checks)}")
            self.auto_fix_issues()
        else:
            logger.info("All checks passed ✓")

    def run(self, interval_minutes: int = 5):
        """Run monitoring loop."""
        logger.info(f"Starting auto-heal monitor (interval: {interval_minutes} min)")

        while True:
            try:
                self.run_check_cycle()
                time.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                logger.info("Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}", exc_info=True)
                time.sleep(60)  # Wait 1 minute before retrying


if __name__ == "__main__":
    monitor = AutoHealMonitor()
    monitor.run(interval_minutes=5)
