"""
Fix database schema to match what portfolio_analytics.py expects.
"""
import sqlite3
import os

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

DB_PATH = _get_db_path()

def fix_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Drop and recreate tables with correct column names
    cursor.executescript("""
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS trades;
        DROP TABLE IF EXISTS positions;
        DROP TABLE IF EXISTS portfolio_history;
        DROP TABLE IF EXISTS signals;
        DROP TABLE IF EXISTS ai_model_performance;

        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT,
            password_hash TEXT,
            balance REAL DEFAULT 100000.0,
            plan_type TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL,
            exit_price REAL,
            quantity REAL DEFAULT 1,
            profit_loss REAL DEFAULT 0,
            status TEXT DEFAULT 'OPEN',
            entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            exit_time TIMESTAMP,
            strategy TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL,
            current_price REAL,
            quantity REAL DEFAULT 1,
            unrealized_pnl REAL DEFAULT 0,
            status TEXT DEFAULT 'OPEN',
            entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE portfolio_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            portfolio_value REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            confidence REAL,
            source TEXT DEFAULT 'ai',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE ai_model_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_version TEXT,
            accuracy REAL,
            training_samples INTEGER,
            validation_samples INTEGER,
            trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            feature_importance TEXT
        );
    """)

    # Insert default admin user with balance
    cursor.execute(
        "INSERT INTO users (username, email, balance, plan_type) VALUES (?, ?, ?, ?)",
        ("admin", "admin@tradingplatform.local", 100000.0, "pro")
    )

    conn.commit()
    conn.close()
    print("[OK] Database schema fixed with correct column names")

if __name__ == "__main__":
    fix_schema()
