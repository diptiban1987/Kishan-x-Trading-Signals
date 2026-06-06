#!/usr/bin/env python3
"""
Walk-Forward Backtesting Framework for Indian Trading System v2
===============================================================
Fixes from v1:
  - Deduplicates trades across overlapping walk-forward windows
  - Tighter SL (1.0× ATR) vs wider TP (2.5× ATR) for better risk/reward
  - Confidence bucket analysis (are high-confidence signals actually better?)
  - Equity curve CSV output
  - Temperature-calibrated confidence from the predictor

Usage:
  python backtest.py                     # Run with defaults
  python backtest.py --symbols RELIANCE TCS BANKNIFTY
  python backtest.py --min-confidence 0.50
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_models.signal_predictor import AISignalPredictor

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    symbol: str
    direction: str
    entry_price: float
    entry_date: datetime
    exit_price: float = 0.0
    exit_date: Optional[datetime] = None
    stop_loss: float = 0.0
    target: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ''
    confidence: float = 0.0
    raw_confidence: float = 0.0


@dataclass
class BacktestResult:
    symbol: str
    trades: List[BacktestTrade] = field(default_factory=list)
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
    buy_precision: float = 0.0
    sell_precision: float = 0.0


class WalkForwardBacktester:
    def __init__(
        self,
        train_days: int = 252,
        test_days: int = 63,
        step_days: int = 63,          # NON-OVERLAPPING: step = test window
        atr_sl_mult: float = 1.0,     # Tighter SL: 1.0× ATR
        atr_tp_mult: float = 2.5,     # Wider TP: 2.5× ATR (better R:R)
        max_hold_days: int = 7,       # Extended from 5 to 7
        min_confidence: float = 0.50, # Lower threshold since calibrated now
        capital: float = 500000,
    ):
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.max_hold_days = max_hold_days
        self.min_confidence = min_confidence
        self.capital = capital
        self.predictor = AISignalPredictor()

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high, low, close = df['high'], df['low'], df['close']
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def backtest_symbol(self, symbol: str, period: str = '2y') -> BacktestResult:
        logger.info(f"{'='*60}")
        logger.info(f"Backtesting {symbol} (train={self.train_days}d, test={self.test_days}d, step={self.step_days}d)")

        df = self.predictor.fetch_market_data(symbol, period=period)
        if df is None or len(df) < self.train_days + self.test_days:
            logger.warning(f"Insufficient data for {symbol}")
            return BacktestResult(symbol=symbol)

        all_trades: List[BacktestTrade] = []
        traded_dates: set = set()  # Track (date) to prevent duplicates
        total_rows = len(df)
        window_start = 0
        fold = 0

        while window_start + self.train_days + self.test_days <= total_rows:
            fold += 1
            train_end = window_start + self.train_days
            test_end = min(train_end + self.test_days, total_rows)

            train_df = df.iloc[window_start:train_end].copy()
            test_df = df.iloc[train_end:test_end].copy()

            if len(train_df) < 100 or len(test_df) < 5:
                window_start += self.step_days
                continue

            # Train model on this window
            try:
                X_train = self.predictor.prepare_features(train_df)
                y_train = self.predictor.create_labels(train_df)
                valid = y_train.notna()
                X_train, y_train = X_train[valid], y_train[valid].astype(int)
                if len(X_train) < 50:
                    window_start += self.step_days
                    continue
                self.predictor._train_from_Xy(X_train, y_train, validation_split=0.15)
            except Exception as e:
                logger.error(f"Training failed fold {fold}: {e}")
                window_start += self.step_days
                continue

            # ATR from training data
            atr_series = self._calc_atr(train_df)
            last_atr = atr_series.iloc[-1] if not atr_series.empty and not np.isnan(atr_series.iloc[-1]) else None

            # Simulate trading — skip dates already traded (dedup)
            fold_trades = self._simulate_trading(test_df, last_atr, symbol, traded_dates)
            all_trades.extend(fold_trades)

            logger.info(f"  Fold {fold}: {train_df.index[0].date()}→{train_df.index[-1].date()} | "
                        f"test {test_df.index[0].date()}→{test_df.index[-1].date()} | "
                        f"trades={len(fold_trades)}")

            # NON-OVERLAPPING step
            window_start += self.step_days

        return self._compute_metrics(symbol, all_trades)

    def _simulate_trading(self, test_df, last_atr, symbol, traded_dates) -> List[BacktestTrade]:
        trades: List[BacktestTrade] = []
        active_trade: Optional[BacktestTrade] = None

        for i in range(len(test_df)):
            row = test_df.iloc[i]
            current_price = row['close']
            current_date = test_df.index[i]
            high, low = row['high'], row['low']
            date_key = current_date.date()

            # Check active trade exits
            if active_trade is not None:
                days_held = (current_date - active_trade.entry_date).days

                hit_sl = hit_tp = False
                if active_trade.direction == 'BUY':
                    hit_sl = low <= active_trade.stop_loss
                    hit_tp = high >= active_trade.target
                else:
                    hit_sl = high >= active_trade.stop_loss
                    hit_tp = low <= active_trade.target

                if hit_sl and hit_tp:
                    # Both hit same day — assume SL hit first (conservative)
                    active_trade.exit_price = active_trade.stop_loss
                    active_trade.exit_reason = 'stop_loss'
                elif hit_sl:
                    active_trade.exit_price = active_trade.stop_loss
                    active_trade.exit_reason = 'stop_loss'
                elif hit_tp:
                    active_trade.exit_price = active_trade.target
                    active_trade.exit_reason = 'target'
                elif days_held >= self.max_hold_days:
                    active_trade.exit_price = current_price
                    active_trade.exit_reason = 'max_hold'

                if active_trade.exit_reason:
                    active_trade.exit_date = current_date
                    if active_trade.direction == 'BUY':
                        active_trade.pnl_pct = (active_trade.exit_price - active_trade.entry_price) / active_trade.entry_price * 100
                    else:
                        active_trade.pnl_pct = (active_trade.entry_price - active_trade.exit_price) / active_trade.entry_price * 100
                    trades.append(active_trade)
                    active_trade = None
                continue

            # Skip if this date was already traded in a previous fold (dedup)
            if date_key in traded_dates:
                continue

            # Need lookback for features
            idx_pos = test_df.index.get_loc(current_date)
            if idx_pos < 1:
                continue
            lookback_df = test_df.iloc[:idx_pos + 1]
            if len(lookback_df) < 30:
                continue

            try:
                signal = self.predictor.predict(lookback_df)
            except Exception:
                continue

            direction = signal.get('signal', 'HOLD')
            confidence = signal.get('confidence', 0)
            raw_conf = signal.get('raw_confidence', confidence)

            if direction == 'HOLD' or confidence < self.min_confidence:
                continue

            # ATR-based SL/TP
            atr = last_atr if last_atr and last_atr > 0 else current_price * 0.015
            atr_pct = atr / current_price

            if direction == 'BUY':
                sl = current_price * (1 - atr_pct * self.atr_sl_mult)
                tp = current_price * (1 + atr_pct * self.atr_tp_mult)
            else:
                sl = current_price * (1 + atr_pct * self.atr_sl_mult)
                tp = current_price * (1 - atr_pct * self.atr_tp_mult)

            active_trade = BacktestTrade(
                symbol=symbol, direction=direction,
                entry_price=current_price, entry_date=current_date,
                stop_loss=sl, target=tp,
                confidence=confidence, raw_confidence=raw_conf,
            )
            traded_dates.add(date_key)

        # Close remaining open trade
        if active_trade is not None:
            active_trade.exit_price = test_df['close'].iloc[-1]
            active_trade.exit_date = test_df.index[-1]
            active_trade.exit_reason = 'end_of_period'
            if active_trade.direction == 'BUY':
                active_trade.pnl_pct = (active_trade.exit_price - active_trade.entry_price) / active_trade.entry_price * 100
            else:
                active_trade.pnl_pct = (active_trade.entry_price - active_trade.exit_price) / active_trade.entry_price * 100
            trades.append(active_trade)

        return trades

    def _compute_metrics(self, symbol, trades) -> BacktestResult:
        result = BacktestResult(symbol=symbol, trades=trades, total_trades=len(trades))
        if not trades:
            return result

        pnls = [t.pnl_pct for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        result.winning_trades = len(winners)
        result.losing_trades = len(losers)
        result.total_pnl_pct = sum(pnls)
        result.win_rate = len(winners) / len(pnls) * 100

        result.avg_winner_pct = np.mean(winners) if winners else 0
        result.avg_loser_pct = np.mean(losers) if losers else 0

        gross_profit = sum(winners) if winners else 0
        gross_loss = abs(sum(losers)) if losers else 0.001
        result.profit_factor = gross_profit / gross_loss

        if len(pnls) > 1:
            arr = np.array(pnls)
            mean_r, std_r = np.mean(arr), np.std(arr, ddof=1)
            if std_r > 0:
                days_span = max(1, (trades[-1].exit_date - trades[0].entry_date).days)
                tpy = min(len(trades) * 252 / days_span, 252)
                result.sharpe_ratio = (mean_r / std_r) * np.sqrt(tpy)

        equity = [self.capital]
        for t in trades:
            equity.append(equity[-1] * (1 + t.pnl_pct / 100))
        equity = np.array(equity)
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / peak * 100
        result.max_drawdown_pct = abs(min(dd))

        buy_t = [t for t in trades if t.direction == 'BUY']
        sell_t = [t for t in trades if t.direction == 'SELL']
        if buy_t:
            result.buy_precision = len([t for t in buy_t if t.pnl_pct > 0]) / len(buy_t) * 100
        if sell_t:
            result.sell_precision = len([t for t in sell_t if t.pnl_pct > 0]) / len(sell_t) * 100

        return result


def confidence_bucket_analysis(all_trades: List[BacktestTrade]):
    """Analyze: does higher confidence actually predict better outcomes?"""
    if not all_trades:
        return

    print(f"\n{'─' * 60}")
    print(f"  📊 CONFIDENCE BUCKET ANALYSIS")
    print(f"{'─' * 60}")
    print(f"  {'Confidence':<14} {'Trades':<8} {'Win%':<8} {'AvgP&L':<10} {'PF':<8}")
    print(f"  {'─'*14} {'─'*7} {'─'*7} {'─'*9} {'─'*7}")

    buckets = [(0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.01)]
    for lo, hi in buckets:
        bucket_trades = [t for t in all_trades if lo <= t.confidence < hi]
        if not bucket_trades:
            continue
        wins = [t for t in bucket_trades if t.pnl_pct > 0]
        pnls = [t.pnl_pct for t in bucket_trades]
        w_pnl = sum(p for p in pnls if p > 0)
        l_pnl = abs(sum(p for p in pnls if p <= 0)) or 0.001
        win_rate = len(wins) / len(bucket_trades) * 100
        avg_pnl = np.mean(pnls)
        pf = w_pnl / l_pnl
        label = f"{lo:.2f}–{hi:.2f}"
        marker = " ✅" if pf > 1.3 else " ⚠️" if pf > 1.0 else " ❌"
        print(f"  {label:<14} {len(bucket_trades):<8} {win_rate:<7.1f}% {avg_pnl:<+9.2f}% {pf:<7.2f}{marker}")


def print_report(results: List[BacktestResult]):
    print("\n" + "=" * 80)
    print("  WALK-FORWARD BACKTEST REPORT v2 (deduplicated, calibrated)")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    all_trades = []
    for r in results:
        all_trades.extend(r.trades)

        print(f"\n{'─' * 60}")
        print(f"  📊 {r.symbol}")
        print(f"{'─' * 60}")
        print(f"  Total Trades:     {r.total_trades}")
        print(f"  Winners/Losers:   {r.winning_trades} / {r.losing_trades}")
        print(f"  Win Rate:         {r.win_rate:.1f}%")
        print(f"  Total P&L:        {r.total_pnl_pct:+.2f}%")
        print(f"  Profit Factor:    {r.profit_factor:.2f}")
        print(f"  Sharpe Ratio:     {r.sharpe_ratio:.2f}")
        print(f"  Max Drawdown:     {r.max_drawdown_pct:.2f}%")
        print(f"  Avg Winner:       {r.avg_winner_pct:+.2f}%")
        print(f"  Avg Loser:        {r.avg_loser_pct:+.2f}%")
        print(f"  BUY Precision:    {r.buy_precision:.1f}%")
        print(f"  SELL Precision:   {r.sell_precision:.1f}%")

        if r.trades:
            reasons = {}
            for t in r.trades:
                reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
            print(f"  Exit Breakdown:   {reasons}")

    # Confidence bucket analysis
    confidence_bucket_analysis(all_trades)

    # Aggregate
    if len(results) > 1 and all_trades:
        print(f"\n{'=' * 80}")
        print(f"  AGGREGATE SUMMARY ({len(results)} symbols)")
        print(f"{'=' * 80}")

        total_trades = sum(r.total_trades for r in results)
        total_winners = sum(r.winning_trades for r in results)
        total_pnl = sum(r.total_pnl_pct for r in results) / len(results)
        all_pnls = [t.pnl_pct for t in all_trades]
        gp = sum(p for p in all_pnls if p > 0)
        gl = abs(sum(p for p in all_pnls if p <= 0)) or 0.001

        print(f"  Total Trades:     {total_trades}")
        print(f"  Overall Win Rate: {total_winners / total_trades * 100:.1f}%" if total_trades else "  No trades")
        print(f"  Avg P&L/Symbol:   {total_pnl:+.2f}%")
        print(f"  Agg Profit Factor:{gp / gl:.2f}")
        print(f"  Avg Sharpe:       {np.mean([r.sharpe_ratio for r in results]):.2f}")
        print(f"  Worst Drawdown:   {max(r.max_drawdown_pct for r in results):.2f}%")

    # Save trade log
    if all_trades:
        base = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base, 'backtest_trades.csv')
        rows = [{
            'symbol': t.symbol, 'direction': t.direction,
            'confidence': round(t.confidence, 4),
            'raw_confidence': round(t.raw_confidence, 4),
            'entry_date': t.entry_date, 'entry_price': round(t.entry_price, 2),
            'exit_date': t.exit_date, 'exit_price': round(t.exit_price, 2),
            'stop_loss': round(t.stop_loss, 2), 'target': round(t.target, 2),
            'pnl_pct': round(t.pnl_pct, 3), 'exit_reason': t.exit_reason,
        } for t in all_trades]
        pd.DataFrame(rows).to_csv(log_path, index=False)
        print(f"\n  📁 Trade log: {log_path}")

        # Save equity curve
        eq_path = os.path.join(base, 'backtest_equity.csv')
        equity = [500000]
        dates = [all_trades[0].entry_date]
        for t in all_trades:
            equity.append(equity[-1] * (1 + t.pnl_pct / 100))
            dates.append(t.exit_date)
        pd.DataFrame({'date': dates, 'equity': equity}).to_csv(eq_path, index=False)
        print(f"  📈 Equity curve: {eq_path}")

    print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(description='Walk-Forward Backtest v2')
    parser.add_argument('--symbols', nargs='+',
                        default=['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'SBIN', 'NIFTY50', 'BANKNIFTY'])
    parser.add_argument('--period', default='2y')
    parser.add_argument('--train-days', type=int, default=252)
    parser.add_argument('--test-days', type=int, default=63)
    parser.add_argument('--step-days', type=int, default=63)
    parser.add_argument('--min-confidence', type=float, default=0.50)
    parser.add_argument('--max-hold', type=int, default=7)
    parser.add_argument('--capital', type=float, default=500000)

    args = parser.parse_args()

    bt = WalkForwardBacktester(
        train_days=args.train_days, test_days=args.test_days,
        step_days=args.step_days, min_confidence=args.min_confidence,
        max_hold_days=args.max_hold, capital=args.capital,
    )

    results = []
    for sym in args.symbols:
        try:
            results.append(bt.backtest_symbol(sym, period=args.period))
        except Exception as e:
            logger.error(f"Backtest failed for {sym}: {e}")
            results.append(BacktestResult(symbol=sym))

    print_report(results)


if __name__ == '__main__':
    main()
