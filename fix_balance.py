import sqlite3

conn = sqlite3.connect('/opt/claude-ml-trading/data/runtime.sqlite')
cursor = conn.cursor()

# Set start balance
cursor.execute("INSERT OR REPLACE INTO runtime_state (key, value) VALUES (?, ?)",
               ('paper_start_balance', '10168.50'))
conn.commit()

# Calculate with compound returns
balance = 10168.50
cursor.execute("SELECT pnl_pct FROM paper_trades WHERE status='closed' AND exit_ts IS NOT NULL ORDER BY id")
for t in cursor.fetchall():
    pnl = float(t[0]) if t[0] else 0
    balance *= (1 + pnl/100)

print(f'Start Balance: $10,168.50')
print(f'Current Balance: ${balance:.2f}')
print(f'Total Return: {((balance-10168.50)/10168.50*100):+.2f}%')

conn.close()
