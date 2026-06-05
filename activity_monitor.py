import os
import sys
import time
import json
import queue
import threading
import logging
import subprocess
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path
from collections import defaultdict, deque

MONITOR_DIR = Path(__file__).parent / "monitor"
LOG_RECORD = MONITOR_DIR / "activity_record.json"
SESSION_LOG = MONITOR_DIR / "session_summary.md"
INTERVAL_SYSTEM = 30
INTERVAL_DB = 15
INTERVAL_HTTP = 10
MAX_RECORDS_PER_TYPE = 5000
LOG_TAIL_LINES = 5

MONITOR_DIR.mkdir(parents=True, exist_ok=True)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class RollingStore:
    def __init__(self, maxlen=MAX_RECORDS_PER_TYPE):
        self.maxlen = maxlen
        self.data = defaultdict(lambda: deque(maxlen=maxlen))

    def add(self, category, record):
        record["_ts"] = datetime.now().isoformat()
        self.data[category].append(record)

    def get(self, category):
        return list(self.data.get(category, []))

    def all_categories(self):
        return dict(self.data)

    def summary(self, category):
        items = self.get(category)
        if not items:
            return "No records"
        return f"{len(items)} records from {items[0]['_ts']} to {items[-1]['_ts']}"

store = RollingStore()


def get_log_sources():
    base = Path(__file__).parent
    sources = {
        "server_error.log": base / "server_error.log",
        "server_stdout.log": base / "server_stdout.log",
        "server_stderr.log": base / "server_stderr.log",
        "trading_app.log": base / "trading_app.log",
        "app_debug_output.log": base / "app_debug_output.log",
        "debug_output.log": base / "debug_output.log",
    }
    logs_dir = base / "logs"
    if logs_dir.exists():
        for f in sorted(logs_dir.iterdir()):
            if f.suffix in (".log", ".md", ".json"):
                sources[f"logs/{f.name}"] = f
    trading_dir = base / "trading"
    if trading_dir.exists():
        for date_dir in sorted(trading_dir.iterdir()):
            if date_dir.is_dir():
                for sub_dir in date_dir.iterdir():
                    for f in sub_dir.iterdir() if sub_dir.is_dir() else [date_dir / sub_dir]:
                        if isinstance(f, Path) and f.is_file() and f.suffix in (".log", ".json", ".md"):
                            src_name = f"trading/{date_dir.name}/{sub_dir.name}/{f.name}" if sub_dir.is_dir() else f"trading/{date_dir.name}/{f.name}"
                            sources[src_name] = f
    return sources


def tail_log_files():
    positions = {}
    while True:
        try:
            sources = get_log_sources()
            for name, path in sources.items():
                if not path.exists():
                    continue
                try:
                    size = path.stat().st_size
                    prev_size, prev_pos = positions.get(name, (0, 0))
                    if size > prev_size:
                        with open(path, "r", encoding="utf-8", errors="replace") as fh:
                            fh.seek(prev_pos)
                            lines = fh.readlines()
                            for line in lines[-LOG_TAIL_LINES:]:
                                stripped = line.strip()
                                if stripped:
                                    store.add("log_lines", {
                                        "source": name,
                                        "content": stripped,
                                        "level": detect_level(stripped),
                                    })
                        positions[name] = (size, fh.tell() if size > prev_size else prev_pos)
                    elif size < prev_size:
                        positions[name] = (size, 0)
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(2)


def detect_level(line):
    upper = line.upper()
    if "ERROR" in upper or "CRITICAL" in upper or "TRACEBACK" in upper or "EXCEPTION" in upper:
        return "ERROR"
    if "WARNING" in upper or "WARN" in upper:
        return "WARNING"
    if "INFO" in upper:
        return "INFO"
    return "DEBUG"


def monitor_system():
    if not HAS_PSUTIL:
        while True:
            time.sleep(INTERVAL_SYSTEM)
        return
    process = psutil.Process()
    while True:
        try:
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(".")
            net = psutil.net_io_counters()
            proc_cpu = process.cpu_percent(interval=0)
            proc_mem = process.memory_info()
            threads = process.num_threads()
            store.add("system_metrics", {
                "cpu_percent": cpu,
                "memory_percent": mem.percent,
                "memory_used_mb": round(mem.used / 1024 / 1024, 1),
                "disk_percent": disk.percent,
                "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
                "net_sent_mb": round(net.bytes_sent / 1024 / 1024, 1),
                "net_recv_mb": round(net.bytes_recv / 1024 / 1024, 1),
                "proc_cpu_percent": proc_cpu,
                "proc_mem_mb": round(proc_mem.rss / 1024 / 1024, 1),
                "proc_threads": threads,
            })
            load_avg = getattr(psutil, "getloadavg", None)
            if load_avg:
                store.add("system_metrics_cpu_load", {
                    "1min": load_avg()[0],
                    "5min": load_avg()[1],
                    "15min": load_avg()[2],
                })
        except Exception as e:
            store.add("monitor_errors", {"context": "system_monitor", "error": str(e), "traceback": traceback.format_exc()})
        time.sleep(INTERVAL_SYSTEM)


def monitor_database():
    db_path = Path(__file__).parent / "trading.db"
    while True:
        try:
            if not db_path.exists():
                time.sleep(INTERVAL_DB)
                continue
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            tables_info = {}
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r["name"] for r in cursor.fetchall()]
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) as cnt FROM \"{table}\"")
                    count = cursor.fetchone()["cnt"]
                    cursor.execute(f"SELECT MAX(rowid) as mx FROM \"{table}\"")
                    max_id = cursor.fetchone()["mx"]
                    tables_info[table] = {"row_count": count, "max_rowid": max_id}
                except Exception:
                    pass
            latest = {}
            for tbl in ["trades", "signals", "orders", "notifications"]:
                if tbl in tables:
                    try:
                        cursor.execute(f"SELECT * FROM \"{tbl}\" ORDER BY rowid DESC LIMIT 5")
                        rows = [dict(r) for r in cursor.fetchall()]
                        latest[tbl] = rows
                    except Exception:
                        pass
            conn.close()
            store.add("database_state", {
                "tables": tables_info,
                "latest_records": latest,
            })
        except Exception as e:
            store.add("monitor_errors", {"context": "db_monitor", "error": str(e), "traceback": traceback.format_exc()})
        time.sleep(INTERVAL_DB)


def monitor_http_endpoints():
    if not HAS_REQUESTS:
        while True:
            time.sleep(INTERVAL_HTTP)
        return
    endpoints = [
        "/api/admin/system-status",
        "/api/admin/performance-metrics",
        "/api/admin/trading-params",
        "/api/admin/cache-stats",
        "/api/admin/rate-limit-stats",
        "/api/admin/security-stats",
        "/api/admin/notification-stats",
        "/api/admin/backup-stats",
        "/api/current_mode",
        "/api/market-status",
    ]
    while True:
        for ep in endpoints:
            try:
                resp = requests.get(f"http://127.0.0.1:4000{ep}", timeout=5)
                if resp.ok:
                    data = resp.json()
                    cat = ep.strip("/").replace("/", "_")
                    store.add(f"http_{cat}", {
                        "endpoint": ep,
                        "status": resp.status_code,
                        "data": data,
                    })
                else:
                    store.add("http_errors", {
                        "endpoint": ep,
                        "status": resp.status_code,
                        "text": resp.text[:500],
                    })
            except requests.ConnectionError:
                store.add("http_errors", {"endpoint": ep, "error": "Connection refused - app may be down"})
            except Exception as e:
                store.add("monitor_errors", {"context": f"http_{ep}", "error": str(e)})
            time.sleep(0.5)
        time.sleep(INTERVAL_HTTP)


def watch_log_dirs():
    base = Path(__file__).parent
    seen = set()
    while True:
        try:
            log_dir = base / "logs"
            if log_dir.exists():
                for f in log_dir.iterdir():
                    if f.suffix in (".log", ".md", ".json") and f.name not in seen:
                        seen.add(f.name)
                        store.add("new_log_files", {"name": f.name, "size": f.stat().st_size, "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()})
            trading_dir = base / "trading"
            if trading_dir.exists():
                for date_dir in sorted(trading_dir.iterdir()):
                    for sub_dir in date_dir.iterdir() if date_dir.is_dir() else [date_dir]:
                        for f in sub_dir.iterdir() if isinstance(sub_dir, Path) and sub_dir.is_dir() else [date_dir / sub_dir]:
                            if isinstance(f, Path) and f.is_file() and f.suffix in (".log", ".json", ".md"):
                                key = str(f.relative_to(base))
                                if key not in seen:
                                    seen.add(key)
                                    store.add("new_log_files", {"name": key, "size": f.stat().st_size, "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()})
        except Exception:
            pass
        time.sleep(30)


def monitor_angelone():
    base = Path(__file__).parent
    sys.path.insert(0, str(base))
    import importlib
    while True:
        try:
            mod = sys.modules.get("angel_one_api")
            if mod and hasattr(mod, "angel_api"):
                api = mod.angel_api
                state = {}
                if hasattr(api, "session"):
                    state["has_session"] = api.session is not None
                if hasattr(api, "is_connected"):
                    state["websocket_connected"] = api.is_connected
                if hasattr(api, "feed_token"):
                    state["feed_token"] = api.feed_token is not None
                if hasattr(api, "demo_mode"):
                    state["demo_mode"] = api.demo_mode
                store.add("angelone_status", state)
        except Exception as e:
            store.add("monitor_errors", {"context": "angelone_monitor", "error": str(e)})
        time.sleep(15)


def monitor_dhan():
    base = Path(__file__).parent
    sys.path.insert(0, str(base))
    while True:
        try:
            mod = sys.modules.get("dhan_api")
            if mod and hasattr(mod, "dhan_client"):
                client = mod.dhan_client
                state = {}
                if hasattr(client, "access_token"):
                    state["has_token"] = client.access_token is not None
                if hasattr(client, "token_expiry"):
                    state["token_expires_at"] = str(client.token_expiry) if client.token_expiry else None
                store.add("dhan_status", state)
        except Exception as e:
            store.add("monitor_errors", {"context": "dhan_monitor", "error": str(e)})
        time.sleep(15)


def monitor_trading_engines():
    base = Path(__file__).parent
    sys.path.insert(0, str(base))
    while True:
        try:
            mod = sys.modules.get("indian_trading_system")
            if mod:
                state = {}
                if hasattr(mod, "indian_trader"):
                    t = mod.indian_trader
                    for attr in ["running", "active_trades", "total_trades", "winning_trades", "losing_trades", "pnl", "last_signal_time"]:
                        if hasattr(t, attr):
                            state[attr] = str(getattr(t, attr))
                if hasattr(mod, "indian_auto_trader") and hasattr(mod.indian_auto_trader, "running"):
                    state["auto_trader_running"] = mod.indian_auto_trader.running
                store.add("indian_trading_status", state)
            mod2 = sys.modules.get("auto_trader")
            if mod2 and hasattr(mod2, "auto_trader_instance"):
                t = mod2.auto_trader_instance
                state2 = {}
                for attr in ["running", "active_trades", "total_trades", "winning_trades", "losing_trades", "pnl"]:
                    if hasattr(t, attr):
                        state2[attr] = str(getattr(t, attr))
                store.add("us_trading_status", state2)
        except Exception as e:
            store.add("monitor_errors", {"context": "trading_engine_monitor", "error": str(e)})
        time.sleep(15)


def monitor_process_threads():
    while True:
        try:
            proc = psutil.Process()
            threads_info = []
            for t in proc.threads() if HAS_PSUTIL else []:
                threads_info.append({"id": t.id, "user_time": t.user_time, "system_time": t.system_time})
            store.add("process_threads", {
                "pid": proc.pid,
                "thread_count": len(threads_info),
                "threads": threads_info[:20],
            })
        except Exception as e:
            store.add("monitor_errors", {"context": "thread_monitor", "error": str(e)})
        time.sleep(60)


def check_db_integrity():
    db_path = Path(__file__).parent / "trading.db"
    while True:
        try:
            if not db_path.exists():
                time.sleep(120)
                continue
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_count")
            pages = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            cursor.execute("PRAGMA freelist_count")
            freelist = cursor.fetchone()[0]
            conn.close()
            store.add("db_integrity", {
                "integrity_check": result,
                "page_count": pages,
                "page_size": page_size,
                "freelist_pages": freelist,
                "size_mb": round(db_path.stat().st_size / 1024 / 1024, 2) if db_path.exists() else 0,
            })
        except Exception as e:
            store.add("monitor_errors", {"context": "db_integrity", "error": str(e)})
        time.sleep(120)


def find_error_patterns():
    while True:
        try:
            error_lines = [r for r in store.get("log_lines") if r.get("level") == "ERROR"]
            recent_errors = error_lines[-100:]
            patterns = defaultdict(int)
            for r in recent_errors:
                content = r.get("content", "")
                for keyword in ["Timeout", "ConnectionError", "Rate limit", "API", "database", "auth", "permission", "denied", "failed", "unreachable", "exception", "traceback"]:
                    if keyword.lower() in content.lower():
                        patterns[keyword] += 1
            if patterns:
                store.add("error_patterns", {k: int(v) for k, v in patterns.items()})
        except Exception as e:
            store.add("monitor_errors", {"context": "error_patterns", "error": str(e)})
        time.sleep(60)


def write_records():
    while True:
        try:
            flush_start = time.time()
            all_data = {}
            for cat, records in store.data.items():
                all_data[cat] = list(records)
            record = {
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": time.time() - _start_time if _start_time else 0,
                "categories": {cat: len(v) for cat, v in all_data.items()},
                "data": all_data,
            }
            tmp = LOG_RECORD.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, default=str, ensure_ascii=False)
            tmp.replace(LOG_RECORD)
            write_session_summary(all_data)
            if time.time() - flush_start > 10:
                store.add("monitor_errors", {"context": "write_records_slow", "seconds": round(time.time() - flush_start, 1)})
        except Exception as e:
            store.add("monitor_errors", {"context": "write_records", "error": str(e), "traceback": traceback.format_exc()})
        time.sleep(10)


def write_session_summary(all_data):
    lines = []
    lines.append(f"# Activity Monitor Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"")
    lines.append(f"**Uptime:** {_start_time_formatted if _start_time_formatted else 'N/A'}")
    lines.append(f"")
    lines.append(f"## Category Overview")
    lines.append(f"")
    lines.append(f"| Category | Record Count |")
    lines.append(f"|----------|-------------|")
    for cat in sorted(all_data.keys()):
        lines.append(f"| {cat} | {len(all_data[cat])} |")
    lines.append(f"")
    if all_data.get("system_metrics"):
        last = all_data["system_metrics"][-1]
        lines.append(f"## Latest System Metrics")
        lines.append(f"")
        lines.append(f"- CPU: {last.get('cpu_percent', '?')}%")
        lines.append(f"- Memory: {last.get('memory_percent', '?')}%")
        lines.append(f"- Disk: {last.get('disk_percent', '?')}%")
        lines.append(f"- Process Memory: {last.get('proc_mem_mb', '?')} MB")
        lines.append(f"- Threads: {last.get('proc_threads', '?')}")
        lines.append(f"")
    if all_data.get("http_errors"):
        lines.append(f"## HTTP Errors")
        lines.append(f"")
        for r in all_data["http_errors"][-10:]:
            lines.append(f"- {r.get('endpoint')}: {r.get('status', r.get('error', '?'))}")
        lines.append(f"")
    if all_data.get("monitor_errors"):
        lines.append(f"## Monitor Internal Errors")
        lines.append(f"")
        for r in all_data["monitor_errors"][-20:]:
            lines.append(f"- [{r.get('context')}] {r.get('error')}")
        lines.append(f"")
    if all_data.get("angelone_status"):
        last = all_data["angelone_status"][-1]
        lines.append(f"## Angel One Status")
        lines.append(f"")
        for k, v in last.items():
            lines.append(f"- {k}: {v}")
        lines.append(f"")
    if all_data.get("dhan_status"):
        last = all_data["dhan_status"][-1]
        lines.append(f"## Dhan Status")
        lines.append(f"")
        for k, v in last.items():
            lines.append(f"- {k}: {v}")
        lines.append(f"")
    if all_data.get("database_state"):
        last = all_data["database_state"][-1]
        lines.append(f"## Database State")
        lines.append(f"")
        if "tables" in last:
            lines.append(f"### Table Row Counts")
            for tbl, info in sorted(last["tables"].items()):
                lines.append(f"- {tbl}: {info.get('row_count', '?')} rows")
        if "latest_records" in last:
            for tbl, rows in last["latest_records"].items():
                if rows:
                    lines.append(f"### Latest {tbl}")
                    for row in rows:
                        lines.append(f"- {json.dumps(row, default=str)}")
        lines.append(f"")
    if all_data.get("error_patterns"):
        lines.append(f"## Error Patterns (last 60s)")
        lines.append(f"")
        for pattern, count in sorted(all_data["error_patterns"][-1].items(), key=lambda x: -int(x[1]) if isinstance(x[1], (int, float)) else 0):
            lines.append(f"- {pattern}: {count} occurrences")
        lines.append(f"")
    if all_data.get("log_lines"):
        recent_logs = [r for r in all_data["log_lines"] if r.get("level") in ("ERROR", "WARNING")][-30:]
        if recent_logs:
            lines.append(f"## Recent Errors/Warnings")
            lines.append(f"")
            for r in recent_logs:
                lines.append(f"- [{r['level']}] [{r['source']}] {r['content'][:200]}")
            lines.append(f"")

    content = "\n".join(lines)
    with open(SESSION_LOG, "w", encoding="utf-8") as f:
        f.write(content)


def cleanup_old_records():
    while True:
        try:
            max_age = 86400 * 7
            now = time.time()
            if LOG_RECORD.exists():
                age = now - LOG_RECORD.stat().st_mtime
                if age > max_age:
                    backup = LOG_RECORD.with_suffix(f".{datetime.fromtimestamp(LOG_RECORD.stat().st_mtime).strftime('%Y%m%d')}.json")
                    LOG_RECORD.rename(backup)
        except Exception:
            pass
        time.sleep(3600)


_start_time = time.time()
_start_time_formatted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

threads = [
    ("log_tailer", tail_log_files),
    ("system_monitor", monitor_system, True),
    ("db_monitor", monitor_database),
    ("http_monitor", monitor_http_endpoints, True),
    ("log_watcher", watch_log_dirs),
    ("angelone_monitor", monitor_angelone),
    ("dhan_monitor", monitor_dhan),
    ("trading_monitor", monitor_trading_engines),
    ("thread_monitor", monitor_process_threads, True),
    ("db_integrity", check_db_integrity),
    ("error_patterns", find_error_patterns),
    ("writer", write_records),
    ("cleanup", cleanup_old_records),
]


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - monitor - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(MONITOR_DIR / "monitor.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Activity Monitor started")
    logger.info(f"Monitor directory: {MONITOR_DIR}")
    logger.info(f"Output file: {LOG_RECORD}")
    logger.info(f"Summary file: {SESSION_LOG}")
    if not HAS_PSUTIL:
        logger.warning("psutil not installed - system/process monitoring disabled")
    if not HAS_REQUESTS:
        logger.warning("requests not installed - HTTP endpoint monitoring disabled")
    running = []
    for name, func, *rest in threads:
        daemon = rest[0] if rest else False
        t = threading.Thread(target=func, name=name, daemon=daemon)
        t.start()
        running.append((name, t))
        logger.info(f"Started monitor thread: {name}")
    logger.info(f"All {len(running)} monitor threads started")
    try:
        while True:
            time.sleep(1)
            for name, t in running:
                if not t.is_alive():
                    logger.error(f"Monitor thread {name} died! Restarting...")
                    new_t = threading.Thread(target=[f for n,f,*r in threads if n==name][0], name=name, daemon=True)
                    new_t.start()
                    store.add("monitor_errors", {"context": "thread_restart", "thread": name})
    except KeyboardInterrupt:
        logger.info("Monitor shutting down...")
        sys.exit(0)


if __name__ == "__main__":
    main()
