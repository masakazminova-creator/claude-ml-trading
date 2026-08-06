#!/bin/bash
# Auto-heal monitor startup script

cd /opt/claude-ml-trading
python scripts/auto_heal.py >> logs/auto_heal.log 2>&1 &

echo $! > /var/run/claude-ml-autoheal.pid
echo "Auto-heal monitor started (PID: $!)"
