"""Quick trade analysis script"""
import sqlite3

conn = sqlite3.connect('trading.db')
cur = conn.cursor()

# Exclude the known anomalous BAJFINANCE trade (exit_price=64.25) and KOTAKBANK anomalies
print("=" * 70)
print("  TRADE PERFORMANCE ANALYSIS (May 27, 2026)")
print("=" * 70)

# Today's trades (excluding known anomaly id=52)
cur.execute("""
    SELECT count(*) as total,
           sum(case when profit_loss > 0 then 1 else 0 end) as wins,
           sum(case when profit_loss < 0 then 1 else 0 end) as losses,
           sum(case when profit_loss = 0 then 1 else 0 end) as flat,
           round(sum(profit_loss), 2) as total_pnl,
           round(avg(profit_loss), 2) as avg_pnl,
           round(sum(case when profit_loss > 0 then profit_loss else 0 end), 2) as gross_win,
           round(sum(case when profit_loss < 0 then profit_loss else 0 end), 2) as gross_loss
    FROM trades
    WHERE entry_time >= '2026-05-27' AND id != 52
""")
row = cur.fetchone()
total, wins, losses, flat, total_pnl, avg_pnl, gross_win, gross_loss = row
win_rate = (wins / total * 100) if total > 0 else 0

print(f"\n📊 Today's Stats (excl. anomaly):")
print(f"   Total Trades:    {total}")
print(f"   Wins:            {wins}  ({win_rate:.1f}%)")
print(f"   Losses:          {losses}")
print(f"   Flat:            {flat}")
print(f"   Total P&L:       ₹{total_pnl}")
print(f"   Avg P&L/Trade:   ₹{avg_pnl}")
print(f"   Gross Win:       ₹{gross_win}")
print(f"   Gross Loss:      ₹{gross_loss}")
if gross_loss != 0:
    print(f"   Profit Factor:   {abs(gross_win / gross_loss):.2f}")

# Per-symbol breakdown
print(f"\n📈 Per-Symbol Breakdown (today, excl. anomaly):")
cur.execute("""
    SELECT symbol,
           count(*) as trades,
           sum(case when profit_loss > 0 then 1 else 0 end) as wins,
           round(sum(profit_loss), 2) as pnl,
           round(avg(profit_loss), 2) as avg_pnl,
           round(avg(cast((julianday(exit_time) - julianday(entry_time)) * 86400 as integer)), 0) as avg_hold_sec
    FROM trades
    WHERE entry_time >= '2026-05-27' AND id != 52
    GROUP BY symbol
    ORDER BY pnl DESC
""")
print(f"   {'Symbol':<15} {'Trades':>6} {'Wins':>5} {'P&L':>10} {'Avg P&L':>10} {'Avg Hold':>10}")
print(f"   {'-'*15} {'-'*6} {'-'*5} {'-'*10} {'-'*10} {'-'*10}")
for r in cur.fetchall():
    hold_str = f"{int(r[5])}s" if r[5] else "N/A"
    print(f"   {r[0]:<15} {r[1]:>6} {r[2]:>5} {r[3]:>10} {r[4]:>10} {hold_str:>10}")

# Holding time analysis
print(f"\n⏱️ Holding Time Analysis (today, excl. anomaly):")
cur.execute("""
    SELECT
        sum(case when hold_sec < 10 then 1 else 0 end) as under_10s,
        sum(case when hold_sec >= 10 and hold_sec < 120 then 1 else 0 end) as s10_to_2m,
        sum(case when hold_sec >= 120 and hold_sec < 600 then 1 else 0 end) as m2_to_10m,
        sum(case when hold_sec >= 600 then 1 else 0 end) as over_10m
    FROM (
        SELECT cast((julianday(exit_time) - julianday(entry_time)) * 86400 as integer) as hold_sec
        FROM trades WHERE entry_time >= '2026-05-27' AND id != 52
    )
""")
r = cur.fetchone()
print(f"   Under 10s:       {r[0]} trades (SCALP / FLASH EXIT)")
print(f"   10s - 2min:      {r[1]} trades")
print(f"   2min - 10min:    {r[2]} trades")
print(f"   Over 10min:      {r[3]} trades")

# Direction analysis
print(f"\n🔄 Direction Analysis (today, excl. anomaly):")
cur.execute("""
    SELECT direction,
           count(*) as trades,
           sum(case when profit_loss > 0 then 1 else 0 end) as wins,
           round(sum(profit_loss), 2) as pnl
    FROM trades
    WHERE entry_time >= '2026-05-27' AND id != 52
    GROUP BY direction
""")
for r in cur.fetchall():
    wr = r[2] / r[1] * 100 if r[1] > 0 else 0
    print(f"   {r[0]:<6} — {r[1]} trades, {r[2]} wins ({wr:.0f}%), P&L: ₹{r[3]}")

# SENSEX analysis (index trades)
print(f"\n🏛️ Index Trades (SENSEX, BANKNIFTY etc):")
cur.execute("""
    SELECT symbol, direction, entry_price, exit_price, profit_loss,
           cast((julianday(exit_time) - julianday(entry_time)) * 86400 as integer) as hold_sec
    FROM trades
    WHERE entry_time >= '2026-05-27' AND symbol IN ('SENSEX','BANKNIFTY','NIFTY50','NIFTY')
    ORDER BY entry_time
""")
for r in cur.fetchall():
    print(f"   {r[0]} {r[1]} @ {r[2]:.2f} -> {r[3]:.2f} = ₹{r[4]:.2f} (held {r[5]}s)")

conn.close()
