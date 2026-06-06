# 🔧 Indian Trading Platform — Comprehensive Bug Report & Fixing Guide

> **Purpose:** This document catalogs every identified bug, logic flaw, and design issue that is causing loss trades or operational failures. Hand this document to a developer or AI assistant to systematically fix each issue.
>
> **⚠️ DO NOT modify:** Angel One API functions (`angel_one_api.py`), `.env` credentials, or broker connection logic. These are working correctly.

---

## Table of Contents

- [Section A: CRITICAL Bugs (Direct Loss-Causing)](#section-a-critical-bugs-direct-loss-causing)
- [Section B: HIGH Severity Bugs (Significant Loss Contributors)](#section-b-high-severity-bugs-significant-loss-contributors)
- [Section C: MODERATE Bugs (Operational / Reliability Issues)](#section-c-moderate-bugs-operational--reliability-issues)
- [Section D: Supporting Module Bugs (Legacy / Unused but Risky)](#section-d-supporting-module-bugs-legacy--unused-but-risky)
- [Section E: AI Model & Training Issues](#section-e-ai-model--training-issues)
- [Prioritized Fix Order](#prioritized-fix-order)

---

## Section A: CRITICAL Bugs (Direct Loss-Causing)

These bugs are actively causing real monetary losses on every trading session.

---

### A1. 🔴 Locked Margin Calculation Uses `quantity²` (Squared) Instead of `quantity`

**File:** `indian_trading_system.py`, Lines 2317-2320
**Impact:** Under-sizes ALL subsequent trade positions, leading to tiny profits on winners but proportionally larger losses on earlier trades.

```python
# BUGGY CODE:
locked_margin = sum(
    t.get('entry_price', 0) * t.get('quantity', 0) * abs(t.get('quantity', 0))
    for t in self.active_trades.values()
) / max(len(self.active_trades), 1)
```

**Problem:** `quantity * abs(quantity)` = `quantity²`. If quantity is 50, this calculates 2500× entry_price per trade instead of 50×. Additionally, dividing by `len(active_trades)` averages instead of summing total locked capital.

**Fix:**
```python
locked_margin = sum(
    t.get('entry_price', 0) * t.get('quantity', 0)
    for t in self.active_trades.values()
)
```

---

### A2. 🔴 AI Confidence Artificially Inflated — Low-Quality Signals Pass Quality Gate

**File:** `indian_trading_system.py`, Line 419
**Impact:** Mediocre AI predictions (raw 55% — barely above random for a 3-class classifier where 33% is random) are boosted to 82%+ and trigger real trades.

```python
# BUGGY CODE:
confidence = min(max(0.82 + (raw_conf - 0.55) * 0.36, 0.60), 0.98)
```

**Problem:** This linearly maps raw softmax confidence from [0.55, 1.0] → [0.82, 0.98]. A raw confidence of 0.55 (barely above random) gets mapped to 0.82 — passing the quality gate at line 1394 (`>= 0.82`). The quality gate becomes meaningless.

**Fix:** Either raise the raw confidence threshold to 0.65+ before mapping, or use an honest mapping that starts below the quality gate:
```python
# Option 1: Raise raw threshold
if raw_conf < 0.65:
    return None  # Skip weak signals

# Option 2: Honest mapping [0.55, 1.0] -> [0.60, 0.95]
confidence = min(max(0.60 + (raw_conf - 0.55) * 0.78, 0.50), 0.95)
```

---

### A3. 🔴 Indicator Key Mismatch — 4+ Strategies Silently Broken

**File:** `indian_trading_system.py`
**Impact:** Major strategies for large-cap stocks (RELIANCE, TCS, HDFCBANK, INFY) silently fail, generating no signals or wrong signals.

`_calculate_indian_indicators()` (line 496) returns these keys:
```
'rsi', 'macd', 'macd_signal', 'bb_upper', 'bb_lower', 'sma50', 'sma200', 'volume_ratio', 'support_levels', 'resistance_levels', 'atr'
```

But multiple strategies read **non-existent keys**:

| Strategy | Line | Reads | Actual Key | Result |
|----------|------|-------|------------|--------|
| `trend_following_strategy` | 997 | `sma_20` | Not computed | Falls back to `current_price` |
| `trend_following_strategy` | 998 | `sma_50` | `sma50` | Falls back to `current_price` |
| `trend_following_strategy` | 999 | `ema_12` | Not computed | Falls back to `current_price` |
| `trend_following_strategy` | 1000 | `ema_26` | Not computed | Falls back to `current_price` |
| `large_cap_strategy` | 1117-1118 | `sma_50`, `sma_200` | `sma50`, `sma200` | Falls back to `current_price` |
| `mean_reversion_strategy` | 950 | `bb_middle` | Not computed | Target = `current_price` (0% profit) |
| `stock_momentum_strategy` | 1180-1181 | `stochastic_k`, `williams_r` | Not computed | Always default |
| `stock_volatility_strategy` | 1242 | `bb_width` | Not computed | Always default |

**Fix:** Add the missing keys to `_calculate_indian_indicators()`:
```python
return {
    # ... existing keys ...
    'sma_20': sma20.iloc[-1] if not sma20.empty else close_prices.iloc[-1],
    'sma_50': sma50.iloc[-1] if not sma50.empty else close_prices.iloc[-1],  # alias for sma50
    'sma_200': sma200.iloc[-1] if not sma200.empty else close_prices.iloc[-1],  # alias for sma200
    'ema_12': ema12.iloc[-1] if not ema12.empty else close_prices.iloc[-1],
    'ema_26': ema26.iloc[-1] if not ema26.empty else close_prices.iloc[-1],
    'bb_middle': sma20.iloc[-1] if not sma20.empty else close_prices.iloc[-1],
    'bb_width': ((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / sma20.iloc[-1]) if not sma20.empty else 0.04,
    'stochastic_k': stoch_k,  # need to compute
    'williams_r': williams_r,  # need to compute
}
```

---

### A4. 🔴 Trailing Stop Never Activates Before Breakeven Is Set

**File:** `indian_trading_system.py`, Line 1784
**Impact:** Stop loss stays at the original wide level forever if the price never reaches 1 ATR in profit. A sudden reversal hits the original stop instead of a tightened one.

```python
# BUGGY CODE:
if 'breakeven_set' not in trade:
    if pct_from_entry >= atr_pct:
        # ... set breakeven ...
        trade['breakeven_set'] = True
    return  # ← THIS RETURN IS OUTSIDE THE INNER IF — always returns!
```

**Problem:** The `return` at line 1784 executes even when `pct_from_entry < atr_pct`. This means the ATR-based trailing stop logic (lines 1787-1812) is **never reached** until breakeven is first set. Trades that move slowly in your favor (say 0.5 ATR) never get their stops tightened.

**Fix:**
```python
if 'breakeven_set' not in trade:
    if pct_from_entry >= atr_pct:
        if trade['type'] == 'BUY' and current_price > trade['entry_price']:
            new_sl = trade['entry_price'] * 1.001
            if new_sl > trade['stop_loss']:
                trade['stop_loss'] = new_sl
                trade['breakeven_set'] = True
                logger.info(f"🔒 Breakeven set for {trade_id} (BUY)")
        elif trade['type'] == 'SELL' and current_price < trade['entry_price']:
            new_sl = trade['entry_price'] * 0.999
            if new_sl < trade['stop_loss']:
                trade['stop_loss'] = new_sl
                trade['breakeven_set'] = True
                logger.info(f"🔒 Breakeven set for {trade_id} (SELL)")
    return  # Only skip trailing AFTER breakeven logic runs — this is correct placement
    # BUT: consider removing this return entirely so trailing can gradually tighten
    # even before breakeven, using a wider trail distance pre-breakeven
```

---

### A5. 🔴 Breakout Strategy Target Set BELOW Current Price for BUY

**File:** `indian_trading_system.py`, Lines 739-742, 1067-1070
**Impact:** Creates BUY signals with targets below entry price (inverted profit target).

```python
# BUGGY CODE:
for resistance in resistance_levels:
    if current_price > resistance and volume_ratio > 1.5:
        breakout_buy = True
        breakout_target = resistance * 1.02  # BUG!
        break
```

**Problem:** When `current_price > resistance`, the price has already broken out. Setting target to `resistance * 1.02` can be BELOW `current_price`. Example: resistance=100, current_price=103 → target=102 < 103.

> **Note:** The ATR override at lines 463-475 fixes this for the primary `_apply_indian_strategies` path, but `enhanced_breakout_strategy` (line 1054) does NOT have this override.

**Same bug at Line 752:** `breakdown_target = support * 0.98` for SELL can be above current price.

**Fix:**
```python
breakout_target = max(resistance * 1.02, current_price * 1.015)
# For sell:
breakdown_target = min(support * 0.98, current_price * 0.985)
```

---

### A6. 🔴 RSI Uses Simple Moving Average Instead of Wilder's Exponential Smoothing

**File:** `indian_trading_system.py`, Lines 897-901
**Impact:** RSI values differ from the standard RSI that the 30/70 overbought/oversold thresholds were calibrated for, causing premature or delayed signals.

```python
# BUGGY CODE:
gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()  # SMA
loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()  # SMA
```

**Fix:** Use Wilder's exponential smoothing:
```python
gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, min_periods=period).mean()
loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, min_periods=period).mean()
```

---

## Section B: HIGH Severity Bugs (Significant Loss Contributors)

---

### B1. 🟠 `_get_atr_pct` Always Returns 2% Default — Volatility Filter Useless

**File:** `indian_trading_system.py`, Line 1856 (the `_get_atr_pct` method)
**Impact:** The volatility filter at line 2278 (`atr_pct < self.min_volatility_pct` at 0.3%) almost never triggers because ATR always defaults to 2%. Trailing stops also use this 2% default instead of actual volatility.

```python
# BUGGY CODE:
df = self.trading_system.get_indian_market_data(symbol)
# No period/interval specified → defaults to 1 day of data
# len(df) > 14 fails → returns default 0.02
```

**Fix:**
```python
df = self.trading_system.get_indian_market_data(symbol, period='1mo', interval='1d')
```

---

### B2. 🟠 Confidence × Streak Multiplier Can Over-Leverage After Wins

**File:** `indian_trading_system.py`, Line 2329
**Impact:** With artificially inflated confidence (Bug A2), sizing multipliers compound dangerously.

```python
confidence_mult = min(2.0, max(0.3, signal.confidence / 0.75))
# confidence=0.98 → 0.98/0.75 = 1.31x
# streak_mult = 1.2 (after 3 wins)
# Total: 1.31 × 1.2 = 1.57x base quantity
```

**Fix:** Cap the combined multiplier:
```python
confidence_mult = min(1.5, max(0.5, signal.confidence / 0.80))
streak_mult = 0.5 if self.consecutive_losses >= 3 else 1.0  # Remove win boost
```

---

### B3. 🟠 BANKNIFTY Sell Confidence Always 1.0 — No Quality Differentiation

**File:** `indian_trading_system.py`, Line 704
**Impact:** All SELL signals from BANKNIFTY volatility strategy get maximum confidence regardless of RSI extremity.

```python
# BUGGY CODE (SELL condition requires rsi > 75):
confidence = min((rsi - 25) / 50, 1.0)
# At RSI=75: (75-25)/50 = 1.0 → always 1.0
```

**Fix:**
```python
confidence = min((rsi - 75) / 25, 1.0)  # Scales within 75-100 range
```

---

### B4. 🟠 Trend Filter Uses Wrong Column Name — Silently Disabled for yfinance Data

**File:** `indian_trading_system.py`, Lines 2262-2266
**Impact:** The trend filter silently fails when yfinance returns data with capitalized column `Close`, allowing counter-trend entries.

```python
# BUGGY CODE:
df = self.trading_system.get_indian_market_data(signal.symbol)
closes = df['close'].values  # lowercase — yfinance returns 'Close' (capital C)
```

**Fix:**
```python
col = 'close' if 'close' in df.columns else 'Close'
closes = df[col].values
```

---

### B5. 🟠 Trend Filter Uses SMA But Variable Named `ema50`

**File:** `indian_trading_system.py`, Line 2265
**Impact:** SMA reacts more slowly than EMA. Trend detection is sluggish, potentially allowing counter-trend entries.

```python
# BUGGY CODE:
ema50 = np.mean(closes[-self.trend_ema_period:])  # This is SMA, not EMA
```

**Fix:**
```python
# Use proper EMA calculation
weights = np.exp(np.linspace(-1., 0., self.trend_ema_period))
weights /= weights.sum()
ema50 = np.dot(weights, closes[-self.trend_ema_period:])
```

---

### B6. 🟠 Hardcoded Price Ranges Are Stale — Valid Trades Rejected

**File:** `indian_trading_system.py`, Lines 120-141
**Impact:** As stock prices evolve over time, the hardcoded ranges become invalid and reject legitimate market data as "anomalous." This causes missed trading opportunities.

```python
self.price_ranges = {
    'NIFTY50': (18000, 28000),    # May be outdated
    'BANKNIFTY': (40000, 55000),  # May be outdated
    'SENSEX': (55000, 85000),     # May be outdated
    'RELIANCE': (1000, 1800),
    # ...
}
```

**Fix:** Either:
1. Widen the ranges significantly with dynamic updates, or
2. Remove static ranges and rely on the `_is_price_sane()` method's 50% deviation check from entry price (which is already implemented).

---

### B7. 🟠 Gemini Validation Is Advisory-Only But Still Called — Wastes 5-10s Per Trade

**File:** `indian_trading_system.py`, Lines 2304-2306
**Impact:** Adds 5-10 seconds of latency to every trade entry for a no-op API call.

```python
if not self._validate_with_gemini(signal):
    logger.info(f"🤖 Gemini AI advisory: ... — allowing trade anyway")
```

**Fix:** Either remove the call entirely, or re-enable it as a blocking gate:
```python
# Option 1: Remove (recommended for speed)
# Delete lines 2304-2306

# Option 2: Re-enable as gate
if not self._validate_with_gemini(signal):
    logger.info(f"🤖 Gemini REJECTED: {signal.symbol} {signal.signal_type}")
    return
```

---

### B8. 🟠 Mean Reversion Target = Current Price (0% Profit Target)

**File:** `indian_trading_system.py`, Line 950
**Impact:** Mean reversion strategy generates signals with target equal to current price.

```python
bb_middle = indicators.get('bb_middle', current_price)
# 'bb_middle' never exists in indicators → always current_price
# target = bb_middle = current_price → 0% profit target
```

**Fix:** Calculate `bb_middle` in `_calculate_indian_indicators()`:
```python
'bb_middle': sma20.iloc[-1] if not sma20.empty else close_prices.iloc[-1],
```

---

## Section C: MODERATE Bugs (Operational / Reliability Issues)

---

### C1. 🟡 Strategy Targets Overwritten by ATR — Strategy-Specific Levels Wasted

**File:** `indian_trading_system.py`, Lines 463-475
**Impact:** All strategy-computed stop-loss and target prices are replaced by ATR-based values. While ATR levels are generally safer, this makes the specific breakout/momentum/mean-reversion targets meaningless.

**Recommendation:** Consider blending strategy targets with ATR bounds rather than fully overriding:
```python
# Use the better of strategy target or ATR target
if signal.signal_type == 'BUY':
    signal.target_price = max(signal.target_price, current_price * (1 + target_mult))
    signal.stop_loss = max(signal.stop_loss, current_price * (1 - stop_mult))  # Tighter SL
```

---

### C2. 🟡 Win/Loss Streak Reset Daily — Streak Protection Weakened

**File:** `indian_trading_system.py`, Lines 1607-1608
**Impact:** A trader with 5 consecutive losses across 2 days gets their streak reset at midnight, going back to full sizing on day 2.

```python
self.consecutive_wins = 0
self.consecutive_losses = 0
```

**Recommendation:** Don't reset streaks at the day boundary. Only reset after a configurable number of profitable trades.

---

### C3. 🟡 Lock Held During DB Writes — Potential UI Stalls

**File:** `indian_trading_system.py`, Lines 2465-2602
**Impact:** The `_close_trade` method holds `self._lock` while performing SQLite writes and Socket.IO emissions. If DB writes are slow, the main trading loop and WebSocket price handler stall.

**Fix:** Minimize the critical section — only hold the lock for in-memory state mutations, release it before DB and network operations.

---

### C4. 🟡 `abs()` on R:R Scale-Out Check — Fragile Design

**File:** `indian_trading_system.py`, Lines 1860-1861
**Impact:** Currently protected by the `in_profit` guard at line 1864, but architecturally dangerous.

```python
risk_per_unit = abs(trade['entry_price'] - stop_loss)
reward_per_unit = abs(current_price - trade['entry_price'])
```

**Recommendation:** Use direction-aware calculations:
```python
if trade['type'] == 'BUY':
    reward_per_unit = current_price - trade['entry_price']
else:
    reward_per_unit = trade['entry_price'] - current_price
risk_per_unit = abs(trade['entry_price'] - stop_loss)
if reward_per_unit > 0 and reward_per_unit / risk_per_unit >= 1.0:
    # Scale out
```

---

### C5. 🟡 Support/Resistance Levels From Distant Past

**File:** `indian_trading_system.py`, Lines 907-930
**Impact:** `_find_support_levels()` and `_find_resistance_levels()` find ALL historical local minima/maxima, not just recent ones. Levels from months ago may be irrelevant.

**Fix:** Only consider the last 60 candles for support/resistance detection.

---

### C6. 🟡 Duplicate Log for Partial Trades

**File:** `indian_trading_system.py`, Lines 1525-1528
**Impact:** Minor — duplicate logging for rehydrated partial-exit trades.

```python
if partial_exit:
    self.scaled_out[tid] = True
    logger.info(f"Restored active trade: {tid}...")  # Log #1 (inside if)
# There's a second logger.info outside the if block  # Log #2
```

---

## Section D: Supporting Module Bugs (Legacy / Unused but Risky)

> **Note:** These files (`auto_trader.py`, `order_manager.py`, `risk_manager.py`, `symbols.py`) appear to be **legacy modules** that are NOT used by the active Indian trading path (`indian_trading_system.py`). However, they could cause issues if any code path references them.

---

### D1. 🔴 `auto_trader.py` — `close_trade()` Doesn't Actually Close Trades

**File:** `auto_trader.py`, Lines 348-362
**Impact:** Only removes trade from in-memory dict. No database update, no P&L calculation, no broker exit order.

```python
def close_trade(self, trade_id: str):
    if trade_id in self.active_trades:
        del self.active_trades[trade_id]
        # "Here you would implement the actual trade closing logic"
```

**Fix:** This entire module needs a full implementation or should be removed if `indian_trading_system.py` is the active system.

---

### D2. 🔴 `auto_trader.py` — Hardcoded 2% Volatility in `_calculate_volatility`

**File:** `auto_trader.py`, Lines 337-346

```python
def _calculate_volatility(self, symbol: str) -> float:
    return 0.02  # Always returns 2% regardless of actual volatility
```

---

### D3. 🔴 `risk_manager.py` — Duplicate `calculate_position_size` Methods

**File:** `risk_manager.py`, Lines 94 vs 391
**Impact:** Two methods with the SAME name but DIFFERENT signatures. Second definition overrides the first. Callers using the first signature crash.

---

### D4. 🔴 `order_manager.py` — Double-Locking Causes Deadlock

**File:** `order_manager.py`, Lines 74 and 188
**Impact:** `place_order()` acquires `self._lock`, then calls `_execute_order()` which tries to acquire the SAME non-reentrant lock → deadlock.

**Fix:** Change `self._lock = threading.Lock()` to `self._lock = threading.RLock()`.

---

### D5. 🔴 `order_manager.py` — Stop-Loss/Take-Profit Not Attached to Market Orders

**File:** `order_manager.py`, Lines 202-221
**Impact:** Market orders created with `sl_price=None` and `tp_price=None` — no stop loss protection.

---

### D6. 🔴 `symbols.py` — No Indian Symbols in Working Symbols List

**File:** `symbols.py`, Lines 38-47
**Impact:** `get_working_symbols()` returns only US symbols. After the US filter in `auto_trader.py`, the symbol list is empty.

---

### D7. 🟠 `risk_manager.py` — `get_daily_pnl` Uses Entry Time Instead of Exit Time

**File:** `risk_manager.py`, Lines 224-228

```python
# Counts PnL based on when trades were OPENED, not CLOSED
SELECT SUM(profit_loss) FROM trades WHERE DATE(entry_time) = ?
```

**Fix:** Use `DATE(exit_time)`.

---

### D8. 🟠 `database_config.py` — MySQL vs SQLite Schema Mismatch

**File:** `database_config.py`
**Impact:** Creates MySQL tables but the app uses SQLite. Column names differ between the schemas (e.g., `current_price` vs `average_price` in the positions table).

---

### D9. 🟠 `config.py` — Conflicting Cache Durations

**File:** `config.py`, Lines 18 vs 37

```python
CACHE_DURATION = 1        # 1 second
PRICE_CACHE_DURATION = 300  # 5 minutes — trading on 5-minute-old prices!
```

---

## Section E: AI Model & Training Issues

---

### E1. 🔴 Training Data Cross-Symbol Leakage

**File:** `ai_models/signal_predictor.py`, Lines 301-302
**Impact:** Model trains on corrupted data, leading to overfit accuracy but poor live performance.

```python
# BUGGY CODE:
combined = pd.concat(all_dfs, ignore_index=True)  # Destroys datetime index
combined = combined.sort_index()  # Sorts by meaningless integer index
```

**Problem:** `ignore_index=True` replaces datetime indices with integers (0, 1, 2...). `sort_index()` then sorts by these meaningless integers. Data from different symbols is interleaved in fetch order, NOT chronologically. The `create_labels()` function uses `shift(-3)` to look 3 periods into the "future" — but at symbol boundaries, the last 3 rows of RELIANCE use the first 3 rows of TCS as "future" data. This is **data leakage**.

**Fix:**
```python
# Option 1: Keep datetime index
combined = pd.concat(all_dfs)  # Don't ignore index
combined = combined.sort_index()

# Option 2 (better): Train per-symbol and average predictions
for sym in symbols:
    df = self.fetch_market_data(sym)
    model.train(df)  # Train on each symbol separately
```

---

### E2. 🟠 RSI in Feature Engineering Also Uses SMA (signal_predictor.py)

**File:** `ai_models/signal_predictor.py`, Lines 136-140

```python
gain = delta.where(delta > 0, 0).rolling(14).mean()  # SMA, not Wilder's
loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
```

**Impact:** Same as Bug A6 — RSI values differ from standard. However, since the model is trained and predicts with the same formula, this is internally consistent (just different from standard RSI).

**Recommendation:** Match the RSI calculation in both `signal_predictor.py` AND `indian_trading_system.py` to use the same method (preferably Wilder's EMA).

---

### E3. 🟠 Model Trained on Daily Data, Used for Intraday Predictions

**File:** `ai_models/signal_predictor.py`
**Impact:** The model is trained on `period='2y'` daily data (line 294) but used to predict on live intraday data via `predict_with_data()`. Features like RSI, MACD, and Bollinger Bands behave differently on daily vs intraday timeframes.

**Fix:** Train a separate intraday model using `interval='5m'` or `interval='15m'` data.

---

## Prioritized Fix Order

> Fix these in order for maximum impact on reducing losses:

| Priority | Bug ID | Description | Expected Impact |
|----------|--------|-------------|-----------------|
| 1 | **A1** | Fix locked margin (qty² → qty) | Correct position sizing for all trades |
| 2 | **A3** | Fix indicator key mismatch | Re-enable 4+ strategies for major stocks |
| 3 | **A2** | Fix AI confidence inflation | Filter out low-quality AI signals |
| 4 | **A4** | Fix trailing stop early return | Enable dynamic stop tightening |
| 5 | **B1** | Fix `_get_atr_pct` default | Enable real volatility-based trailing stops |
| 6 | **A6** | Fix RSI calculation | Correct overbought/oversold detection |
| 7 | **A5** | Fix breakout target below price | Correct profit targets on breakout trades |
| 8 | **B3** | Fix BANKNIFTY sell confidence | Better signal quality differentiation |
| 9 | **B4** | Fix trend filter column name | Re-enable trend filter for yfinance data |
| 10 | **E1** | Fix training data leakage | Better AI model predictions |
| 11 | **B2** | Cap confidence × streak multiplier | Prevent over-leveraging after wins |
| 12 | **B7** | Remove/fix Gemini advisory call | Reduce trade entry latency by 5-10s |
| 13 | **B8** | Fix mean reversion target | Correct profit target for mean reversion |
| 14 | **B6** | Update hardcoded price ranges | Stop rejecting valid market data |
| 15 | **C1-C6** | Moderate fixes | General reliability improvements |

---

## Quick Verification After Fixes

After applying fixes, run these checks:

```bash
# 1. Syntax check
python -m py_compile indian_trading_system.py
python -m py_compile app.py
python -m py_compile ai_models/signal_predictor.py

# 2. Check indicator keys match
python -c "
from indian_trading_system import IndianTradingSystem
# Verify _calculate_indian_indicators returns all required keys
"

# 3. Verify locked margin formula
python -c "
# Simulate: entry=1000, qty=50
# Old: 1000 * 50 * 50 = 2,500,000 (WRONG)
# New: 1000 * 50 = 50,000 (CORRECT)
print('Old margin:', 1000 * 50 * abs(50))
print('New margin:', 1000 * 50)
"

# 4. Restart server
taskkill /F /FI "WINDOWTITLE eq python*" 2>nul
.\venv_fresh\Scripts\python.exe app.py
```

---

> **Document generated on:** 2026-06-06
> **Files analyzed:** `indian_trading_system.py` (2661 lines), `app.py` (5948 lines), `signal_predictor.py` (525 lines), `gemini_explainer.py` (264 lines), `risk_manager.py` (650 lines), `order_manager.py` (271 lines), `auto_trader.py` (370 lines), `config.py` (93 lines), `database_config.py` (285 lines), `symbols.py` (47 lines), `trading_system.py` (549 lines)
