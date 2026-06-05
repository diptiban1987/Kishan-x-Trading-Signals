import sqlite3, json

conn = sqlite3.connect('E:\\Indian_Trading Platform_Files\\WORKABLE\\Kishan-x-Trading-Signals-main\\trading.db')
conn.row_factory = sqlite3.Row

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
for t in tables:
    name = t['name']
    cols = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
    col_names = [c['name'] for c in cols]
    cnt = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    print(f'{name} ({cnt} rows): {col_names}')
    if cnt > 0 and name in ('trades', 'signals', 'orders', 'users', 'active_trades', 'portfolio_history'):
        sample = conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid DESC LIMIT 5').fetchall()
        for s in sample:
            print(f'  -> {dict(s)}')
    print()

conn.close()
