import sqlite3, json

conn = sqlite3.connect('E:\\Indian_Trading Platform_Files\\WORKABLE\\Kishan-x-Trading-Signals-main\\trading.db')
conn.row_factory = sqlite3.Row

print('=== ACTIVE TRADES ===')
for r in conn.execute('SELECT * FROM active_trades WHERE user_id=3').fetchall():
    print(dict(r))

print()
print('=== TODAY TRADES (all) ===')
for r in conn.execute("SELECT * FROM trades WHERE user_id=3 AND entry_time LIKE '2026-06-04%' ORDER BY id").fetchall():
    print(dict(r))

print()
print('=== PORTFOLIO HISTORY ===')
for r in conn.execute('SELECT * FROM portfolio_history WHERE user_id=3 ORDER BY id DESC LIMIT 5').fetchall():
    print(dict(r))

print()
print('=== USER ===')
u = dict(conn.execute('SELECT id, username, balance, is_premium FROM users WHERE id=3').fetchone())
print(u)

# P&L Analysis for today
print()
print('=== TODAY P&L ANALYSIS ===')
rows = conn.execute("SELECT profit_loss FROM trades WHERE user_id=3 AND status='CLOSED' AND entry_time LIKE '2026-06-04%'").fetchall()
pnls = [r['profit_loss'] for r in rows if r['profit_loss']]
print(f'Trades: {len(pnls)}')
print(f'Total P&L: {sum(pnls):.2f}')
print(f'Profitable: {len([p for p in pnls if p > 0])}')
print(f'Loss: {len([p for p in pnls if p < 0])}')
print(f'Win Rate: {len([p for p in pnls if p > 0])/len(pnls)*100:.1f}%' if pnls else 'N/A')
print(f'Avg Win: {sum([p for p in pnls if p > 0])/len([p for p in pnls if p > 0]):.2f}' if any(p > 0 for p in pnls) else 'N/A')
print(f'Avg Loss: {sum([p for p in pnls if p < 0])/len([p for p in pnls if p < 0]):.2f}' if any(p < 0 for p in pnls) else 'N/A')

# Check ALL P&L for this user (all time)
print()
print('=== ALL-TIME P&L ===')
rows_all = conn.execute("SELECT profit_loss FROM trades WHERE user_id=3 AND status='CLOSED'").fetchall()
pnls_all = [r['profit_loss'] for r in rows_all if r['profit_loss']]
print(f'Trades: {len(pnls_all)}')
print(f'Total P&L: {sum(pnls_all):.2f}')
prof = [p for p in pnls_all if p > 0]
los = [p for p in pnls_all if p < 0]
print(f'Profitable: {len(prof)} / Loss: {len(los)}')
print(f'Win Rate: {len(prof)/len(pnls_all)*100:.1f}%')
print(f'Avg Win: {sum(prof)/len(prof):.2f}' if prof else 'N/A')
print(f'Avg Loss: {sum(los)/len(los):.2f}' if los else 'N/A')

conn.close()
