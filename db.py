import os
import sqlite3
import logging
import threading
import re
from flask import g

logger = logging.getLogger(__name__)

_db_local = threading.local()


def is_render():
    return os.environ.get('RENDER') == '1'


def get_mysql_config():
    return {
        'host': os.environ.get('MYSQL_HOST', 'localhost'),
        'port': int(os.environ.get('MYSQL_PORT', 3306)),
        'user': os.environ.get('MYSQL_USER', 'root'),
        'password': os.environ.get('MYSQL_PASSWORD', ''),
        'database': os.environ.get('MYSQL_DATABASE', 'trading_platform'),
    }


def _try_mysql():
    try:
        import mysql.connector
        cfg = get_mysql_config()
        conn = mysql.connector.connect(**cfg)
        if conn.is_connected():
            logger.info(f"Connected to MySQL at {cfg['host']}:{cfg['port']}/{cfg['database']}")
            return conn
    except Exception as e:
        logger.info(f"MySQL not available ({e}), falling back to SQLite")
    return None


class CompatRow(dict):
    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            values = list(self.values())
            return values[key]
        return super().__getitem__(key)


class MySQLCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        mysql_sql = _translate_sql(sql)
        if params is None:
            self._cursor.execute(mysql_sql)
        elif isinstance(params, (tuple, list)):
            self._cursor.execute(mysql_sql, params)
        else:
            self._cursor.execute(mysql_sql, (params,))
        return self

    def executemany(self, sql, seq):
        mysql_sql = _translate_sql(sql)
        self._cursor.executemany(mysql_sql, seq)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        return CompatRow(row) if row else None

    def fetchall(self):
        return [CompatRow(r) for r in self._cursor.fetchall()]

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def close(self):
        self._cursor.close()

    def __iter__(self):
        for row in self._cursor:
            yield CompatRow(row)


class MySQLConnection:
    def __init__(self, mysql_conn):
        self._conn = mysql_conn

    def cursor(self):
        return MySQLCursor(self._conn.cursor(dictionary=True))

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)


class SQLiteRow:
    @staticmethod
    def factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d


class SQLiteConnection:
    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self._conn.row_factory = SQLiteRow.factory
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, sql, params=None):
        return self._conn.execute(sql, params)


SQLITE_FUNCTIONS = {
    r"DATE\('now',\s*'localtime'\)": "CURDATE()",
    r"datetime\('now',\s*'localtime'\)": "NOW()",
    r"datetime\('now'\)": "NOW()",
    r"strftime\('%s',\s*(\w+)\)": r"UNIX_TIMESTAMP(\1)",
    r"(\w+)\s+REAL": r"\1 DOUBLE",
    r"(\w+)\s+BOOLEAN": r"\1 TINYINT(1)",
    r"\b(?<![a-zA-Z_])REAL\b": "DOUBLE",
}

ON_CONFLICT_RE = re.compile(r"ON\s+CONFLICT\s*\(\s*(\w+)\s*\)\s*DO\s+UPDATE\s+SET\s+(.*)", re.IGNORECASE)


def _translate_sql(sql):
    if not sql:
        return sql
    mysql_sql = sql.replace('?', '%s')
    for pattern, replacement in SQLITE_FUNCTIONS.items():
        mysql_sql = re.sub(pattern, replacement, mysql_sql, flags=re.IGNORECASE)
    mysql_sql = ON_CONFLICT_RE.sub(r"ON DUPLICATE KEY UPDATE \2", mysql_sql)
    return mysql_sql


_db_type = None
_db_instance = None


def _detect_db():
    global _db_type
    if _db_type is not None:
        return _db_type
    mysql_conn = _try_mysql()
    if mysql_conn:
        mysql_conn.close()
        _db_type = 'mysql'
        logger.info("Database: MySQL (detected)")
    else:
        _db_type = 'sqlite'
        logger.info("Database: SQLite (fallback)")
    return _db_type


def _connect_db():
    global _db_instance
    db_type = _detect_db()
    if db_type == 'mysql':
        mysql_conn = _try_mysql()
        if mysql_conn:
            _db_instance = MySQLConnection(mysql_conn)
            return _db_instance
        _db_type = 'sqlite'
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')
    _db_instance = SQLiteConnection(db_path)
    return _db_instance


def get_db():
    try:
        if not hasattr(g, 'db'):
            g.db = _connect_db()
        return g.db
    except RuntimeError:
        return _connect_db()


def close_connection(exception=None):
    try:
        db = getattr(g, 'db', None)
        if db is not None:
            try:
                db.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
    except RuntimeError:
        pass


def get_db_for_thread():
    if not hasattr(_db_local, 'conn') or _db_local.conn is None:
        _db_local.conn = _connect_db()
    return _db_local.conn


def get_db_type():
    _detect_db()
    return _db_type


def is_mysql():
    return get_db_type() == 'mysql'


def init_db():
    if is_mysql():
        _init_mysql()
    else:
        _init_sqlite()


def _init_mysql():
    import database_config
    database_config.init_database()


def _init_sqlite():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                last_login TEXT,
                balance REAL DEFAULT 10000.00,
                is_premium INTEGER DEFAULT 0,
                demo_end_time TEXT
            );
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                pair TEXT NOT NULL,
                direction TEXT NOT NULL,
                confidence REAL NOT NULL,
                time TEXT NOT NULL,
                created_at TEXT NOT NULL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                result INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                quantity REAL NOT NULL,
                status TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                profit_loss REAL,
                stop_loss REAL,
                take_profit REAL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                average_price REAL NOT NULL,
                last_updated TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                UNIQUE(user_id, symbol)
            );
            CREATE TABLE IF NOT EXISTS portfolio_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                portfolio_value REAL NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                order_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL,
                stop_price REAL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                executed_at TEXT,
                trade_id INTEGER,
                reject_reason TEXT,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS active_trades (
                id TEXT PRIMARY KEY,
                symbol TEXT,
                type TEXT,
                entry_price REAL,
                quantity INTEGER,
                entry_time TEXT,
                user_id INTEGER,
                strategy TEXT,
                confidence REAL,
                stop_loss REAL,
                target_price REAL,
                partial_exit_done INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS login_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                success INTEGER DEFAULT 1,
                method TEXT DEFAULT 'password',
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        conn.commit()
        logger.info("SQLite database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating SQLite tables: {e}")
        raise
    finally:
        conn.close()
