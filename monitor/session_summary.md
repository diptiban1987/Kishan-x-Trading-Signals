# Activity Monitor Summary - 2026-06-04 11:51:59

**Uptime:** 2026-06-04 09:44:05

## Category Overview

| Category | Record Count |
|----------|-------------|
| database_state | 512 |
| db_integrity | 64 |
| error_patterns | 127 |
| http_api_admin_backup-stats | 496 |
| http_api_admin_cache-stats | 494 |
| http_api_admin_notification-stats | 496 |
| http_api_admin_performance-metrics | 494 |
| http_api_admin_rate-limit-stats | 495 |
| http_api_admin_security-stats | 495 |
| http_api_admin_system-status | 495 |
| http_api_admin_trading-params | 494 |
| http_api_current_mode | 496 |
| http_api_market-status | 496 |
| http_errors | 40 |
| log_lines | 5000 |
| new_log_files | 15 |
| process_threads | 128 |
| system_metrics | 248 |
| system_metrics_cpu_load | 248 |

## Latest System Metrics

- CPU: 1.5%
- Memory: 62.5%
- Disk: 91.8%
- Process Memory: 191.6 MB
- Threads: 18

## HTTP Errors

- /api/admin/performance-metrics: Connection refused - app may be down
- /api/admin/trading-params: Connection refused - app may be down
- /api/admin/cache-stats: Connection refused - app may be down
- /api/admin/rate-limit-stats: Connection refused - app may be down
- /api/admin/security-stats: Connection refused - app may be down
- /api/admin/notification-stats: Connection refused - app may be down
- /api/admin/backup-stats: Connection refused - app may be down
- /api/current_mode: Connection refused - app may be down
- /api/market-status: Connection refused - app may be down
- /api/admin/system-status: Connection refused - app may be down

## Database State

### Table Row Counts
- active_trades: 1 rows
- api_rate_limits: 0 rows
- app_settings: 31 rows
- backup_history: 42 rows
- backup_settings: 5 rows
- feature_usage: 0 rows
- login_attempts: 0 rows
- login_history: 96 rows
- notification_templates: 660 rows
- notifications: 0 rows
- orders: 0 rows
- payments: 0 rows
- portfolio_history: 41 rows
- positions: 0 rows
- referrals: 0 rows
- security_events: 0 rows
- signals: 0 rows
- sqlite_sequence: 11 rows
- subscriptions: 1 rows
- trades: 39 rows
- user_notification_preferences: 0 rows
- user_permissions: 0 rows
- user_sessions: 0 rows
- users: 4 rows
### Latest trades
- {"id": 167, "user_id": 3, "symbol": "HINDUNILVR", "direction": "SELL", "entry_price": 2107.10009765625, "exit_price": 2110.470068024208, "quantity": 48.0, "status": "CLOSED", "entry_time": "2026-06-04 11:01:41", "exit_time": "2026-06-04 11:16:46", "profit_loss": -161.75857766198897, "stop_loss": 2117.635598144531, "take_profit": 2090.243296875}
- {"id": 166, "user_id": 3, "symbol": "ICICIBANK", "direction": "SELL", "entry_price": 1251.300048828125, "exit_price": 1251.5674585661723, "quantity": 84.0, "status": "CLOSED", "entry_time": "2026-06-04 10:44:36", "exit_time": "2026-06-04 11:00:03", "profit_loss": -22.4624179959701, "stop_loss": 1257.5565490722654, "take_profit": 1241.2896484375}
- {"id": 165, "user_id": 3, "symbol": "HINDUNILVR", "direction": "BUY", "entry_price": 2103.7, "exit_price": 2105.2762446777087, "quantity": 44.0, "status": "CLOSED", "entry_time": "2026-06-04 09:56:48", "exit_time": "2026-06-04 10:43:20", "profit_loss": 69.35476581919283, "stop_loss": 2093.1814999999997, "take_profit": 2120.5296}
- {"id": 164, "user_id": 3, "symbol": "KOTAKBANK", "direction": "BUY", "entry_price": 380.70001220703125, "exit_price": 380.6798142297553, "quantity": 157.0, "status": "CLOSED", "entry_time": "2026-06-04 09:47:32", "exit_time": "2026-06-04 10:25:02", "profit_loss": -3.1710824323205884, "stop_loss": 380.70001220703125, "take_profit": 383.7456123046875}
- {"id": 163, "user_id": 3, "symbol": "BANKNIFTY", "direction": "BUY", "entry_price": 53958.3984375, "exit_price": 53935.94533210965, "quantity": 1.0, "status": "CLOSED", "entry_time": "2026-06-04 09:33:00", "exit_time": "2026-06-04 09:58:24", "profit_loss": -22.453105390348355, "stop_loss": 53688.6064453125, "take_profit": 54390.065625}

## Error Patterns (last 60s)

- exception: 17 occurrences
- _ts: 2026-06-04T11:51:05.464980 occurrences

## Recent Errors/Warnings

- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for IWM
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for DIA
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for VTI
- [ERROR] [trading/2026-06-01/indian_only.log] jinja2.exceptions.UndefinedError: 'get_setting' is undefined
- [ERROR] [trading/2026-06-03/indian_only.log] return codecs.charmap_encode(input,self.errors,encoding_table)[0]
- [ERROR] [trading/2026-06-03/indian_only.log] UnicodeEncodeError: 'charmap' codec can't encode character '\u2705' in position 0: character maps to <undefined>
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for IWM
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for DIA
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for VTI
- [ERROR] [trading/2026-06-01/indian_only.log] jinja2.exceptions.UndefinedError: 'get_setting' is undefined
- [ERROR] [trading/2026-06-03/indian_only.log] return codecs.charmap_encode(input,self.errors,encoding_table)[0]
- [ERROR] [trading/2026-06-03/indian_only.log] UnicodeEncodeError: 'charmap' codec can't encode character '\u2705' in position 0: character maps to <undefined>
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for IWM
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for DIA
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for VTI
- [ERROR] [trading/2026-06-01/indian_only.log] jinja2.exceptions.UndefinedError: 'get_setting' is undefined
- [ERROR] [trading/2026-06-03/indian_only.log] return codecs.charmap_encode(input,self.errors,encoding_table)[0]
- [ERROR] [trading/2026-06-03/indian_only.log] UnicodeEncodeError: 'charmap' codec can't encode character '\u2705' in position 0: character maps to <undefined>
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for IWM
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for DIA
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for VTI
- [ERROR] [trading/2026-06-01/indian_only.log] jinja2.exceptions.UndefinedError: 'get_setting' is undefined
- [ERROR] [trading/2026-06-03/indian_only.log] return codecs.charmap_encode(input,self.errors,encoding_table)[0]
- [ERROR] [trading/2026-06-03/indian_only.log] UnicodeEncodeError: 'charmap' codec can't encode character '\u2705' in position 0: character maps to <undefined>
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for IWM
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for DIA
- [ERROR] [server_stderr.log] ERROR:trading_system:No data available for VTI
- [ERROR] [trading/2026-06-01/indian_only.log] jinja2.exceptions.UndefinedError: 'get_setting' is undefined
- [ERROR] [trading/2026-06-03/indian_only.log] return codecs.charmap_encode(input,self.errors,encoding_table)[0]
- [ERROR] [trading/2026-06-03/indian_only.log] UnicodeEncodeError: 'charmap' codec can't encode character '\u2705' in position 0: character maps to <undefined>
