"""
Dedicated live session tracker for user satyadeep (id=3).
Monitors trades, signals, P&L, portfolio every 10 seconds for 30+ minutes.
Outputs to monitor/satyadeep_session.json and monitor/satyadeep_session.md
"""
import sqlite3
import json
import time
import os
import sys
import traceback
from datetime import datetime
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent.parent
DB = BASE / "trading.db"
OUT_JSON = BASE / "monitor" / "satyadeep_session.json"
OUT_MD = BASE / "monitor" / "satyadeep_session.md"
USER_ID = 3
INTERVAL = 10
DURATION = 3600

records = []
start_time = time.time()

def get_trades(c):
    c.execute("SELECT * FROM trades WHERE user_id=? ORDER BY id DESC", (USER_ID,))
    return [dict(r) for r in c.fetchall()]

def get_active(c):
    c.execute("SELECT * FROM active_trades WHERE user_id=? ORDER BY entry_time", (USER_ID,))
    return [dict(r) for r in c.fetchall()]

def get_signals(c):
    c.execute("SELECT * FROM signals WHERE user_id=? ORDER BY id DESC LIMIT 20", (USER_ID,))
    return [dict(r) for r in c.fetchall()]

def get_user(c):
    c.execute("SELECT id, username, balance, is_premium FROM users WHERE id=?", (USER_ID,))
    return dict(c.fetchone())

def get_portfolio(c):
    c.execute("SELECT * FROM portfolio_history WHERE user_id=? ORDER BY id DESC LIMIT 1", (USER_ID,))
    r = c.fetchone()
    return dict(r) if r else {}

def main():
    print(f"[{datetime.now().isoformat()}] Starting satyadeep tracker")
    print(f"[{datetime.now().isoformat()}] DB: {DB}")
    print(f"[{datetime.now().isoformat()}] Interval: {INTERVAL}s, Duration: {DURATION}s")
    
    last_trade_count = 0
    trade_open_times = defaultdict(list)
    
    while time.time() - start_time < DURATION:
        try:
            if not DB.exists():
                time.sleep(INTERVAL)
                continue
            conn = sqlite3.connect(str(DB))
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "elapsed_seconds": round(time.time() - start_time, 1),
                "user": get_user(c),
                "portfolio": get_portfolio(c),
                "trades": get_trades(c),
                "active_trades": get_active(c),
                "signals": get_signals(c),
                "trade_count": len(get_trades(c)),
                "active_count": len(get_active(c)),
            }
            
            today_trades = [t for t in snapshot["trades"] if t.get("entry_time","").startswith("2026-06-04")]
            closed_today = [t for t in today_trades if t.get("status") == "CLOSED"]
            total_pnl = sum(t.get("profit_loss") or 0 for t in closed_today)
            
            snapshot["today_closed_trades"] = len(closed_today)
            snapshot["today_total_pnl"] = round(total_pnl, 2)
            snapshot["today_profit"] = round(sum(t.get("profit_loss") or 0 for t in closed_today if (t.get("profit_loss") or 0) > 0), 2)
            snapshot["today_loss"] = round(sum(t.get("profit_loss") or 0 for t in closed_today if (t.get("profit_loss") or 0) < 0), 2)
            
            active_symbols = [a["symbol"] for a in snapshot["active_trades"]]
            snapshot["active_symbols"] = active_symbols
            
            if snapshot["trade_count"] > last_trade_count:
                new_trades = [t for t in today_trades if t["id"] not in trade_open_times]
                for t in new_trades:
                    trade_open_times[t["id"]] = t.get("entry_time", "")
                    if t.get("status") == "OPEN":
                        print(f"\n[{snapshot['timestamp']}] NEW OPEN TRADE: {t['symbol']} {t['direction']} @ {t['entry_price']}")
                    elif t.get("status") == "CLOSED":
                        print(f"\n[{snapshot['timestamp']}] TRADE CLOSED: {t['symbol']} {t['direction']} P&L={t.get('profit_loss',0):.2f}")
                last_trade_count = snapshot["trade_count"]
            
            if snapshot["active_count"] > 0:
                print(f"[{snapshot['timestamp']}] Active: {snapshot['active_symbols']} | Today P&L: {snapshot['today_total_pnl']:+.2f} | Portfolio: {snapshot['portfolio'].get('portfolio_value', '?'):.2f}")
            else:
                print(f"[{snapshot['timestamp']}] No active trades | Today P&L: {snapshot['today_total_pnl']:+.2f} | Portfolio: {snapshot['portfolio'].get('portfolio_value', '?'):.2f}")
            
            records.append(snapshot)
            
            with open(OUT_JSON, "w", encoding="utf-8") as f:
                json.dump({"session_start": start_time, "records": records}, f, indent=2, default=str, ensure_ascii=False)
            
            with open(OUT_MD, "w", encoding="utf-8") as f:
                f.write(f"# Satyadeep Live Trading Session\n")
                f.write(f"**Started:** {datetime.fromtimestamp(start_time).isoformat()}\n")
                f.write(f"**Last Updated:** {snapshot['timestamp']}\n")
                f.write(f"**Elapsed:** {snapshot['elapsed_seconds']:.0f}s / {DURATION}s\n\n")
                f.write(f"## Summary\n\n")
                f.write(f"| Metric | Value |\n")
                f.write(f"|--------|-------|\n")
                f.write(f"| Balance | {snapshot['user'].get('balance', '?'):,.2f} |\n")
                f.write(f"| Portfolio Value | {snapshot['portfolio'].get('portfolio_value', '?'):,.2f} |\n")
                f.write(f"| Today Closed Trades | {snapshot['today_closed_trades']} |\n")
                f.write(f"| Today Total P&L | {snapshot['today_total_pnl']:+.2f} |\n")
                f.write(f"| Today Profit | {snapshot['today_profit']:+.2f} |\n")
                f.write(f"| Today Loss | {snapshot['today_loss']:+.2f} |\n")
                f.write(f"| Active Trades | {snapshot['active_count']} |\n")
                f.write(f"| Active Symbols | {', '.join(active_symbols) if active_symbols else 'None'} |\n\n")
                
                if snapshot["active_trades"]:
                    f.write(f"## Active Positions\n\n")
                    f.write(f"| Symbol | Type | Entry Price | Qty | Stop Loss | Target |\n")
                    f.write(f"|--------|------|-------------|-----|-----------|--------|\n")
                    for a in snapshot["active_trades"]:
                        f.write(f"| {a.get('symbol','?')} | {a.get('direction','?')} | {a.get('entry_price','?'):.2f} | {a.get('quantity','?')} | {a.get('stop_loss','None')} | {a.get('target_price','None')} |\n")
                    f.write(f"\n")
                
                if closed_today:
                    f.write(f"## Today's Closed Trades\n\n")
                    f.write(f"| Time | Symbol | Dir | Entry | Exit | P&L |\n")
                    f.write(f"|------|--------|-----|-------|------|------|\n")
                    for t in sorted(closed_today, key=lambda x: x.get("entry_time","")):
                        f.write(f"| {t.get('entry_time','?')} | {t.get('symbol','?')} | {t.get('direction','?')} | {t.get('entry_price','?'):.2f} | {t.get('exit_price','?'):.2f} | {t.get('profit_loss',0):+.2f} |\n")
                    f.write(f"\n")
                
                if snapshot["signals"]:
                    f.write(f"## Recent Signals\n\n")
                    f.write(f"| Time | Symbol | Direction | Confidence |\n")
                    f.write(f"|------|--------|-----------|------------|\n")
                    for s in snapshot["signals"][:10]:
                        f.write(f"| {s.get('time','?')} | {s.get('pair','?')} | {s.get('direction','?')} | {s.get('confidence','?'):.4f} |\n")
            
            conn.close()
            
        except Exception as e:
            print(f"[ERROR] {e}")
            traceback.print_exc()
        
        time.sleep(INTERVAL)
    
    elapsed = time.time() - start_time
    total_trades_today = [r for r in records if r["today_closed_trades"] > 0]
    final_pnl = records[-1]["today_total_pnl"] if records else 0
    
    print(f"\n{'='*60}")
    print(f"SESSION COMPLETE - Elapsed: {elapsed:.0f}s")
    print(f"Records captured: {len(records)}")
    print(f"Final Today P&L: {final_pnl:+.2f}")
    print(f"Data saved to: {OUT_JSON}")
    print(f"Summary saved to: {OUT_MD}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
