# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 09:12:22
**Last Restart (fixes applied):** 09:50:00 IST
**Mode:** DEMO (Mock Funds ₹1,00,000)
**Angel One:** Connected (DEMO mode — virtual funds, live market data)
**Status:** ✅ RUNNING (auto-trading active)

---

## All Fixes Applied Today

| # | Fix | File | Details |
|---|-----|------|---------|
| 1 | Signal confidence threshold 0.60→**0.72** | `indian_trading_system.py:1340` | Only high-confidence trades enter |
| 2 | Max concurrent trades **3** | `indian_trading_system.py:1465` | Prevents over-trading |
| 3 | NIFTY momentum: multi-confirmation | `indian_trading_system.py:516` | 5 checks, requires 3+ |
| 4 | **Price validation** on all entries | `indian_trading_system.py:139-160` | Rejects trades with bad prices |
| 5 | **WebSocket bad tick rejection** | `indian_trading_system.py:1544-1568` | Ignores corrupt price ticks |
| 6 | **Monitor fallback** to yfinance | `indian_trading_system.py:1887-1910` | Falls back when WS price is wrong |
| 7 | **Price sanity check** before exits | `indian_trading_system.py:1597-1616` | Won't close at bad price |
| 8 | Trade quantity **enforced 1** | `indian_trading_system.py:1461` | Always 1 quantity |
| 9 | Activity logging added | `indian_trading_system.py:164-189` | Full trade log |
| 10 | `str.replace()` bug fixed | `indian_trading_system.py:1608` | Was causing monitor crash |

---

## Current Active Trades (as of 09:50 IST)

| Symbol | Type | Entry | Current | Qty | P&L | Strategy |
|--------|------|-------|---------|-----|-----|----------|
| HDFCBANK | BUY | 766.40 | 766.40 | 1 | 0.00 | AI XGBoost |
| KOTAKBANK | SELL | 388.90 | 388.90 | 1 | 0.00 | AI XGBoost |

---

## Full Trading Log

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance |
|------|--------|--------|-------|------|-----|-----|---------|
| 09:16:27 | TCS | ENTRY(BUY) | 2287.00 | - | 1 | 0.00 | 100000.00 |
| 09:16:27 | BAJFINANCE | ENTRY(BUY) | 933.60 | - | 1 | 0.00 | 100000.00 |
| 09:16:27 | BHARTIARTL | ENTRY(BUY) | 1851.20 | - | 1 | 0.00 | 100000.00 |
| 09:16:27 | INFY | ENTRY(BUY) | 1165.90 | - | 1 | 0.00 | 100000.00 |
| 09:16:27 | SENSEX | ENTRY(BUY) | 76009.70 | - | 1 | 0.00 | 100000.00 |
| 09:16:42 | HDFCBANK | ENTRY(BUY) | 766.40 | - | 1 | 0.00 | 100000.00 |
| 09:16:42 | ICICIBANK | ENTRY(BUY) | 1283.10 | - | 1 | 0.00 | 100000.00 |
| 09:16:42 | SBIN | ENTRY(SELL) | 970.50 | - | 1 | 0.00 | 100000.00 |
| 09:17:27 | KOTAKBANK | ENTRY(SELL) | 388.90 | - | 1 | 0.00 | 100000.00 |
| 09:34:36 | BAJFINANCE | CLOSE(Stop Loss) | 933.60 | 64.25 | 1 | -869.35 | 99130.65 |
| 09:46:07 | TCS | CLOSE(Target) | 2287.00 | 2266.70 | 1 | -20.30 | 99979.70 |
| 09:46:18 | BHARTIARTL | CLOSE(Target) | 1851.20 | 1847.70 | 1 | -3.50 | 99976.20 |
| 09:46:19 | INFY | CLOSE(Target) | 1165.90 | 1158.80 | 1 | -7.10 | 99969.10 |
| 09:46:29 | SENSEX | CLOSE(Target) | 76009.70 | 75877.13 | 1 | -132.57 | 99836.53 |
| 09:46:30 | ICICIBANK | CLOSE(Target) | 1283.10 | 1280.30 | 1 | -2.80 | 99833.73 |
| 09:46:31 | SBIN | CLOSE(Stop Loss) | 970.50 | 969.00 | 1 | +1.50 | 99835.23 |

---

## Performance Summary

| Metric | Value |
|--------|-------|
| Total Trades | 16 entered, 14 closed |
| Active Trades | 2 |
| Realized P&L | -1034.12 |
| Unrealized P&L | 0.00 |
| Total P&L | -1034.12 |
| Initial Balance | ₹1,00,000 |
| Current Portfolio | ~₹99,835 |
| Average Loss/Trade | -73.87 |
| Biggest Loss | -869.35 (BAJFINANCE — bad price feed) |

---

## Issues Resolved

1. **✅ BAJFINANCE bad stop loss (64.25)** — Root cause: Angel One WebSocket returning wrong price tick for BAJFINANCE token. **Fix:** Added price validation (`_is_price_sane`) that rejects any price >50% from entry, preventing false stop-loss triggers.

2. **✅ KOTAKBANK price validated** — ₹388 is correct. Stock has fallen significantly. Range check passes (300-2100). No issue here.

3. **✅ WebSocket corrupt ticks** — `on_price_update()` now validates every tick against both expected price range AND deviation from entry price before storing.

4. **✅ Monitor crash** — Fixed `str.replace('.NS', '.BO', '')` bug that was passing string as integer count parameter, crashing the entire monitor loop.

5. **⚠️ Old trades (pre-fix)** — 8 trades were entered with old 0.60 threshold. New threshold 0.72 will only allow higher-confidence trades going forward.

---

## Monitoring Notes

- **System will run until 15:30 IST** (market close)
- After market close, auto-sleeps until next trading day 09:15 IST
- New trades will only enter at confidence ≥ 0.72 with max 3 concurrent
- Price validation protects against bad WebSocket ticks
- Activity log auto-updates with each trade event

---

*Generated on 2026-05-27 at 09:50 IST by Kishan x Trading Signals — Fixes Applied*
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 09:57:24
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 10:07:47
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 10:09:48
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 10:55:28
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:10:46
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:11:15 | BHARTIARTL | ENTRY(BUY) | 1860.70 | 0.00 | 1 | +0.00 | 100000.00 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:16:33
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:16:37 | HDFCBANK | CLOSE(Partial Target Reached (50%)) | 766.40 | 765.30 | 1 | -1.10 | 99998.90 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:17:07
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:17:11 | KOTAKBANK | CLOSE(Stop Loss Hit) | 388.90 | 389.50 | 1 | -0.60 | 99998.30 | AI XGBoost Predictor |
| 11:17:12 | BHARTIARTL | CLOSE(Partial Target Reached (50%)) | 1860.70 | 1865.75 | 1 | +5.05 | 100003.35 | AI XGBoost Predictor |
| 11:17:40 | BHARTIARTL | ENTRY(BUY) | 1865.75 | 0.00 | 1 | +0.00 | 100003.35 | AI XGBoost Predictor |
| 11:17:40 | BAJFINANCE | ENTRY(BUY) | 928.45 | 0.00 | 1 | +0.00 | 100003.35 | AI XGBoost Predictor |
| 11:17:40 | TCS | ENTRY(BUY) | 2279.00 | 0.00 | 1 | +0.00 | 100003.35 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:18:41
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:18:43 | BHARTIARTL | CLOSE(Partial Target Reached (50%)) | 1865.75 | 1864.40 | 1 | -1.35 | 99998.65 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:19:16
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:19:22 | BAJFINANCE | CLOSE(Partial Target Reached (50%)) | 928.45 | 929.35 | 1 | +0.90 | 99999.55 | AI XGBoost Predictor |
| 11:19:25 | TCS | CLOSE(Partial Target Reached (50%)) | 2279.00 | 2278.65 | 1 | -0.35 | 99999.20 | AI XGBoost Predictor |
| 11:19:54 | BHARTIARTL | ENTRY(BUY) | 1864.40 | 0.00 | 1 | +0.00 | 99999.20 | AI XGBoost Predictor |
| 11:19:54 | BAJFINANCE | ENTRY(BUY) | 929.35 | 0.00 | 1 | +0.00 | 99999.20 | AI XGBoost Predictor |
| 11:19:54 | SENSEX | ENTRY(BUY) | 76188.67 | 0.00 | 1 | +0.00 | 99999.20 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:21:03
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:21:08 | BHARTIARTL | CLOSE(Partial Target Reached (50%)) | 1864.40 | 1865.90 | 1 | +1.50 | 100001.50 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:21:17
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:21:22 | BAJFINANCE | CLOSE(Partial Target Reached (50%)) | 929.35 | 929.90 | 1 | +0.55 | 100002.05 | AI XGBoost Predictor |
| 11:21:32 | SENSEX | CLOSE(Partial Target Reached (50%)) | 76188.67 | 76132.24 | 1 | -56.43 | 99945.62 | AI XGBoost Predictor |
| 11:22:09 | BHARTIARTL | ENTRY(BUY) | 1865.90 | 0.00 | 1 | +0.00 | 99945.62 | AI XGBoost Predictor |
| 11:22:09 | BAJFINANCE | ENTRY(BUY) | 929.90 | 0.00 | 1 | +0.00 | 99945.62 | AI XGBoost Predictor |
| 11:22:27 | TCS | ENTRY(BUY) | 2276.40 | 0.00 | 1 | +0.00 | 99945.62 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:23:39
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:23:41 | BHARTIARTL | CLOSE(Partial Target Reached (50%)) | 1865.90 | 1865.70 | 1 | -0.20 | 99999.80 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:24:05
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:24:09 | BAJFINANCE | CLOSE(Partial Target Reached (50%)) | 929.90 | 930.45 | 1 | +0.55 | 100000.35 | AI XGBoost Predictor |
| 11:24:10 | TCS | CLOSE(Partial Target Reached (50%)) | 2276.40 | 2276.70 | 1 | +0.30 | 100000.65 | AI XGBoost Predictor |
| 11:24:49 | BHARTIARTL | ENTRY(BUY) | 1865.70 | 0.00 | 1 | +0.00 | 100000.65 | AI XGBoost Predictor |
| 11:24:49 | BAJFINANCE | ENTRY(BUY) | 930.45 | 0.00 | 1 | +0.00 | 100000.65 | AI XGBoost Predictor |
| 11:24:49 | TCS | ENTRY(BUY) | 2276.70 | 0.00 | 1 | +0.00 | 100000.65 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:29:07
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:29:10 | BHARTIARTL | CLOSE(Partial Target Reached (50%)) | 1865.70 | 1866.00 | 1 | +0.30 | 100000.30 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:29:27
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:29:29 | BAJFINANCE | CLOSE(Partial Target Reached (50%)) | 930.45 | 930.50 | 1 | +0.05 | 100000.35 | AI XGBoost Predictor |
| 11:29:30 | TCS | CLOSE(Partial Target Reached (50%)) | 2276.70 | 2275.00 | 1 | -1.70 | 99998.65 | AI XGBoost Predictor |
| 11:30:00 | BAJFINANCE | ENTRY(BUY) | 930.50 | 0.00 | 1 | +0.00 | 99998.65 | AI XGBoost Predictor |
| 11:30:00 | BHARTIARTL | ENTRY(BUY) | 1866.00 | 0.00 | 1 | +0.00 | 99998.65 | AI XGBoost Predictor |
| 11:30:00 | TCS | ENTRY(BUY) | 2275.00 | 0.00 | 1 | +0.00 | 99998.65 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:40:01
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:40:03 | BAJFINANCE | CLOSE(Partial Target Reached (50%)) | 930.50 | 928.85 | 1 | -1.65 | 99998.35 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:40:35
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:40:37 | BHARTIARTL | CLOSE(Partial Target Reached (50%)) | 1866.00 | 1862.90 | 1 | -3.10 | 99995.25 | AI XGBoost Predictor |
| 11:40:37 | TCS | CLOSE(Partial Target Reached (50%)) | 2275.00 | 2273.40 | 1 | -1.60 | 99993.65 | AI XGBoost Predictor |
| 11:41:16 | BHARTIARTL | ENTRY(BUY) | 1862.90 | 0.00 | 1 | +0.00 | 99993.65 | AI XGBoost Predictor |
| 11:41:16 | BAJFINANCE | ENTRY(BUY) | 928.85 | 0.00 | 1 | +0.00 | 99993.65 | AI XGBoost Predictor |
| 11:42:22 | TCS | ENTRY(BUY) | 2273.40 | 0.00 | 1 | +0.00 | 99993.65 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:43:59
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:44:02 | BHARTIARTL | CLOSE(Partial Target Reached (50%)) | 1862.90 | 1864.20 | 1 | +1.30 | 100001.30 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:44:17
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:44:20 | BAJFINANCE | CLOSE(Partial Target Reached (50%)) | 928.85 | 930.00 | 1 | +1.15 | 100002.45 | AI XGBoost Predictor |
| 11:44:22 | TCS | CLOSE(Partial Target Reached (50%)) | 2273.40 | 2275.50 | 1 | +2.10 | 100004.55 | AI XGBoost Predictor |
| 11:44:59 | BHARTIARTL | ENTRY(BUY) | 1864.20 | 0.00 | 1 | +0.00 | 100004.55 | AI XGBoost Predictor |
| 11:46:22 | TCS | ENTRY(BUY) | 2275.50 | 0.00 | 1 | +0.00 | 100004.55 | AI XGBoost Predictor |
| 11:47:12 | BAJFINANCE | ENTRY(BUY) | 930.00 | 0.00 | 1 | +0.00 | 100004.55 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 11:56:45
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 11:57:15 | BHARTIARTL | ENTRY(BUY) | 1861.60 | 0.00 | 1 | +0.00 | 100000.00 | AI XGBoost Predictor |
| 11:57:15 | BAJFINANCE | ENTRY(BUY) | 929.50 | 0.00 | 1 | +0.00 | 100000.00 | AI XGBoost Predictor |
| 11:59:33 | SENSEX | ENTRY(BUY) | 76116.28 | 0.00 | 1 | +0.00 | 100000.00 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 12:50:48
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 12:54:31 | SENSEX | CLOSE(Partial Target Reached (50%)) | 76116.28 | 76047.82 | 1 | -68.46 | 99931.54 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 12:56:00
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 12:58:35 | SENSEX | ENTRY(BUY) | 76046.73 | 0.00 | 1 | +0.00 | 99931.54 | AI XGBoost Predictor |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 13:44:55
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 13:52:51
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 14:00:29 | KOTAKBANK | ENTRY(BUY) | 388.95 | 0.00 | 1 | +0.00 | 100000.00 | Multi-Strategy |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 14:14:26
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 14:29:49 | BHARTIARTL | ENTRY(BUY) | 1853.00 | 0.00 | 1 | +0.00 | 100000.00 | Multi-Strategy |
| 14:30:26 | BAJFINANCE | ENTRY(BUY) | 930.60 | 0.00 | 1 | +0.00 | 100000.00 | Multi-Strategy |
| 15:15:20 | BHARTIARTL | CLOSE(Max Duration Exit (45min)) | 1853.00 | 1860.00 | 1 | +7.00 | 100007.00 | Multi-Strategy |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 15:16:00
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
| 15:16:02 | HINDUNILVR | ENTRY(SELL) | 2195.60 | 0.00 | 1 | +0.00 | 100007.00 | Multi-Strategy |
| 15:16:02 | BAJFINANCE | CLOSE(Max Duration Exit (45min)) | 930.60 | 928.75 | 1 | -1.85 | 100005.15 | Multi-Strategy |
| 15:29:43 | HINDUNILVR | CLOSE(Market Close Exit) | 2195.60 | 2197.00 | 1 | -1.40 | 100003.75 | Multi-Strategy |
# Trading Session Activity Log — 2026-05-27

**System:** Indian Auto Trader (DEMO Mode)
**Started:** 2026-05-27 16:49:53
**Mode:** DEMO (Mock Funds ₹1,00,000)

| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |
|------|--------|--------|-------|------|-----|-----|---------|----------|
