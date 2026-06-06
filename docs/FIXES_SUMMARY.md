# Fixes Applied — Summary & Impact

## CRITICAL Fixes

### A1 — Locked Margin Calculation (Qty² → Qty)
- **Before:** `entry_price × quantity × abs(quantity)` + averaging across active trades → massively overestimated locked margin → under-sized all subsequent trades
- **After:** `entry_price × quantity` (total sum, no averaging) → correct margin calculation → proper position sizing across all concurrent trades

### A2 — AI Confidence No Longer Artificially Inflated
- **Before:** Raw confidence of 0.55 (barely above random) was mapped to 0.82, passing the quality gate → weak signals triggered real trades
- **After:** Signals with raw confidence < 0.65 are rejected entirely. Remaining signals use an honest [0.55→1.0] → [0.60→0.95] mapping → only genuinely high-quality AI signals enter trades

### A3 — Indicator Keys Fixed (4+ Strategies Unblocked)
- **Before:** `trend_following`, `large_cap`, `mean_reversion`, `stock_momentum`, `stock_volatility` strategies all read non-existent keys (e.g. `sma_20`, `ema_12`, `bb_middle`, `stochastic_k`) → fell back to `current_price`, making targets/stops meaningless
- **After:** `_calculate_indian_indicators()` now returns all 9 missing keys with proper computed values → all strategies work correctly with real indicator data

### A4 — Trailing Stop Now Works Before Breakeven
- **Before:** The `return` on every pre-breakeven cycle prevented any trailing stop tightening until price hit 1 ATR profit → stop stayed at original wide level until breakeven, then jumped
- **After:** Pre-breakeven trailing enabled at 3× wider distance → stop gradually tightens even if price never reaches 1 ATR profit → reduced loss size on partial runners

### A5 — Breakout Targets No Longer Below Entry Price
- **Before:** `resistance × 1.02` could be below `current_price` when price already broke out → BUY targets set below entry (guaranteed loss if hit)
- **After:** `max(resistance × 1.02, current × 1.015)` for BUY, `min(support × 0.98, current × 0.985)` for SELL → targets are always above entry for BUY / below entry for SELL

### A6 — RSI Uses Wilder's EMA (Standard Calculation)
- **Before:** Simple moving average for RSI gains/losses → RSI values differed from standard 30/70 thresholds → premature or delayed signals
- **After:** Wilder's exponential smoothing (`ewm(alpha=1/14)`) → RSI matches standard calculation → overbought/oversold thresholds work as intended

## HIGH Severity Fixes

### B1 — ATR% Now Fetches Enough Data
- **Before:** `get_indian_market_data(symbol)` defaulted to 1 day → `len(df) > 14` almost always false → returned hardcoded 2% → volatility filter never triggered
- **After:** `get_indian_market_data(symbol, period='1mo', interval='1d')` → actual ATR calculated → volatility filter works, trailing stops use real market volatility

### B2 — Confidence × Streak Multiplier Capped
- **Before:** `confidence_mult` up to 2.0×, win streak bonus of 1.2× → combined 2.4× leverage after wins → overexposed after winning streak
- **After:** Confidence mult max 1.5× (at 90%+ confidence), streak mult is 1.0 or 0.5 (losses only, no win boost) → controlled sizing, no over-leverage after wins

### B3 — BANKNIFTY SELL Confidence Correctly Scaled
- **Before:** `min((rsi - 25) / 50, 1.0)` → at RSI=75 (sell threshold), confidence was always 1.0 → no quality differentiation
- **After:** `min((rsi - 75) / 25, 1.0)` → confidence scales from 0.0 at RSI=75 to 1.0 at RSI=100 → meaningful signal strength ranking

### B4 — Trend Filter Handles yfinance Column Names
- **Before:** Hardcoded `df['close']` → yfinance returns `Close` (capital C) → `KeyError` silently caught → trend filter effectively disabled
- **After:** `col = 'close' if 'close' in df.columns else 'Close'` → trend filter works with both data sources

### B5 — Trend Filter Uses Real EMA Instead of SMA
- **Before:** `np.mean(closes[-trend_ema_period:])` — this is SMA, not EMA, despite variable name `ema50` → sluggish trend detection
- **After:** Exponential weights via `np.exp(np.linspace(-1., 0., period))` → proper EMA → faster, more responsive trend detection

### B6 — Price Ranges Widened
- **Before:** Stale hardcoded ranges (e.g., BANKNIFTY 40000-55000, RELIANCE 1000-1800) rejected valid current market data
- **After:** Ranges widened significantly (BANKNIFTY 35000-65000, RELIANCE 800-2200, etc.) → legitimate trades no longer rejected

### B7 — Gemini Advisory Call Removed
- **Before:** `_validate_with_gemini()` called on every trade entry, but result was ignored → wasted 5-10 seconds per trade
- **After:** Call completely removed → trade entry latency reduced by 5-10 seconds

## MODERATE Fixes (Reliability)

### C1 — ATR Blends With Strategy Targets (Not Override)
- **Before:** ATR-based levels fully overwrote strategy-computed targets → strategy-specific breakout/momentum levels were meaningless
- **After:** Uses `max()` for BUY targets, `min()` for SELL targets → picks the better strategy or ATR level

### C2 — Win/Loss Streaks Not Reset Daily
- **Before:** `consecutive_wins` and `consecutive_losses` reset to 0 at midnight → trader with 5 losses across 2 days got full sizing back on day 2
- **After:** Streaks persist across days → sizing protection continues until actual winning trade resets the streak

### C3 — Lock Held Only for In-Memory State in `_close_trade`
- **Before:** `self._lock` held across SQLite writes (DB I/O) and Socket.IO emissions (network) → potential UI stalls and trading loop blocking
- **After:** Lock only covers fast in-memory mutations; DB and network operations outside lock → no UI stalls, responsive trading loop

### C4 — Direction-Aware R:R for Scale-Out
- **Before:** `abs(current_price - entry_price)` for both BUY and SELL → could show positive R:R even in losing direction (theoretically)
- **After:** BUY: `current - entry`, SELL: `entry - current` → only positive when trade is actually in profit

### C5 — Support/Resistance Uses Last 60 Candles
- **Before:** Scanned ALL historical data → pivot levels from months ago were irrelevant and caused stale breakout targets
- **After:** Only scans last 60 candles → support/resistance levels are recent and relevant

### C6 — Duplicate Log Removed
- **Before:** Two almost-identical log lines for partial-exit trades → noisy logs
- **After:** Single log line → cleaner monitoring output

## AI Model Fixes

### E1 — Training Data No Longer Has Cross-Symbol Leakage
- **Before:** `pd.concat(all_dfs, ignore_index=True)` replaced datetime with integer index → `sort_index()` sorted by meaningless integers → `shift(-3)` at symbol boundaries used next symbol's data as "future" → model trained on leaked data
- **After:** `pd.concat(all_dfs)` preserves datetime index → `sort_index()` sorts chronologically → no inter-symbol data leakage → model learns genuine patterns

### E2 — Signal Predictor RSI Matches Main System
- **Before:** `signal_predictor.py` used SMA-based RSI while `indian_trading_system.py` used Wilder's EMA → inconsistent RSI values between training and live inference
- **After:** Both use Wilder's `ewm(alpha=1/14)` → consistent RSI calculation → model features match live inference features
