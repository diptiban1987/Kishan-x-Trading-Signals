#!/usr/bin/env python3
"""
Price Validator — fetches live prices from Yahoo Finance and compares
with the active trades in the system to verify Angel One WebSocket accuracy.

Usage:
    python check_prices.py
    python check_prices.py --symbol HDFCBANK  (check a single symbol)
"""

import sys
import json
import time
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / "trading.db"

# All tradeable symbols with their Yahoo Finance tickers
SYMBOL_MAP = {
    'RELIANCE': 'RELIANCE.NS',
    'TCS': 'TCS.NS',
    'HDFCBANK': 'HDFCBANK.NS',
    'INFY': 'INFY.NS',
    'ICICIBANK': 'ICICIBANK.NS',
    'HINDUNILVR': 'HINDUNILVR.NS',
    'SBIN': 'SBIN.NS',
    'BHARTIARTL': 'BHARTIARTL.NS',
    'KOTAKBANK': 'KOTAKBANK.NS',
    'BAJFINANCE': 'BAJFINANCE.NS',
    'NIFTY50': '^NSEI',
    'BANKNIFTY': '^NSEBANK',
    'SENSEX': '^BSESN',
}


def get_active_trades_from_db():
    """Read active trades from trading.db"""
    if not DB_PATH.exists():
        print(f"  DB not found at {DB_PATH}")
        return []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT id, symbol, type, entry_price, quantity, entry_time, user_id, stop_loss, target_price FROM active_trades")
        rows = cur.fetchall()
        conn.close()
        trades = []
        for row in rows:
            trades.append({
                'id': row[0],
                'symbol': row[1],
                'type': row[2],
                'entry_price': float(row[3]),
                'quantity': int(row[4]),
                'entry_time': row[5],
                'user_id': row[6],
                'stop_loss': float(row[7]) if row[7] else 0,
                'target_price': float(row[8]) if row[8] else 0,
            })
        return trades
    except Exception as e:
        print(f"  Error reading DB: {e}")
        return []


def fetch_yahoo_price(symbol):
    """Fetch latest price from Yahoo Finance"""
    yf_ticker = SYMBOL_MAP.get(symbol)
    if not yf_ticker:
        return None, "no mapping"
    try:
        import yfinance as yf
        stock = yf.Ticker(yf_ticker)
        data = stock.history(period="1d", interval="1m")
        if data is not None and not data.empty:
            latest = float(data['Close'].iloc[-1])
            ts = str(data.index[-1])
            return latest, ts
        # fallback to 5d daily
        data = stock.history(period="5d", interval="1d")
        if data is not None and not data.empty:
            latest = float(data['Close'].iloc[-1])
            ts = str(data.index[-1])
            return latest, ts
        return None, "no data"
    except ImportError:
        return None, "yfinance not installed"
    except Exception as e:
        return None, str(e)


def fetch_google_price(symbol):
    """Fallback: fetch price via Google Finance if yfinance fails"""
    yf_ticker = SYMBOL_MAP.get(symbol, symbol)
    try:
        import requests
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_ticker}?interval=1m&range=1d"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            meta = data.get('chart', {}).get('result', [{}])[0].get('meta', {})
            price = meta.get('regularMarketPrice')
            if price:
                return float(price), "yahoo-api"
            quotes = data.get('chart', {}).get('result', [{}])[0].get('indicators', {}).get('quote', [{}])[0]
            closes = quotes.get('close', [])
            if closes:
                for c in reversed(closes):
                    if c is not None:
                        return float(c), "yahoo-api"
        return None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, str(e)


def main():
    parser = argparse.ArgumentParser(description="Validate trade prices against Yahoo Finance")
    parser.add_argument("--symbol", "-s", help="Check only this symbol")
    args = parser.parse_args()

    print("=" * 70)
    print(f"  PRICE VALIDATOR — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Compares active trade prices with Yahoo Finance live data")
    print("=" * 70)

    # 1. Get active trades from DB
    trades = get_active_trades_from_db()
    if not trades:
        print("\n  No active trades found in DB.")
        # If no trades, still check all symbols
        print("  Checking all tradeable symbols...\n")
        trades = [{'symbol': s, 'type': '---', 'entry_price': 0, 'quantity': 0,
                   'entry_time': '', 'user_id': 0, 'id': ''}
                  for s in SYMBOL_MAP]

    if args.symbol:
        symbol_upper = args.symbol.upper()
        trades = [t for t in trades if t['symbol'] == symbol_upper]
        if not trades:
            # If symbol not in active trades, create a check entry
            trades = [{'symbol': symbol_upper, 'type': '---', 'entry_price': 0, 'quantity': 0,
                       'entry_time': '', 'user_id': 0, 'id': ''}]

    # 2. Deduplicate symbols
    seen = set()
    unique_trades = []
    for t in trades:
        if t['symbol'] not in seen:
            seen.add(t['symbol'])
            unique_trades.append(t)
    trades = unique_trades

    # 3. Fetch prices and compare
    print(f"\n  {'Symbol':<14} {'Trade':>5} {'Entry':>10} {'Live Price':>12} {'Diff':>10} {'Diff%':>8}  {'Source'}")
    print(f"  {'-'*14} {'-'*5} {'-'*10} {'-'*12} {'-'*10} {'-'*8}  {'-'*12}")

    total_diff_pct = 0
    count = 0

    for i, trade in enumerate(trades):
        symbol = trade['symbol']

        # Fetch from Yahoo Finance (primary)
        live_price, source = fetch_yahoo_price(symbol)
        if live_price is None:
            # Try Google Finance fallback
            live_price, source = fetch_google_price(symbol)

        trade_type = trade.get('type', '---')
        entry_price = trade.get('entry_price', 0)

        if live_price is not None:
            diff = live_price - entry_price
            diff_pct = (diff / entry_price * 100) if entry_price > 0 else 0
            total_diff_pct += abs(diff_pct)
            count += 1

            entry_str = f"{entry_price:.2f}" if entry_price > 0 else "N/A"
            live_str = f"{live_price:.2f}"
            diff_str = f"{diff:+.2f}" if entry_price > 0 else "N/A"
            pct_str = f"{diff_pct:+.2f}%" if entry_price > 0 else "N/A"

            status = "[OK]" if abs(diff_pct) < 5 else "[WARN]" if abs(diff_pct) < 20 else "[ERR]"

            print(f"  {status} {symbol:<12} {trade_type:>5} {entry_str:>10} {live_str:>12} {diff_str:>10} {pct_str:>8}  {source}")
        else:
            print(f"  [?] {symbol:<12} {trade_type:>5} {'---':>10} {'NO DATA':>12} {'':>10} {'':>8}  {source}")

        # Small delay to avoid rate limiting
        if i < len(trades) - 1:
            time.sleep(0.5)

    # Summary
    print(f"\n  {'=' * 70}")
    if count > 0:
        avg_deviation = total_diff_pct / count
        print(f"  Average price deviation from entry: {avg_deviation:.2f}%")
        if avg_deviation < 2:
            print(f"  [OK] Prices are consistent with Yahoo Finance")
        elif avg_deviation < 5:
            print(f"  [WARN] Minor deviations — within normal market movement")
        else:
            print(f"  [ERR] Large deviations detected — investigate data feed")
    print(f"  Total symbols checked: {count}")
    print(f"\n  Note: Entry prices are from trade open time. Differences may reflect\n"
          f"        normal market movement since entry, not data feed errors.")
    print("=" * 70)


if __name__ == '__main__':
    main()
