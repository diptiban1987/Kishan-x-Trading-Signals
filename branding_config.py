import os
import json
import sqlite3
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_BRANDING = {
    "platform_name": "Trading Signals Pro",
    "short_name": "TSP",
    "platform_logo": "images/logo.png",
    "favicon": "favicon.ico",
    "support_email": "support@tradingsignalspro.com",
    "support_phone": "+1-800-TRADE",
    "company_name": "Trading Signals Pro Inc.",
    "company_address": "123 Trading Street, Financial District, NY 10005",
    "footer_text": "Trade responsibly. Trading involves substantial risk of loss.",
    "copyright_text": "All rights reserved.",
    "terms_url": "/terms",
    "privacy_url": "/legal",
    "risk_disclosure_url": "/legal#risk-disclosure",
    "refund_policy_url": "/legal#refund-policy",
    "primary_color": "#00C2FF",
    "secondary_color": "#111827",
    "accent_color": "#00E676",
    "dark_mode_default": True,
    "light_mode_support": False,
    "default_currency": "USD",
    "timezone": "UTC",
    "notification_sender_name": "Trading Signals Pro",
    "notification_email": "notifications@tradingsignalspro.com",
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_username": "",
    "smtp_password": "",
    "smtp_use_tls": True
}


class BrandingConfig:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')
        self._cache = {}
        self._init_table()

    def _init_table(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            for key, value in DEFAULT_BRANDING.items():
                cursor.execute('''
                    INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)
                ''', (key, json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error initializing branding table: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._cache:
            return self._cache[key]
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM app_settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            conn.close()
            if row:
                val = row[0]
                if val in ('True', 'False'):
                    val = val == 'True'
                else:
                    try:
                        val = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
                self._cache[key] = val
                return val
        except Exception as e:
            logger.error(f"Error reading branding setting {key}: {e}")
        return default if default is not None else DEFAULT_BRANDING.get(key)

    def set(self, key: str, value: Any):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            str_val = json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)
            cursor.execute('''
                INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, str_val))
            conn.commit()
            conn.close()
            self._cache[key] = value
        except Exception as e:
            logger.error(f"Error writing branding setting {key}: {e}")

    def get_all(self) -> dict:
        settings = {}
        for key in DEFAULT_BRANDING:
            settings[key] = self.get(key)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT key, value FROM app_settings')
            for key, val in cursor.fetchall():
                if key not in DEFAULT_BRANDING:
                    if val in ('True', 'False'):
                        val = val == 'True'
                    else:
                        try:
                            val = json.loads(val)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    settings[key] = val
            conn.close()
        except Exception as e:
            logger.error(f"Error reading all settings: {e}")
        return settings

    def to_dict(self) -> dict:
        return self.get_all()

    def clear_cache(self):
        self._cache = {}


branding = BrandingConfig()


def get_platform_setting(key: str, default: Any = None) -> Any:
    return branding.get(key, default)
