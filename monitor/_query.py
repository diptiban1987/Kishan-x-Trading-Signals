"""Quick DB query helper"""
import sqlite3, sys, json

DB = 'E:\\Indian_Trading Platform_Files\\WORKABLE\\Kishan-x-Trading-Signals-main\\trading.db'

def query(sql, params=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

if __name__ == '__main__':
    if len(sys.argv) > 1:
        sql = ' '.join(sys.argv[1:])
    else:
        sql = 'SELECT * FROM trades ORDER BY id DESC LIMIT 5'
    result = query(sql)
    print(json.dumps(result, indent=2, default=str))
