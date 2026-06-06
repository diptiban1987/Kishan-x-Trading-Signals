import os
import logging
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()

logger = logging.getLogger(__name__)


def is_render():
    return os.environ.get('RENDER') == '1'


def get_mysql_config():
    if is_render():
        return {
            'host': os.environ.get('MYSQL_HOST'),
            'port': int(os.environ.get('MYSQL_PORT', 3306)),
            'user': os.environ.get('MYSQL_USER', 'root'),
            'password': os.environ.get('MYSQL_PASSWORD', ''),
            'database': os.environ.get('MYSQL_DATABASE', 'trading_platform'),
        }
    return {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', '3306')),
        'user': os.getenv('MYSQL_USER', 'root'),
        'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', 'trading_platform'),
    }


def get_db_connection(database=None):
    try:
        config = get_mysql_config()
        if database:
            config['database'] = database
        connection = mysql.connector.connect(**config)
        if connection.is_connected():
            logger.info(f"Connected to MySQL at {config['host']}:{config.get('port', 3306)}")
            return connection
    except Error as e:
        logger.warning(f"Error connecting to MySQL: {e}")
        return None

def create_database_if_not_exists():
    try:
        conn = get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        db_name = get_mysql_config()['database']
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute(f"USE `{db_name}`")
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Database '{db_name}' ready")
        return True
    except Error as e:
        logger.error(f"Error creating database: {e}")
        return False

def init_database():
    """Initialize the database with ALL required tables"""
    if not create_database_if_not_exists():
        return

    connection = get_db_connection()
    if connection is None:
        return

    try:
        cursor = connection.cursor()

        tables = [
            # Core tables
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                registered_at DATETIME NOT NULL,
                last_login DATETIME,
                balance DECIMAL(10,2) DEFAULT 10000.00,
                is_premium BOOLEAN DEFAULT 0,
                demo_end_time DATETIME
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                pair VARCHAR(50) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                confidence DECIMAL(5,2) NOT NULL,
                time DATETIME NOT NULL,
                created_at DATETIME NOT NULL,
                entry_price DECIMAL(10,2),
                stop_loss DECIMAL(10,2),
                take_profit DECIMAL(10,2),
                result INT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                symbol VARCHAR(50) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                entry_price DECIMAL(10,2) NOT NULL,
                exit_price DECIMAL(10,2),
                quantity DECIMAL(10,2) NOT NULL,
                status VARCHAR(20) NOT NULL,
                entry_time DATETIME NOT NULL,
                exit_time DATETIME,
                profit_loss DECIMAL(10,2),
                stop_loss DECIMAL(10,2),
                take_profit DECIMAL(10,2),
                FOREIGN KEY(user_id) REFERENCES users(id)
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS positions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                symbol VARCHAR(50) NOT NULL,
                quantity DECIMAL(10,2) NOT NULL,
                average_price DECIMAL(10,2) NOT NULL,
                last_updated DATETIME NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                UNIQUE(user_id, symbol)
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS market_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(50) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                volume DECIMAL(20,2),
                timestamp DATETIME NOT NULL,
                UNIQUE(symbol, timestamp)
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS risk_limits (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                max_position_size DECIMAL(5,2) DEFAULT 0.02,
                max_daily_loss DECIMAL(5,2) DEFAULT 0.05,
                max_drawdown DECIMAL(5,2) DEFAULT 0.15,
                stop_loss_pct DECIMAL(5,2) DEFAULT 0.02,
                take_profit_pct DECIMAL(5,2) DEFAULT 0.04,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS portfolio_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                portfolio_value DECIMAL(10,2) NOT NULL,
                timestamp DATETIME NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                symbol VARCHAR(50) NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                UNIQUE(user_id, symbol)
            ) ENGINE=InnoDB
            """,
            # Security tables
            """
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL,
                ip_address VARCHAR(45) NOT NULL,
                success BOOLEAN NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_agent TEXT
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                session_token VARCHAR(255) UNIQUE NOT NULL,
                ip_address VARCHAR(45) NOT NULL,
                user_agent TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS api_rate_limits (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ip_address VARCHAR(45) NOT NULL,
                endpoint VARCHAR(255) NOT NULL,
                request_count INT DEFAULT 1,
                window_start DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_request DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS security_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                event_type VARCHAR(100) NOT NULL,
                user_id INT,
                ip_address VARCHAR(45),
                details TEXT,
                severity VARCHAR(20) DEFAULT 'INFO',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
            """,
            """
            CREATE TABLE IF NOT EXISTS user_permissions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                permission VARCHAR(100) NOT NULL,
                granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                granted_by INT,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, permission)
            ) ENGINE=InnoDB
            """,
            # Notification tables
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                type VARCHAR(50) NOT NULL,
                priority VARCHAR(20) DEFAULT 'MEDIUM',
                title VARCHAR(255) NOT NULL,
                message TEXT,
                data JSON,
                is_read BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            ) ENGINE=InnoDB
            """,
            # Backup tables
            """
            CREATE TABLE IF NOT EXISTS backup_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                size_bytes BIGINT,
                type VARCHAR(50) NOT NULL,
                status VARCHAR(50) DEFAULT 'completed',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
            """,
            # App settings
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key VARCHAR(100) PRIMARY KEY,
                setting_value TEXT
            ) ENGINE=InnoDB
            """,
            # Active trades persistence
            """
            CREATE TABLE IF NOT EXISTS active_trades (
                trade_id VARCHAR(100) PRIMARY KEY,
                user_id INT NOT NULL,
                symbol VARCHAR(50) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                entry_price DECIMAL(10,2),
                quantity INT,
                entry_time DATETIME,
                strategy VARCHAR(100),
                confidence DECIMAL(5,2),
                partial_exit_done TINYINT(1) DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            ) ENGINE=InnoDB
            """,
            # Orders table
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                symbol VARCHAR(50) NOT NULL,
                order_type VARCHAR(20) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                quantity DECIMAL(10,2) NOT NULL,
                price DECIMAL(10,2),
                stop_price DECIMAL(10,2),
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at DATETIME NOT NULL,
                executed_at DATETIME,
                trade_id INT,
                reject_reason TEXT,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            ) ENGINE=InnoDB
            """,
            # Login history
            """
            CREATE TABLE IF NOT EXISTS login_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                ip_address VARCHAR(45),
                user_agent TEXT,
                success TINYINT(1) DEFAULT 1,
                method VARCHAR(20) DEFAULT 'password',
                timestamp DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            ) ENGINE=InnoDB
            """
        ]

        for table_sql in tables:
            cursor.execute(table_sql)

        migrations = [
            "ALTER TABLE users ADD COLUMN tutorial_completed TINYINT(1) DEFAULT 0",
            "ALTER TABLE users ADD COLUMN totp_secret VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN totp_enabled TINYINT(1) DEFAULT 0",
            "ALTER TABLE users ADD COLUMN recovery_codes TEXT",
            "ALTER TABLE active_trades ADD COLUMN partial_exit_done TINYINT(1) DEFAULT 0",
        ]
        for migration in migrations:
            try:
                cursor.execute(migration)
            except Error:
                pass

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_trades_user_exit ON trades(user_id, exit_time)",
            "CREATE INDEX IF NOT EXISTS idx_portfolio_user_time ON portfolio_history(user_id, timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_signals_user_time ON signals(user_id, time)",
            "CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders(user_id, created_at)",
        ]
        for idx_sql in indexes:
            try:
                cursor.execute(idx_sql)
            except Error:
                pass

        connection.commit()
        logger.info("All MySQL database tables created successfully")

    except Error as e:
        print(f"Error creating database tables: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            print("Database connection closed")

if __name__ == "__main__":
    init_database() 