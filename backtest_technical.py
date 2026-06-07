#!/usr/bin/env python3
"""
Technical-Only Backtest — No AI Predictor
==========================================
Uses the same technical strategies as the live system:
  - NIFTY Momentum (for NIFTY50, indices)
  - BANKNIFTY Volatility (for BANKNIFTY)
  - Large Cap (for RELIANCE, TCS, HDFCBANK, INFY)
  - Breakout/Breakdown (for all other stocks)

This answers: "Do the technical strategies have edge WITHOUT AI?"

Usage:
  python backtest_technical.py
  python backtest_technical.py --symbols RELIANCE BANKNIFTY NIFTY50
"""

import os, sys, argparse, logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# ─── Data Classes ─────────────────────────────────────────────

@dataclass
class Trade:
    symbol: str
    direction: str
    strategy: str
    entry_price: float
    entry_date: datetime
    exit_price: float = 0.0
    exit_date: Optional[datetime] = None
    stop_loss: float = 0.0
    target: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ''
    confidence: float = 0.0

@dataclass
class Result:
    symbol: str
    trades: List[Trade] = field(default_factory=list)
    total_pnl_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_winner_pct: float = 0.0
    avg_loser_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0


# ─── Technical Indicator Calculator ──────────────────────────

def calc_indicators(df: pd.DataFrame) -> Dict:
    """Calculate all technical indicators — mirrors indian_trading_system._calculate_indian_indicators"""
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # RSI-14 (Wilder's EMA)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()

    # Bollinger Bands (2.2 std for Indian markets)
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = sma20 + std20 * 2.2
    bb_lower = sma20 - std20 * 2.2

    # SMAs
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    # Volume ratio
    vol_sma = volume.rolling(20).mean()
    vol_ratio = volume / (vol_sma + 1e-10)

    # ATR-14
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # Support & Resistance (last 60 candles)
    recent = close.iloc[-60:] if len(close) >= 60 else close
    supports, resistances = [], []
    for i in range(10, len(recent) - 1):
        if recent.iloc[i] <= recent.iloc[i-10:i+1].min():
            supports.append(float(recent.iloc[i]))
        if recent.iloc[i] >= recent.iloc[i-10:i+1].max():
            resistances.append(float(recent.iloc[i]))
    supports = sorted(set(supports))[-3:] if supports else []
    resistances = sorted(set(resistances))[-3:] if resistances else []

    return {
        'rsi': float(rsi.iloc[-1]) if not rsi.empty else 50,
        'macd': float(macd.iloc[-1]) if not macd.empty else 0,
        'macd_signal': float(macd_signal.iloc[-1]) if not macd_signal.empty else 0,
        'bb_upper': float(bb_upper.iloc[-1]) if not bb_upper.empty else float(close.iloc[-1]),
        'bb_lower': float(bb_lower.iloc[-1]) if not bb_lower.empty else float(close.iloc[-1]),
        'sma50': float(sma50.iloc[-1]) if not sma50.empty and not np.isnan(sma50.iloc[-1]) else float(close.iloc[-1]),
        'sma200': float(sma200.iloc[-1]) if not sma200.empty and not np.isnan(sma200.iloc[-1]) else float(close.iloc[-1]),
        'sma_50': float(sma50.iloc[-1]) if not sma50.empty and not np.isnan(sma50.iloc[-1]) else float(close.iloc[-1]),
        'sma_200': float(sma200.iloc[-1]) if not sma200.empty and not np.isnan(sma200.iloc[-1]) else float(close.iloc[-1]),
        'volume_ratio': float(vol_ratio.iloc[-1]) if not vol_ratio.empty else 1.0,
        'atr': float(atr.iloc[-1]) if not atr.empty and not np.isnan(atr.iloc[-1]) else float(close.iloc[-1]) * 0.02,
        'support_levels': supports,
        'resistance_levels': resistances,
    }


# ─── Strategy Implementations ───────────────────────────────

def nifty_momentum(price, ind) -> Dict:
    """Multi-confirmation momentum for NIFTY/index symbols"""
    rsi = ind['rsi']
    macd_hist = ind['macd'] - ind['macd_signal']
    sma50 = ind['sma50']
    sma200 = ind['sma200']
    vr = ind['volume_ratio']

    buy_score = sum([price > sma50, 40 < rsi < 75, macd_hist > 0, price > sma200, vr > 0.8])
    sell_score = sum([price < sma50, 25 < rsi < 60, macd_hist < 0, price < sma200, vr > 0.8])

    if buy_score >= 3:
        conf = 0.6 + (buy_score / 5.0) * 0.3
        return {'type': 'BUY', 'confidence': min(conf, 0.95), 'strategy': 'NIFTY Momentum'}
    elif sell_score >= 3:
        conf = 0.6 + (sell_score / 5.0) * 0.3
        return {'type': 'SELL', 'confidence': min(conf, 0.95), 'strategy': 'NIFTY Momentum'}
    return {'type': 'HOLD', 'confidence': 0, 'strategy': 'NIFTY Momentum'}


def banknifty_volatility(price, ind) -> Dict:
    """Bollinger Band mean-reversion for BANKNIFTY"""
    bb_upper = ind['bb_upper']
    bb_lower = ind['bb_lower']
    rsi = ind['rsi']
    vr = ind['volume_ratio']

    if price <= bb_lower and rsi < 35 and vr > 1.2:
        return {'type': 'BUY', 'confidence': min((35 - rsi) / 35, 1.0), 'strategy': 'BANKNIFTY Volatility'}
    elif price >= bb_upper and rsi > 75 and vr > 1.2:
        return {'type': 'SELL', 'confidence': min((rsi - 75) / 25, 1.0), 'strategy': 'BANKNIFTY Volatility'}
    return {'type': 'HOLD', 'confidence': 0, 'strategy': 'BANKNIFTY Volatility'}


def large_cap(price, ind) -> Dict:
    """Conservative trend-following for large caps"""
    rsi = ind['rsi']
    sma50 = ind['sma_50']
    sma200 = ind['sma_200']
    macd = ind['macd']
    macd_sig = ind['macd_signal']
    vr = ind['volume_ratio']

    bullish = (45 < rsi < 65 and price > sma50 > sma200 and macd > macd_sig and vr > 1.2)
    bearish = (35 < rsi < 55 and price < sma50 and macd < macd_sig and vr > 1.2)

    if bullish:
        return {'type': 'BUY', 'confidence': 0.75, 'strategy': 'Large Cap Trend'}
    elif bearish:
        return {'type': 'SELL', 'confidence': 0.75, 'strategy': 'Large Cap Trend'}
    return {'type': 'HOLD', 'confidence': 0, 'strategy': 'Large Cap Trend'}


def breakout(price, ind) -> Dict:
    """Support/Resistance breakout for mid-cap stocks"""
    resistances = ind['resistance_levels']
    supports = ind['support_levels']
    vr = ind['volume_ratio']

    for r in resistances:
        if price > r and vr > 1.5:
            return {'type': 'BUY', 'confidence': min(0.8, 0.5 + vr * 0.1), 'strategy': 'Breakout'}
    for s in supports:
        if price < s and vr > 1.5:
            return {'type': 'SELL', 'confidence': min(0.8, 0.5 + vr * 0.1), 'strategy': 'Breakdown'}
    return {'type': 'HOLD', 'confidence': 0, 'strategy': 'Breakout'}


def get_signal(symbol: str, price: float, ind: Dict) -> Dict:
    """Route symbol to the correct strategy — mirrors _apply_indian_strategies"""
    clean = symbol.upper().replace('.NS', '').replace('.BO', '')
    if 'BANKNIFTY' in clean:
        return banknifty_volatility(price, ind)
    elif 'NIFTY' in clean or 'SENSEX' in clean:
        return nifty_momentum(price, ind)
    elif clean in ('RELIANCE', 'TCS', 'HDFCBANK', 'INFY'):
        return large_cap(price, ind)
    else:
        return breakout(price, ind)


# ─── Backtester ──────────────────────────────────────────────

class TechnicalBacktester:
    INDIAN_YF = {
        'NIFTY50': '^NSEI', 'BANKNIFTY': '^NSEBANK', 'SENSEX': '^BSESN',
        'RELIANCE': 'RELIANCE.NS', 'TCS': 'TCS.NS', 'HDFCBANK': 'HDFCBANK.NS',
        'INFY': 'INFY.NS', 'ICICIBANK': 'ICICIBANK.NS', 'SBIN': 'SBIN.NS',
        'BAJFINANCE': 'BAJFINANCE.NS', 'HINDUNILVR': 'HINDUNILVR.NS',
    }

    def __init__(self, atr_sl=1.5, atr_tp=2.5, max_hold=7, min_conf=0.60, capital=500000):
        self.atr_sl = atr_sl
        self.atr_tp = atr_tp
        self.max_hold = max_hold
        self.min_conf = min_conf
        self.capital = capital

    def _fetch(self, symbol, period='2y'):
        import yfinance as yf
        clean = symbol.upper().replace('.NS', '').replace('.BO', '')
        yf_sym = self.INDIAN_YF.get(clean, f"{clean}.NS")
        df = yf.Ticker(yf_sym).history(period=period)
        if df.empty:
            return None
        df.columns = [c.lower() for c in df.columns]
        return df

    def backtest_symbol(self, symbol: str, period='2y') -> Result:
        logger.info(f"{'='*50}")
        logger.info(f"Technical backtest: {symbol}")

        df = self._fetch(symbol, period)
        if df is None or len(df) < 220:
            logger.warning(f"Insufficient data for {symbol}")
            return Result(symbol=symbol)

        trades: List[Trade] = []
        active: Optional[Trade] = None
        lookback = 200  # Need 200 days for SMA200

        for i in range(lookback, len(df)):
            window = df.iloc[:i+1]
            row = df.iloc[i]
            price = row['close']
            high = row['high']
            low = row['low']
            date = df.index[i]

            # Check active trade
            if active is not None:
                days_held = (date - active.entry_date).days
                hit_sl = hit_tp = False

                if active.direction == 'BUY':
                    hit_sl = low <= active.stop_loss
                    hit_tp = high >= active.target
                else:
                    hit_sl = high >= active.stop_loss
                    hit_tp = low <= active.target

                if hit_sl and hit_tp:
                    active.exit_price = active.stop_loss  # Conservative
                    active.exit_reason = 'stop_loss'
                elif hit_sl:
                    active.exit_price = active.stop_loss
                    active.exit_reason = 'stop_loss'
                elif hit_tp:
                    active.exit_price = active.target
                    active.exit_reason = 'target'
                elif days_held >= self.max_hold:
                    active.exit_price = price
                    active.exit_reason = 'max_hold'

                if active.exit_reason:
                    active.exit_date = date
                    if active.direction == 'BUY':
                        active.pnl_pct = (active.exit_price - active.entry_price) / active.entry_price * 100
                    else:
                        active.pnl_pct = (active.entry_price - active.exit_price) / active.entry_price * 100
                    trades.append(active)
                    active = None
                continue

            # No active trade — generate signal
            try:
                ind = calc_indicators(window)
            except Exception:
                continue

            sig = get_signal(symbol, price, ind)
            if sig['type'] == 'HOLD' or sig['confidence'] < self.min_conf:
                continue

            atr = ind['atr']
            atr_pct = atr / price if price > 0 else 0.02

            if sig['type'] == 'BUY':
                sl = price * (1 - atr_pct * self.atr_sl)
                tp = price * (1 + atr_pct * self.atr_tp)
            else:
                sl = price * (1 + atr_pct * self.atr_sl)
                tp = price * (1 - atr_pct * self.atr_tp)

            active = Trade(
                symbol=symbol, direction=sig['type'], strategy=sig['strategy'],
                entry_price=price, entry_date=date,
                stop_loss=sl, target=tp, confidence=sig['confidence'],
            )

        # Close remaining
        if active:
            active.exit_price = df['close'].iloc[-1]
            active.exit_date = df.index[-1]
            active.exit_reason = 'end_of_period'
            if active.direction == 'BUY':
                active.pnl_pct = (active.exit_price - active.entry_price) / active.entry_price * 100
            else:
                active.pnl_pct = (active.entry_price - active.exit_price) / active.entry_price * 100
            trades.append(active)

        return self._metrics(symbol, trades)

    def _metrics(self, symbol, trades) -> Result:
        r = Result(symbol=symbol, trades=trades, total_trades=len(trades))
        if not trades:
            return r

        pnls = [t.pnl_pct for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        r.winning_trades = len(winners)
        r.losing_trades = len(losers)
        r.total_pnl_pct = sum(pnls)
        r.win_rate = len(winners) / len(pnls) * 100
        r.avg_winner_pct = np.mean(winners) if winners else 0
        r.avg_loser_pct = np.mean(losers) if losers else 0

        gp = sum(winners) if winners else 0
        gl = abs(sum(losers)) if losers else 0.001
        r.profit_factor = gp / gl

        if len(pnls) > 1:
            m, s = np.mean(pnls), np.std(pnls, ddof=1)
            if s > 0:
                days = max(1, (trades[-1].exit_date - trades[0].entry_date).days)
                tpy = min(len(trades) * 252 / days, 252)
                r.sharpe_ratio = (m / s) * np.sqrt(tpy)

        eq = [self.capital]
        for t in trades:
            eq.append(eq[-1] * (1 + t.pnl_pct / 100))
        eq = np.array(eq)
        pk = np.maximum.accumulate(eq)
        dd = (eq - pk) / pk * 100
        r.max_drawdown_pct = abs(min(dd))

        return r


# ─── Report ──────────────────────────────────────────────────

def print_report(results: List[Result]):
    print("\n" + "=" * 80)
    print("  TECHNICAL-ONLY BACKTEST (No AI Predictor)")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    all_trades = []
    for r in results:
        all_trades.extend(r.trades)
        print(f"\n{'─'*60}")
        print(f"  📊 {r.symbol}")
        print(f"{'─'*60}")
        print(f"  Trades:         {r.total_trades}")
        print(f"  Win/Loss:       {r.winning_trades} / {r.losing_trades}")
        print(f"  Win Rate:       {r.win_rate:.1f}%")
        print(f"  Total P&L:      {r.total_pnl_pct:+.2f}%")
        print(f"  Profit Factor:  {r.profit_factor:.2f}")
        print(f"  Sharpe:         {r.sharpe_ratio:.2f}")
        print(f"  Max Drawdown:   {r.max_drawdown_pct:.2f}%")
        print(f"  Avg Winner:     {r.avg_winner_pct:+.2f}%")
        print(f"  Avg Loser:      {r.avg_loser_pct:+.2f}%")
        if r.trades:
            reasons = {}
            strategies = {}
            for t in r.trades:
                reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
                strategies[t.strategy] = strategies.get(t.strategy, 0) + 1
            print(f"  Exit Reasons:   {reasons}")
            print(f"  Strategies:     {strategies}")

    # Strategy breakdown across all symbols
    if all_trades:
        print(f"\n{'─'*60}")
        print(f"  📊 STRATEGY BREAKDOWN")
        print(f"{'─'*60}")
        strats = {}
        for t in all_trades:
            if t.strategy not in strats:
                strats[t.strategy] = []
            strats[t.strategy].append(t.pnl_pct)
        
        print(f"  {'Strategy':<22} {'Trades':<8} {'Win%':<8} {'AvgP&L':<10} {'PF':<8}")
        print(f"  {'─'*22} {'─'*7} {'─'*7} {'─'*9} {'─'*7}")
        for s, pnls in sorted(strats.items()):
            w = [p for p in pnls if p > 0]
            l = [p for p in pnls if p <= 0]
            wr = len(w) / len(pnls) * 100
            ap = np.mean(pnls)
            gp = sum(w) if w else 0
            gl = abs(sum(l)) if l else 0.001
            pf = gp / gl
            mark = " ✅" if pf > 1.3 else " ⚠️" if pf > 1.0 else " ❌"
            print(f"  {s:<22} {len(pnls):<8} {wr:<7.1f}% {ap:<+9.2f}% {pf:<7.2f}{mark}")

    # Aggregate
    if len(results) > 1 and all_trades:
        print(f"\n{'='*80}")
        print(f"  AGGREGATE ({len(results)} symbols)")
        print(f"{'='*80}")
        tt = sum(r.total_trades for r in results)
        tw = sum(r.winning_trades for r in results)
        all_pnls = [t.pnl_pct for t in all_trades]
        gp = sum(p for p in all_pnls if p > 0)
        gl = abs(sum(p for p in all_pnls if p <= 0)) or 0.001
        avg_pnl = sum(r.total_pnl_pct for r in results) / len(results)

        print(f"  Total Trades:     {tt}")
        print(f"  Overall Win Rate: {tw/tt*100:.1f}%" if tt else "  No trades")
        print(f"  Avg P&L/Symbol:   {avg_pnl:+.2f}%")
        print(f"  Agg Profit Factor:{gp/gl:.2f}")
        print(f"  Avg Sharpe:       {np.mean([r.sharpe_ratio for r in results]):.2f}")
        print(f"  Worst Drawdown:   {max(r.max_drawdown_pct for r in results):.2f}%")

    # Comparison header
    print(f"\n{'='*80}")
    print(f"  COMPARE: AI vs Technical-Only")
    print(f"{'='*80}")
    print(f"  {'Metric':<20} {'AI (v2)':<15} {'Technical':<15}")
    print(f"  {'─'*20} {'─'*14} {'─'*14}")
    tt = sum(r.total_trades for r in results)
    tw = sum(r.winning_trades for r in results)
    all_pnls = [t.pnl_pct for t in all_trades] if all_trades else [0]
    gp = sum(p for p in all_pnls if p > 0)
    gl = abs(sum(p for p in all_pnls if p <= 0)) or 0.001
    avg_s = np.mean([r.sharpe_ratio for r in results]) if results else 0
    print(f"  {'Trades':<20} {'159':<15} {tt:<15}")
    print(f"  {'Win Rate':<20} {'32.7%':<15} {tw/tt*100 if tt else 0:.1f}%")
    print(f"  {'Profit Factor':<20} {'0.75':<15} {gp/gl:.2f}")
    print(f"  {'Avg Sharpe':<20} {'-0.75':<15} {avg_s:.2f}")

    # Save trade log
    if all_trades:
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, 'backtest_technical_trades.csv')
        rows = [{
            'symbol': t.symbol, 'direction': t.direction, 'strategy': t.strategy,
            'confidence': round(t.confidence, 4),
            'entry_date': t.entry_date, 'entry_price': round(t.entry_price, 2),
            'exit_date': t.exit_date, 'exit_price': round(t.exit_price, 2),
            'stop_loss': round(t.stop_loss, 2), 'target': round(t.target, 2),
            'pnl_pct': round(t.pnl_pct, 3), 'exit_reason': t.exit_reason,
        } for t in all_trades]
        pd.DataFrame(rows).to_csv(path, index=False)
        print(f"\n  📁 Trade log: {path}")

    print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(description='Technical-Only Backtest')
    parser.add_argument('--symbols', nargs='+',
                        default=['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'SBIN', 'NIFTY50', 'BANKNIFTY'])
    parser.add_argument('--period', default='2y')
    parser.add_argument('--atr-sl', type=float, default=1.5)
    parser.add_argument('--atr-tp', type=float, default=2.5)
    parser.add_argument('--max-hold', type=int, default=7)
    parser.add_argument('--min-conf', type=float, default=0.60)
    args = parser.parse_args()

    bt = TechnicalBacktester(
        atr_sl=args.atr_sl, atr_tp=args.atr_tp,
        max_hold=args.max_hold, min_conf=args.min_conf,
    )
    results = []
    for sym in args.symbols:
        try:
            results.append(bt.backtest_symbol(sym, args.period))
        except Exception as e:
            logger.error(f"Failed {sym}: {e}")
            results.append(Result(symbol=sym))
    print_report(results)


if __name__ == '__main__':
    main()
