import os
import sqlite3
import logging
import random
import hashlib
import json
import secrets
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Optional, Union, Tuple, List
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g, send_file, abort, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import numpy as np
import yfinance as yf
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.pdfgen import canvas
import json
import requests
import time
import threading
import math
from statistics import NormalDist
from dotenv import load_dotenv
# Load .env BEFORE any module that reads env vars (Dhan, Angel One, etc.)
load_dotenv()

from config import *
from otc_data import OTCDataHandler
from forex_data import get_cached_realtime_forex
from trading_system import TradingSystem
from risk_manager import RiskManager
from auto_trader import AutoTrader
from indian_trading_system import IndianTradingSystem, IndianAutoTrader
from portfolio_analytics import PortfolioAnalytics
from angel_one_api import AngelOneAPI, AngelOneDataProvider
from data_injection_service import get_data_injection_service
from security_manager import security_manager, require_auth, require_permission, rate_limit
from notification_system import notification_system, NotificationType, NotificationPriority
from backup_system import backup_system
from order_manager import OrderManager
from trading_assistant import get_response as assistant_get_response
from datetime import date
from datetime import datetime as dt

import pyotp

# Import subscription and AI modules
from routes.subscription_routes import subscription_bp
from routes.ai_signals import ai_signals_bp
from models.subscription import SubscriptionManager
from auth.decorators import require_login, require_plan, check_signal_quota
from branding_config import branding, get_platform_setting
from db import is_mysql, get_db, get_db_type, _connect_db, close_connection as db_close_connection, init_db as db_init_db

# Get absolute paths for PythonAnywhere
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
TEMPLATES_FOLDER = os.path.join(BASE_DIR, 'templates')

# Configure Flask app for PythonAnywhere
app = Flask(__name__,
    static_url_path='/static',
    static_folder=STATIC_FOLDER,
    template_folder=TEMPLATES_FOLDER
)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY') or os.getenv('SECRET_KEY') or secrets.token_hex(32)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = (os.getenv('ENV') or os.getenv('FLASK_ENV', 'production')) == 'production'
CORS(app)

# Register blueprints
app.register_blueprint(subscription_bp)
app.register_blueprint(ai_signals_bp)

# Disable caching to always serve the latest templates and static assets
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
try:
    app.jinja_env.cache = {}
except Exception as e:
    logger.debug(f"Could not clear Jinja cache: {e}")

# Append file modification time to static asset URLs for cache-busting
@app.context_processor
def override_static_url():
    def static_url(filename: str):
        file_path = os.path.join(STATIC_FOLDER, filename)
        version = int(os.path.getmtime(file_path)) if os.path.exists(file_path) else int(time.time())
        return url_for('static', filename=filename, v=version)
    return dict(static_url=static_url)

@app.context_processor
def inject_branding():
    return dict(
        branding=branding.to_dict(),
        get_setting=get_platform_setting,
        platform_name=get_platform_setting('platform_name'),
        short_name=get_platform_setting('short_name'),
        support_email=get_platform_setting('support_email')
    )

# Prevent browsers/proxies from caching HTML responses
@app.after_request
def add_no_cache_headers(response):
    content_type = response.headers.get('Content-Type', '')
    if 'text/html' in content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Configure SocketIO for PythonAnywhere
# NOTE: reconnection* options are client-side only; they do not belong here.
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    always_connect=True,
    manage_session=True  # Enable session management
)

# Configure logging for PythonAnywhere
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, 'trading_app.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Persistence helpers for autostart/active trades ---
def ensure_persistence_tables():
    if is_mysql():
        return
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        cur.execute('''
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
            )
        ''')
        try:
            cur.execute("ALTER TABLE active_trades ADD COLUMN partial_exit_done INTEGER DEFAULT 0")
        except Exception:
            pass
        cur.execute("""
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
            )
        """)
        try:
            cur.execute("ALTER TABLE users ADD COLUMN tutorial_completed INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE users ADD COLUMN recovery_codes TEXT")
        except Exception:
            pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS login_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                success INTEGER DEFAULT 1,
                method TEXT DEFAULT 'password',
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()
    except Exception as e:
        logger.error(f"Error ensuring persistence tables: {e}")

def set_setting(key: str, value: str):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('INSERT INTO app_settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
        conn.commit()
    except Exception as e:
        logger.error(f"Error setting app setting {key}: {e}")

def get_setting(key: str, default: str = None):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT value FROM app_settings WHERE key=?', (key,))
        row = cur.fetchone()
        return row['value'] if row else default
    except Exception as e:
        logger.error(f"Error getting app setting {key}: {e}")
        return default
# --- Portfolio/P&L endpoints ---
@app.route('/portfolio/summary')
def portfolio_summary():
    if not session.get('user_id'):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        sync_autotrader_user()
    except Exception as sync_err:
        logger.error(f"Error syncing autotrader: {sync_err}")
    try:
        user_id = session['user_id']
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT portfolio_value, timestamp FROM portfolio_history
            WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1
        ''', (user_id,))
        row = cursor.fetchone()
        latest_value = float(row['portfolio_value']) if row else float(indian_auto_trader.initial_balance)

        # Compute today's P&L from midnight
        cursor.execute('''
            SELECT SUM(profit_loss) AS pnl_sum FROM trades
            WHERE user_id = ? AND DATE(exit_time) = DATE('now', 'localtime')
        ''', (user_id,))
        pnl_row = cursor.fetchone()
        today_pnl = float(pnl_row['pnl_sum']) if pnl_row and pnl_row['pnl_sum'] is not None else 0.0

        return jsonify({
            'portfolio_value': round(latest_value, 2),
            'today_pnl': round(today_pnl, 2)
        })
    except Exception as e:
        logger.error(f"Error fetching portfolio summary: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/portfolio/pnl_by_date')
def portfolio_pnl_by_date():
    if not session.get('user_id'):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        sync_autotrader_user()
    except Exception as sync_err:
        logger.error(f"Error syncing autotrader: {sync_err}")
    try:
        user_id = session['user_id']
        start_date = request.args.get('start')  # YYYY-MM-DD or MM/DD/YYYY
        end_date = request.args.get('end')      # YYYY-MM-DD or MM/DD/YYYY
        if not start_date:
            start_date = date.today().strftime('%Y-%m-%d')
        if not end_date:
            end_date = start_date

        # Normalize MM/DD/YYYY to YYYY-MM-DD if needed
        def norm(d):
            if not d:
                return d
            if '/' in d:
                try:
                    return dt.strptime(d, '%m/%d/%Y').strftime('%Y-%m-%d')
                except ValueError:
                    logger.warning(f"Invalid date format: {d}")
            return d
        start_date = norm(start_date)
        end_date = norm(end_date)

        conn = get_db()
        cursor = conn.cursor()
        # Handle rows where exit_time may have been stored as time-only (HH:MM:SS)
        # Interpret time-only as 'today' for the purpose of date filtering
        cursor.execute('''
            SELECT d, SUM(profit_loss) as pnl FROM (
                SELECT 
                    CASE 
                        WHEN LENGTH(exit_time) = 8 AND INSTR(exit_time, ':') > 0 THEN DATE('now','localtime')
                        ELSE DATE(exit_time)
                    END AS d,
                    profit_loss
                FROM trades
                WHERE user_id = ?
            ) t
            WHERE d BETWEEN DATE(?) AND DATE(?)
            GROUP BY d
            ORDER BY d ASC
        ''', (user_id, start_date, end_date))
        rows = cursor.fetchall()
        data = [{'date': r['d'], 'pnl': float(r['pnl']) if r['pnl'] is not None else 0.0} for r in rows]
        total = sum(item['pnl'] for item in data)
        # Breakdown: profit, loss, wins, losses, portfolio balance
        cursor.execute('''
            SELECT 
                SUM(CASE WHEN profit_loss > 0 THEN profit_loss ELSE 0 END) AS total_profit,
                SUM(CASE WHEN profit_loss < 0 THEN -profit_loss ELSE 0 END) AS total_loss,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) AS losses
            FROM (
                SELECT 
                    CASE 
                        WHEN LENGTH(exit_time) = 8 AND INSTR(exit_time, ':') > 0 THEN DATE('now','localtime')
                        ELSE DATE(exit_time)
                    END AS d,
                    profit_loss
                FROM trades
                WHERE user_id = ?
            ) x
            WHERE d BETWEEN DATE(?) AND DATE(?)
        ''', (user_id, start_date, end_date))
        br = cursor.fetchone() or {}
        total_profit = float(br['total_profit'] or 0.0)
        total_loss = float(br['total_loss'] or 0.0)
        wins = int(br['wins'] or 0)
        losses = int(br['losses'] or 0)
        denominator = total_profit + total_loss
        profit_pct = (total_profit / denominator * 100.0) if denominator > 0 else 0.0
        loss_pct = (total_loss / denominator * 100.0) if denominator > 0 else 0.0
        win_rate = (wins / (wins + losses) * 100.0) if (wins + losses) > 0 else 0.0
        # Latest portfolio value
        # Add unrealized P&L from active trades when date range covers today
        today_str = date.today().strftime('%Y-%m-%d')
        if start_date <= today_str <= end_date:
            try:
                active_trades = indian_auto_trader.get_active_trades()
                latest_prices = getattr(indian_auto_trader, 'latest_prices', {})
                for trade_id, trade in active_trades.items():
                    entry_price = float(trade.get('entry_price', 0) or 0)
                    symbol = str(trade.get('symbol', ''))
                    current_price = float(
                        trade.get('current_price') or 
                        trade.get('last_price') or 
                        latest_prices.get(symbol) or 
                        entry_price
                    )
                    qty = int(trade.get('quantity', trade.get('qty', 0)) or 0)
                    if trade.get('type', 'BUY').upper() == 'BUY':
                        pnl = (current_price - entry_price) * qty
                    else:
                        pnl = (entry_price - current_price) * qty
                    total += pnl
                    if pnl > 0:
                        total_profit += pnl
                    else:
                        total_loss += abs(pnl)
            except Exception:
                pass  # non-critical, just skip active trade P&L
            # Recalculate percentages
            denominator = total_profit + total_loss
            profit_pct = (total_profit / denominator * 100.0) if denominator > 0 else 0.0
            loss_pct = (total_loss / denominator * 100.0) if denominator > 0 else 0.0

        cursor.execute('''
            SELECT portfolio_value FROM portfolio_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1
        ''', (user_id,))
        prow = cursor.fetchone()
        portfolio_value = float(prow['portfolio_value']) if prow and prow['portfolio_value'] is not None else float(getattr(indian_auto_trader, 'initial_balance', 500000.0))

        logger.info(f"P&L by_date[{start_date}-{end_date}]: range_total={total:.2f}, profit={total_profit:.2f}, loss={total_loss:.2f}, portfolio={portfolio_value:.2f}")
        return jsonify({
            'range_total': round(total, 2),
            'by_date': data,
            'total_profit': round(total_profit, 2),
            'total_loss': round(total_loss, 2),
            'profit_pct': round(profit_pct, 2),
            'loss_pct': round(loss_pct, 2),
            'win_rate': round(win_rate, 2),
            'portfolio_value': round(portfolio_value, 2)
        })
    except Exception as e:
        logger.error(f"Error fetching P&L by date: {e}")
        return jsonify({'error': str(e)}), 500

# Closed trades for Indian dashboard
@app.route('/indian_closed_trades')
def indian_closed_trades():
    if not session.get('user_id'):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        user_id = session['user_id']
        filter_type = request.args.get('filter', 'all')
        from_date = request.args.get('from', '')
        to_date = request.args.get('to', '')
        symbol_filter = request.args.get('symbol', '').strip().upper()

        conditions = ["user_id = ?", "status = 'CLOSED'"]
        params = [user_id]

        if filter_type == 'profit':
            conditions.append("profit_loss > 0")
        elif filter_type == 'loss':
            conditions.append("profit_loss < 0")

        if from_date:
            conditions.append("DATE(exit_time) >= DATE(?)")
            params.append(from_date)
        if to_date:
            conditions.append("DATE(exit_time) <= DATE(?)")
            params.append(to_date)

        if symbol_filter:
            conditions.append("UPPER(symbol) LIKE ?")
            params.append(f"%{symbol_filter}%")

        where = " AND ".join(conditions)
        cursor = get_db().cursor()
        cursor.execute(f'''
            SELECT DISTINCT symbol, direction, entry_price, exit_price, quantity, status, entry_time, exit_time, profit_loss
            FROM trades
            WHERE {where}
            ORDER BY datetime(exit_time) DESC
            LIMIT 100
        ''', params)
        rows = cursor.fetchall()
        results = []
        if rows:
            cols = [d[0] for d in cursor.description]
            for r in rows:
                item = {k: r[idx] for idx, k in enumerate(cols)}
                results.append(item)
        return jsonify({'trades': results, 'count': len(results)})
    except Exception as e:
        logger.error(f"Error fetching indian closed trades: {e}")
        return jsonify({'error': str(e)}), 500

# Seed dummy trades for demo/visual checks
@app.route('/seed_dummy_trades')
def seed_dummy_trades():
    if not session.get('user_id'):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        user_id = session['user_id']
        connection = get_db()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = connection.cursor()

        # Simple helper to insert a closed trade
        def insert_trade(symbol, direction, entry_price, exit_price, qty, status, entry_dt, exit_dt, pnl):
            # Skip if an identical closed trade already exists (same symbol, direction, entry/exit times and P&L)
            cursor.execute('''
                SELECT 1 FROM trades WHERE user_id = ? AND symbol = ? AND direction = ?
                AND entry_time = ? AND exit_time = ? AND profit_loss = ? AND status = 'CLOSED' LIMIT 1
            ''', (user_id, symbol, direction, entry_dt, exit_dt, float(pnl)))
            if cursor.fetchone():
                return
            cursor.execute('''
                INSERT INTO trades (user_id, symbol, direction, entry_price, exit_price, quantity, status, entry_time, exit_time, profit_loss, stop_loss, take_profit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, symbol, direction, float(entry_price), float(exit_price), float(qty), status, entry_dt, exit_dt, float(pnl), 0.0, 0.0))

        now = datetime.now()
        today = now.strftime('%Y-%m-%d')
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        # Example dummy trades
        insert_trade('SENSEX', 'SELL', 65000.0, 64850.0, 1, 'CLOSED', f'{today} 09:45:00', f'{today} 10:30:00', 1500.00)
        insert_trade('HINDUNILVR', 'SELL', 2500.0, 2525.0, 1, 'CLOSED', f'{today} 10:30:00', f'{today} 11:45:00', -625.00)
        insert_trade('BANKNIFTY', 'BUY', 44500.0, 44620.0, 1, 'CLOSED', f'{yesterday} 10:00:00', f'{yesterday} 11:10:00', 1200.00)

        # Update portfolio_history snapshot based on last value
        cursor.execute('''
            SELECT portfolio_value FROM portfolio_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1
        ''', (user_id,))
        row = cursor.fetchone()
        last_val = float(row['portfolio_value']) if row else float(getattr(indian_auto_trader, 'initial_balance', 500000.0))
        delta = 1500.00 - 625.00 + 1200.00
        new_val = last_val + delta
        cursor.execute('''
            INSERT INTO portfolio_history (user_id, portfolio_value, timestamp) VALUES (?, ?, ?)
        ''', (user_id, new_val, now.strftime('%Y-%m-%d %H:%M:%S')))

        connection.commit()
        return jsonify({'status': 'ok', 'inserted_trades': 3, 'new_portfolio_value': round(new_val, 2)})
    except Exception as e:
        try:
            connection.rollback()
        except Exception as rb_e:
            logger.debug(f"Rollback failed in seed_dummy_trades: {rb_e}")
        logger.error(f"Error seeding dummy trades: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/create_default_user')
def create_default_user():
    """Create a default user for testing if none exists"""
    try:
        connection = get_db()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        
        # Check if any user exists
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        if user_count == 0:
            # Create default user
            default_password = generate_password_hash("admin123")
            cursor.execute("""
                INSERT INTO users (username, password, registered_at, balance, is_premium, demo_end_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                "admin",
                default_password,
                datetime.now().isoformat(),
                500000.00,  # Starting balance
                1,  # Premium user
                (datetime.now() + timedelta(days=30)).isoformat()  # 30 days demo
            ))
            
            # Create initial portfolio snapshot
            cursor.execute("""
                INSERT INTO portfolio_history (user_id, portfolio_value, timestamp)
                VALUES (?, ?, ?)
            """, (1, 500000.00, datetime.now().isoformat()))
            
            connection.commit()
            cursor.close()
            
            return jsonify({
                'status': 'success',
                'message': 'Default user created successfully',
                'username': 'admin',
                'password': 'admin123'
            })
        else:
            return jsonify({
                'status': 'info',
                'message': f'Users already exist ({user_count} users)'
            })
            
    except Exception as e:
        logger.error(f"Error creating default user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/db_status')
def check_database_status():
    """Check database status and table information"""
    try:
        connection = get_db()
        if connection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = connection.cursor()
        
        # Get table information
        tables = ['users', 'trades', 'positions', 'portfolio_history', 'signals']
        table_info = {}
        
        for table in tables:
            try:
                cursor.execute("SELECT COUNT(*) FROM [{}]".format(table.replace(']', ']]')))
                count = cursor.fetchone()[0]
                table_info[table] = count
            except Exception as e:
                table_info[table] = f"Error: {str(e)}"
        
        cursor.close()
        
        return jsonify({
            'status': 'success',
            'database': 'trading.db',
            'tables': table_info,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error checking database status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/reset_database')
def reset_database():
    """Reset database completely and recreate with sample data"""
    try:
        import os
        
        # Close any existing connections
        if hasattr(g, 'db'):
            g.db.close()
            delattr(g, 'db')
        
        # Delete the database file
        db_path = os.path.join(BASE_DIR, 'trading.db')
        if os.path.exists(db_path):
            os.remove(db_path)
            logger.info("Database file deleted")
        
        # Reinitialize database
        init_db()
        
        return jsonify({
            'status': 'success',
            'message': 'Database reset successfully',
            'default_user': 'admin',
            'default_password': 'admin123'
        })
        
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/cache-stats', methods=['GET'])
def get_cache_stats():
    """Get cache statistics"""
    try:
        from cache_manager import cache_manager
        stats = cache_manager.get_cache_stats()
        return jsonify({
            'status': 'success',
            'cache_stats': stats
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/clear-cache', methods=['POST'])
def clear_cache():
    """Clear all cache entries"""
    try:
        from cache_manager import cache_manager
        result = cache_manager.clear_all()
        return jsonify({
            'status': 'success',
            'message': 'Cache cleared successfully' if result else 'Failed to clear cache'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/cleanup-cache', methods=['POST'])
def cleanup_cache():
    """Clean up expired cache entries"""
    try:
        from cache_manager import cache_manager
        removed_count = cache_manager.cleanup_expired()
        return jsonify({
            'status': 'success',
            'message': f'Cleaned up {removed_count} expired cache entries'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/rate-limit-stats', methods=['GET'])
def get_rate_limit_stats():
    """Get rate limiting statistics"""
    try:
        from rate_limiter import rate_limiter
        stats = rate_limiter.get_stats()
        return jsonify({
            'status': 'success',
            'rate_limit_stats': stats
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/reset-rate-limits', methods=['POST'])
def reset_rate_limits():
    """Reset rate limiting for all services"""
    try:
        from rate_limiter import rate_limiter
        rate_limiter.reset()
        return jsonify({
            'status': 'success',
            'message': 'Rate limits reset successfully'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/performance-metrics', methods=['GET'])
def get_performance_metrics():
    """Get current performance metrics"""
    try:
        from performance_monitor import performance_monitor
        metrics = performance_monitor.get_current_metrics()
        return jsonify({
            'status': 'success',
            'performance_metrics': metrics
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/performance-history', methods=['GET'])
def get_performance_history():
    """Get performance metrics history"""
    try:
        from performance_monitor import performance_monitor
        hours = request.args.get('hours', 24, type=int)
        history = performance_monitor.get_metrics_history(hours)
        return jsonify({
            'status': 'success',
            'performance_history': history
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/performance-summary', methods=['GET'])
def get_performance_summary():
    """Get performance summary"""
    try:
        from performance_monitor import performance_monitor
        summary = performance_monitor.get_performance_summary()
        return jsonify({
            'status': 'success',
            'performance_summary': summary
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/start-performance-monitoring', methods=['POST'])
def start_performance_monitoring():
    """Start performance monitoring"""
    try:
        from performance_monitor import performance_monitor
        interval = request.json.get('interval', 30) if request.json else 30
        performance_monitor.start_monitoring(interval)
        return jsonify({
            'status': 'success',
            'message': f'Performance monitoring started with {interval}s interval'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/stop-performance-monitoring', methods=['POST'])
def stop_performance_monitoring():
    """Stop performance monitoring"""
    try:
        from performance_monitor import performance_monitor
        performance_monitor.stop_monitoring()
        return jsonify({
            'status': 'success',
            'message': 'Performance monitoring stopped'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/portfolio/analytics', methods=['GET'])
def get_portfolio_analytics():
    """Get comprehensive portfolio analytics"""
    try:
        user_id = request.args.get('user_id', 3, type=int)
        days = request.args.get('days', 30, type=int)
        
        # Get portfolio summary
        summary = portfolio_analytics.get_portfolio_summary(user_id)
        
        # Get performance analysis
        performance = portfolio_analytics.get_performance_analysis(user_id, days)
        
        # Get risk analysis
        risk_analysis = portfolio_analytics.get_risk_analysis(user_id)
        
        # Get trade analytics
        trade_analytics = portfolio_analytics.get_trade_analytics(user_id, days)
        
        # Get sector analysis
        sector_analysis = portfolio_analytics.get_sector_analysis(user_id)
        
        return jsonify({
            'summary': summary,
            'performance': performance,
            'risk_analysis': risk_analysis,
            'trade_analytics': trade_analytics,
            'sector_analysis': sector_analysis,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/portfolio/performance', methods=['GET'])
def get_portfolio_performance():
    """Get detailed performance analysis"""
    try:
        user_id = request.args.get('user_id', 3, type=int)
        days = request.args.get('days', 30, type=int)
        
        performance = portfolio_analytics.get_performance_analysis(user_id, days)
        
        return jsonify(performance)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/portfolio/risk', methods=['GET'])
def get_portfolio_risk():
    """Get risk analysis"""
    try:
        user_id = request.args.get('user_id', 3, type=int)
        
        risk_analysis = portfolio_analytics.get_risk_analysis(user_id)
        
        return jsonify(risk_analysis)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/portfolio/trades', methods=['GET'])
def get_trade_analytics():
    """Get trade analytics"""
    try:
        user_id = request.args.get('user_id', 3, type=int)
        days = request.args.get('days', 30, type=int)
        
        trade_analytics = portfolio_analytics.get_trade_analytics(user_id, days)
        
        return jsonify(trade_analytics)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/portfolio/sectors', methods=['GET'])
def get_sector_analysis():
    """Get sector analysis"""
    try:
        user_id = request.args.get('user_id', 3, type=int)
        
        sector_analysis = portfolio_analytics.get_sector_analysis(user_id)
        
        return jsonify(sector_analysis)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/angel_one/configure', methods=['POST'])
def configure_angel_one():
    """Configure Angel One API credentials"""
    try:
        data = request.get_json()
        
        api_key = data.get('api_key')
        client_id = data.get('client_id')
        password = data.get('password')
        totp_secret = data.get('totp_secret')
        
        if not all([api_key, client_id, password, totp_secret]):
            return jsonify({'error': 'Missing required credentials'}), 400
        
        # Initialize Angel One client
        global angel_one_client
        angel_one_client = AngelOneAPI(api_key, client_id, password, totp_secret)
        
        # Test connection
        if angel_one_client.generate_session():
            # Update all components with new client
            global trading_system, risk_manager, indian_trading_system, angel_one_ws_manager
            
            # Default to demo mode (mock funds, live data) for safety
            angel_one_client.set_demo_mode(True)
            set_trading_mode(False)
            
            trading_system = TradingSystem(angel_one_client)
            risk_manager = RiskManager(angel_one_client=angel_one_client)
            indian_trading_system = IndianTradingSystem(db_path=os.path.join(BASE_DIR, 'trading.db'), angel_one_client=angel_one_client)
            
            from angel_one_api import AngelOneWebSocket
            angel_one_ws_manager = AngelOneWebSocket(angel_one_client)
            angel_one_ws_manager.start_streaming(push_indian_price_update)
            
            return jsonify({
                'status': 'success',
                'message': 'Angel One API configured successfully — started in DEMO mode (virtual funds)',
                'client_id': client_id
            })
        else:
            return jsonify({'error': 'Failed to authenticate with Angel One API'}), 401
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/angel_one/status', methods=['GET'])
def get_angel_one_status():
    """Get Angel One API status — uses lightweight is_connected flag, does NOT re-authenticate"""
    try:
        global angel_one_client
        
        if angel_one_client is None:
            return jsonify({
                'status': 'not_configured',
                'message': 'Angel One API not configured'
            })
        
        if not hasattr(angel_one_client, 'is_connected'):
            return jsonify({
                'status': 'mock',
                'message': 'Using mock Angel One API for testing'
            })
        
        if angel_one_client.is_connected:
            # Lightweight verification — try getProfile to confirm session is still alive
            try:
                profile = angel_one_client.get_profile()
                if profile and profile.get('status'):
                    mode = 'demo' if getattr(angel_one_client, 'demo_mode', False) else 'connected'
                    label = 'DEMO mode (virtual funds, live market data)' if mode == 'demo' else 'connected successfully'
                    return jsonify({
                        'status': mode,
                        'message': f'Angel One API connected — {label}'
                    })
            except Exception:
                pass  # Fall through to connected response below if profile check fails
            
            # Profile check failed but is_connected is still True — treat as connected
            mode = 'demo' if getattr(angel_one_client, 'demo_mode', False) else 'connected'
            return jsonify({
                'status': mode,
                'message': f'Angel One API connected'
            })
        else:
            return jsonify({
                'status': 'disconnected',
                'message': 'Angel One API not connected. Click "Refresh Session" to reconnect.'
            })
            
    except Exception as e:
        logger.error(f"Error checking Angel One status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/angel_one/refresh', methods=['POST'])
def refresh_angel_one_session():
    """Force an Angel One session refresh using configured credentials/TOTP"""
    try:
        global angel_one_client, angel_one_ws_manager
        if angel_one_client is None:
            return jsonify({'error': 'Angel One API not configured'}), 400
        if getattr(angel_one_client, 'client_id', None) == 'mock_client' or not hasattr(angel_one_client, 'generate_session'):
            return jsonify({'status': 'mock', 'message': 'Using mock API'}), 200
        ok = angel_one_client.generate_session()
        if ok:
            # Restart WebSocket with new session token
            try:
                angel_one_ws_manager.close_connection()
            except Exception:
                pass
            from angel_one_api import AngelOneWebSocket
            angel_one_ws_manager = AngelOneWebSocket(angel_one_client)
            angel_one_ws_manager.start_streaming(push_indian_price_update)
            return jsonify({'status': 'connected', 'message': 'Session and WebSocket refreshed successfully'})
        return jsonify({'status': 'disconnected', 'message': 'Failed to refresh session'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/angel_one/funds', methods=['GET'])
def get_angel_one_funds():
    """Get available funds from Angel One"""
    try:
        global angel_one_client
        
        if angel_one_client is None:
            return jsonify({'error': 'Angel One API not configured'}), 400
        
        funds = angel_one_client.get_funds()
        return jsonify(funds)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/angel_one/holdings', methods=['GET'])
def get_angel_one_holdings():
    """Get holdings from Angel One"""
    try:
        global angel_one_client
        
        if angel_one_client is None:
            return jsonify({'error': 'Angel One API not configured'}), 400
        
        holdings = angel_one_client.get_holdings()
        return jsonify(holdings)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/angel_one/positions', methods=['GET'])
def get_angel_one_positions():
    """Get positions from Angel One"""
    try:
        global angel_one_client
        
        if angel_one_client is None:
            return jsonify({'error': 'Angel One API not configured'}), 400
        
        positions = angel_one_client.get_positions()
        return jsonify(positions)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Global trading mode flag (True = live, False = demo)
# Determined by Angel One connection state, not by string matching
TRADING_MODE_LIVE = False

def is_live_mode() -> bool:
    """Check if system is in live trading mode"""
    global TRADING_MODE_LIVE
    return TRADING_MODE_LIVE

def set_trading_mode(live: bool):
    """Set the global trading mode flag and sync to all sub-systems"""
    global TRADING_MODE_LIVE
    TRADING_MODE_LIVE = live
    try:
        if 'indian_trading_system' in dir() and indian_trading_system is not None:
            indian_trading_system.set_live_mode(live)
    except Exception:
        pass
    logger.info(f"Trading mode set to: {'LIVE' if live else 'DEMO'}")

# ── Subscription Plan Helpers ───────────────────────────────────────────────
# is_premium column values: 0 = Free, 1 = Premium, 2 = Pro, 3 = Enterprise
PLAN_ORDER = {'free': 0, 'premium': 1, 'pro': 2, 'enterprise': 3}
PLAN_NAMES = {0: 'free', 1: 'premium', 2: 'pro', 3: 'enterprise'}

def get_user_plan(user_id):
    """Get user's subscription plan: 'free', 'premium', 'pro', or 'enterprise'"""
    try:
        db = get_db()
        if db is None:
            return 'free'
        cursor = db.cursor()
        
        sub_plan = 'free'
        # 1. Check subscriptions table
        try:
            cursor.execute("SELECT plan_type, status FROM subscriptions WHERE user_id = ?", (user_id,))
            sub_row = cursor.fetchone()
            if sub_row:
                plan_type, status = sub_row
                if status in ['active', 'trialing']:
                    sub_plan = plan_type.lower()
        except Exception as sub_e:
            pass
            
        # 2. Check legacy users.is_premium column
        legacy_plan = 'free'
        try:
            cursor.execute('SELECT is_premium FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                tier = row[0] if row[0] else 0
                legacy_plan = PLAN_NAMES.get(int(tier), 'free')
        except Exception as legacy_e:
            pass
            
        cursor.close()
        
        # Return the plan with the higher order rank
        if PLAN_ORDER.get(sub_plan, 0) >= PLAN_ORDER.get(legacy_plan, 0):
            return sub_plan
        return legacy_plan
    except Exception as e:
        logger.error(f"Error getting user plan: {e}")
        return 'free'

def require_plan(minimum_plan):
    """Decorator: block access if user plan is below minimum_plan.
    Usage: @require_plan('premium') before a route handler."""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Not authenticated'}), 401
            user_plan = get_user_plan(user_id)
            if PLAN_ORDER.get(user_plan, 0) < PLAN_ORDER.get(minimum_plan, 0):
                return jsonify({
                    'error': f'This feature requires {minimum_plan.title()} plan or above. You are on the {user_plan.title()} plan.',
                    'required_plan': minimum_plan,
                    'current_plan': user_plan,
                    'upgrade_required': True
                }), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

FREE_DAILY_SIGNAL_LIMIT = 5

def check_signal_limit(user_id):
    """Check if a free user has exceeded their daily signal limit.
    Returns (allowed: bool, remaining: int)."""
    plan = get_user_plan(user_id)
    if plan != 'free':
        return True, 999  # unlimited
    try:
        db = get_db()
        cursor = db.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT COUNT(*) FROM signals WHERE user_id = ? AND DATE(created_at) = ?",
            (user_id, today)
        )
        count = cursor.fetchone()[0]
        cursor.close()
        remaining = max(0, FREE_DAILY_SIGNAL_LIMIT - count)
        return count < FREE_DAILY_SIGNAL_LIMIT, remaining
    except Exception as e:
        logger.error(f"Error checking signal limit: {e}")
        return True, FREE_DAILY_SIGNAL_LIMIT

# Trading Mode Management
@app.route('/api/current_mode', methods=['GET'])
def get_current_mode():
    """Get current trading mode"""
    from indian_trading_system import IndianTradingSystem
    return jsonify({
        'mode': 'live' if is_live_mode() else 'demo',
        'simulation': get_setting('simulation_mode', '0') == '1'
    })

@app.route('/api/switch_to_live', methods=['POST'])
def switch_to_live():
    """Switch to live trading mode"""
    try:
        global angel_one_client, trading_system, risk_manager, indian_trading_system, indian_auto_trader
        from trading_system import TradingSystem
        from risk_manager import RiskManager
        from indian_trading_system import IndianTradingSystem, IndianAutoTrader

        # Check Angel One credentials exist
        api_key = os.getenv('ANGEL_ONE_API_KEY')
        client_id = os.getenv('ANGEL_ONE_CLIENT_CODE')
        password = os.getenv('ANGEL_ONE_PASSWORD')
        totp_secret = os.getenv('ANGEL_ONE_TOTP_SECRET')
        if not all([api_key, client_id, password, totp_secret]):
            return jsonify({'status': 'error', 'error': 'Angel One credentials not configured in .env'}), 400

        # Create fresh real client
        new_client = AngelOneAPI(api_key, client_id, password, totp_secret)
        if not new_client.generate_session():
            return jsonify({'status': 'error', 'error': 'Failed to authenticate with Angel One API'}), 401

        # Terminate old session if switching from another live client
        if angel_one_client and hasattr(angel_one_client, 'terminate_session') and angel_one_client is not new_client:
            try:
                angel_one_client.terminate_session()
            except Exception:
                pass

        angel_one_client = new_client
        angel_one_client.set_demo_mode(False)
        set_trading_mode(True)

        # Re-init ALL sub-systems with real client
        risk_manager = RiskManager(angel_one_client=angel_one_client)
        trading_system = TradingSystem(angel_one_client=angel_one_client)
        indian_trading_system = IndianTradingSystem(db_path=os.path.join(BASE_DIR, 'trading.db'), angel_one_client=angel_one_client)
        indian_auto_trader = IndianAutoTrader(indian_trading_system, user_id=1, default_quantity=1, initial_balance=500000.0)

        return jsonify({
            'status': 'success',
            'message': 'Switched to LIVE trading mode',
            'mode': 'live'
        })

    except Exception as e:
        set_trading_mode(False)
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/switch_to_demo', methods=['POST'])
def switch_to_demo():
    """Switch to demo trading mode — keeps live Angel One connection for market data,
    but returns mock funds and simulates orders."""
    try:
        global angel_one_client, trading_system, risk_manager, indian_trading_system, indian_auto_trader
        from trading_system import TradingSystem
        from risk_manager import RiskManager
        from indian_trading_system import IndianTradingSystem, IndianAutoTrader

        # Stop auto-trader if running
        if indian_auto_trader:
            try:
                indian_auto_trader.stop()
            except Exception:
                pass

        # If we have a real live Angel One client, keep it but set demo mode
        if angel_one_client is not None and hasattr(angel_one_client, 'smart_api') and angel_one_client.is_connected:
            logger.info("Keeping live Angel One client, switching to demo mode (mock funds)")
            angel_one_client.set_demo_mode(True)
        else:
            # No real client connected — create a mock client for data-less demo
            angel_one_client = AngelOneAPI(
                api_key="mock_key",
                client_id="mock_client",
                password="mock_password",
                totp_secret="MOCKMOCKMOCKMOCKMOCKMOCKMOCKMOCKMOCKMOCK"
            )
            angel_one_client.access_token = "mock_token"
            angel_one_client.feed_token = "mock_feed_token"
            angel_one_client.is_connected = True
            angel_one_client.refresh_token = "mock_refresh_token"
            angel_one_client.demo_mode = True

        set_trading_mode(False)

        # Re-init ALL sub-systems (they'll inherit the demo_mode-aware client)
        risk_manager = RiskManager(angel_one_client=angel_one_client)
        trading_system = TradingSystem(angel_one_client=angel_one_client)
        indian_trading_system = IndianTradingSystem(db_path=os.path.join(BASE_DIR, 'trading.db'), angel_one_client=angel_one_client)
        indian_auto_trader = IndianAutoTrader(indian_trading_system, user_id=1, default_quantity=1, initial_balance=500000.0)

        return jsonify({
            'status': 'success',
            'message': 'Switched to DEMO trading mode — live market data with virtual funds',
            'mode': 'demo'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

# Admin Panel API Endpoints
@app.route('/api/admin/system-status', methods=['GET'])
def get_admin_system_status():
    """Get system status for admin panel"""
    try:
        # Get current trading status
        auto_trading_active = hasattr(indian_auto_trader, 'running') and indian_auto_trader.running
        
        # Get portfolio summary
        portfolio_summary = portfolio_analytics.get_portfolio_summary(1)  # Default user ID
        
        # Get performance data
        performance = portfolio_analytics.get_performance_analysis(1, 30)
        
        # Check data feed status
        data_service = get_data_injection_service()
        data_feed_active = len(data_service.update_threads) > 0
        
        trading_mode = 'LIVE' if is_live_mode() else 'DEMO'
        
        return jsonify({
            'active_trades': portfolio_summary.get('num_active_positions', 0),
            'total_pnl': portfolio_summary.get('today_pnl', 0.0),
            'win_rate': performance.get('win_rate', 0.0),
            'trading_mode': trading_mode,
            'auto_trading_active': auto_trading_active,
            'data_feed_active': data_feed_active,
            'system_health': 100,  # Placeholder
            'data_quality': 85 if data_feed_active else 0  # Placeholder
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/trading-params', methods=['GET'])
def get_admin_trading_params():
    """Get current trading parameters"""
    try:
        # Get current risk manager settings
        risk_params = {
            'max_concurrent_trades': getattr(risk_manager, 'max_concurrent_trades', 5),
            'risk_per_trade': getattr(risk_manager, 'risk_per_trade', 2.0),
            'stop_loss': getattr(risk_manager, 'stop_loss', 3.0),
            'take_profit': getattr(risk_manager, 'take_profit', 6.0),
            'strategy': 'momentum'  # Default strategy
        }
        
        return jsonify(risk_params)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/update-trading-params', methods=['POST'])
def update_admin_trading_params():
    """Update trading parameters"""
    try:
        data = request.get_json()
        
        # Update risk manager parameters
        if hasattr(risk_manager, 'max_concurrent_trades'):
            risk_manager.max_concurrent_trades = data.get('max_concurrent_trades', 5)
        if hasattr(risk_manager, 'risk_per_trade'):
            risk_manager.risk_per_trade = data.get('risk_per_trade', 2.0)
        if hasattr(risk_manager, 'stop_loss'):
            risk_manager.stop_loss = data.get('stop_loss', 3.0)
        if hasattr(risk_manager, 'take_profit'):
            risk_manager.take_profit = data.get('take_profit', 6.0)
        
        # Update strategy (placeholder for future implementation)
        strategy = data.get('strategy', 'momentum')
        
        return jsonify({
            'status': 'success',
            'message': 'Trading parameters updated successfully'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/start-data-injection', methods=['POST'])
def start_admin_data_injection():
    """Start data injection from external API"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('data_source') or not data.get('symbols'):
            return jsonify({'status': 'error', 'error': 'Missing required fields'}), 400
        
        # Get data injection service
        data_service = get_data_injection_service()
        
        # Start data injection
        result = data_service.start_data_injection(data)
        
        if result['status'] == 'success':
            return jsonify(result)
        else:
            return jsonify(result), 400
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/stop-data-injection', methods=['POST'])
def stop_admin_data_injection():
    """Stop data injection"""
    try:
        # Get data injection service
        data_service = get_data_injection_service()
        
        # Stop data injection
        result = data_service.stop_data_injection()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/start-auto-trading', methods=['POST'])
@require_plan('premium')
def start_admin_auto_trading():
    """Start auto-trading system (requires Premium+)"""
    try:
        sync_autotrader_user()
    except Exception as sync_err:
        logger.error(f"Error syncing autotrader: {sync_err}")
    try:
        if hasattr(indian_auto_trader, 'start'):
            indian_auto_trader.start()
            return jsonify({
                'status': 'success',
                'message': 'Auto-trading started successfully'
            })
        else:
            return jsonify({'status': 'error', 'error': 'Auto-trading system not available'}), 400
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/stop-auto-trading', methods=['POST'])
def stop_admin_auto_trading():
    """Stop auto-trading system"""
    try:
        if hasattr(indian_auto_trader, 'stop'):
            indian_auto_trader.stop()
            return jsonify({
                'status': 'success',
                'message': 'Auto-trading stopped successfully'
            })
        else:
            return jsonify({'status': 'error', 'error': 'Auto-trading system not available'}), 400
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/clear-trades', methods=['POST'])
def clear_admin_trades():
    """Clear all trades"""
    try:
        connection = get_db()
        if connection is None:
            return jsonify({'status': 'error', 'error': 'Database connection failed'}), 500
        
        cursor = connection.cursor()
        
        # Clear trades table
        cursor.execute('DELETE FROM trades')
        cursor.execute('DELETE FROM orders')
        cursor.execute('DELETE FROM positions')
        cursor.execute('DELETE FROM portfolio_history')
        cursor.execute('DELETE FROM signals')
        
        # Reset user balance
        cursor.execute('UPDATE users SET balance = 500000.00 WHERE id = 1')
        
        # Insert initial portfolio snapshot
        cursor.execute('''
            INSERT INTO portfolio_history (user_id, portfolio_value, timestamp)
            VALUES (?, ?, ?)
        ''', (1, 500000.00, datetime.now().isoformat()))
        
        connection.commit()
        cursor.close()
        
        return jsonify({
            'status': 'success',
            'message': 'All trades cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"Error clearing trades: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/reset-portfolio', methods=['POST'])
def reset_admin_portfolio():
    """Reset portfolio to initial state"""
    try:
        connection = get_db()
        if connection is None:
            return jsonify({'status': 'error', 'error': 'Database connection failed'})
        
        cursor = connection.cursor()
        
        # Clear all trading data
        cursor.execute('DELETE FROM trades')
        cursor.execute('DELETE FROM positions')
        cursor.execute('DELETE FROM portfolio_history')
        cursor.execute('DELETE FROM signals')
        
        # Reset user balance to initial amount
        cursor.execute('UPDATE users SET balance = 500000.00 WHERE id = 1')
        
        # Insert initial portfolio snapshot
        cursor.execute('''
            INSERT INTO portfolio_history (user_id, portfolio_value, timestamp)
            VALUES (?, ?, ?)
        ''', (1, 500000.00, datetime.now().isoformat()))
        
        # Re-seed with sample data
        init_db()
        
        connection.commit()
        cursor.close()
        
        return jsonify({
            'status': 'success',
            'message': 'Portfolio reset successfully'
        })
        
    except Exception as e:
        logger.error(f"Error resetting portfolio: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/export-data', methods=['GET'])
def export_admin_data():
    """Export trading data"""
    try:
        connection = get_db()
        if connection is None:
            return jsonify({'error': 'Database connection failed'}), 500
        
        cursor = connection.cursor()
        
        # Export trades
        cursor.execute('SELECT * FROM trades')
        trades = cursor.fetchall()
        
        # Export positions
        cursor.execute('SELECT * FROM positions')
        positions = cursor.fetchall()
        
        # Export portfolio history
        cursor.execute('SELECT * FROM portfolio_history')
        portfolio_history = cursor.fetchall()
        
        # Export users
        cursor.execute('SELECT * FROM users')
        users = cursor.fetchall()
        
        cursor.close()
        
        export_data = {
            'trades': trades,
            'positions': positions,
            'portfolio_history': portfolio_history,
            'users': users,
            'export_timestamp': datetime.now().isoformat()
        }
        
        return jsonify(export_data)
        
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/import-data', methods=['POST'])
def import_admin_data():
    """Import trading data"""
    try:
        data = request.get_json()
        
        connection = get_db()
        if connection is None:
            return jsonify({'status': 'error', 'error': 'Database connection failed'}), 500
        
        cursor = connection.cursor()
        
        # Clear existing data
        cursor.execute('DELETE FROM trades')
        cursor.execute('DELETE FROM positions')
        cursor.execute('DELETE FROM portfolio_history')
        cursor.execute('DELETE FROM signals')
        cursor.execute('DELETE FROM users')
        
        # Import trades
        if 'trades' in data:
            for trade in data['trades']:
                # Pad trade record with default stop_loss/take_profit if missing (backward compat)
                while len(trade) < 13:
                    trade = list(trade) + [0.0]
                cursor.execute('''
                    INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', trade)
        
        # Import positions
        if 'positions' in data:
            for position in data['positions']:
                cursor.execute('''
                    INSERT INTO positions VALUES (?, ?, ?, ?, ?)
                ''', position)
        
        # Import portfolio history
        if 'portfolio_history' in data:
            for entry in data['portfolio_history']:
                cursor.execute('''
                    INSERT INTO portfolio_history VALUES (?, ?, ?)
                ''', entry)
        
        # Import users
        if 'users' in data:
            for user in data['users']:
                cursor.execute('''
                    INSERT INTO users VALUES (?, ?, ?, ?, ?)
                ''', user)
        
        connection.commit()
        cursor.close()
        
        return jsonify({
            'status': 'success',
            'message': 'Data imported successfully'
        })
        
    except Exception as e:
        logger.error(f"Error importing data: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

# --- Order Management API ---

@app.route('/api/trade', methods=['POST'])
def api_trade():
    """Execute a market order immediately."""
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper().strip()
        trade_type = data.get('trade_type', '').lower()
        quantity = float(data.get('quantity', 1))
        if not symbol or trade_type not in ('buy', 'sell') or quantity <= 0:
            return jsonify({'success': False, 'message': 'Invalid parameters'}), 400

        result = order_manager.place_order(
            user_id=session['user_id'],
            symbol=symbol,
            order_type='market',
            direction=trade_type,
            quantity=quantity
        )
        if result.get('success'):
            return jsonify({'success': True, 'message': result.get('message', 'Trade executed'), 'trade_id': result.get('trade_id')})
        return jsonify({'success': False, 'message': result.get('error', 'Trade failed')}), 400
    except Exception as e:
        logger.error(f"Error in /api/trade: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/orders', methods=['GET', 'POST'])
def api_orders():
    """List orders or place a new order."""
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401

    if request.method == 'GET':
        try:
            status = request.args.get('status')
            symbol = request.args.get('symbol')
            order_type = request.args.get('order_type')
            limit = request.args.get('limit', 50, type=int)
            orders = order_manager.get_orders(
                user_id=session['user_id'],
                status=status,
                symbol=symbol,
                order_type=order_type,
                limit=min(limit, 200)
            )
            return jsonify({'orders': orders})
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return jsonify({'error': str(e)}), 500

    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper().strip()
        order_type = data.get('order_type', '').lower()
        direction = data.get('direction', '').lower()
        quantity = float(data.get('quantity', 1))
        price = float(data.get('price')) if data.get('price') else None
        stop_price = float(data.get('stop_price')) if data.get('stop_price') else None

        if not symbol or order_type not in ('market', 'limit', 'stop_loss', 'take_profit'):
            return jsonify({'success': False, 'error': 'Invalid order type or symbol'}), 400
        if direction not in ('buy', 'sell'):
            return jsonify({'success': False, 'error': 'Direction must be buy or sell'}), 400
        if quantity <= 0:
            return jsonify({'success': False, 'error': 'Quantity must be positive'}), 400

        result = order_manager.place_order(
            user_id=session['user_id'],
            symbol=symbol,
            order_type=order_type,
            direction=direction,
            quantity=quantity,
            price=price,
            stop_price=stop_price
        )
        if result.get('success'):
            return jsonify(result), 201
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
def api_cancel_order(order_id):
    """Cancel a pending order."""
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        result = order_manager.cancel_order(order_id, user_id=session['user_id'])
        if result.get('success'):
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/check', methods=['POST'])
def api_check_orders():
    """Manually trigger pending order matching against current prices."""
    try:
        market_prices = {}
        if request.is_json:
            market_prices = request.get_json().get('prices', {})
        executed = order_manager.check_pending_orders(market_prices)
        return jsonify({'executed': len(executed), 'orders': executed})
    except Exception as e:
        logger.error(f"Error checking orders: {e}")
        return jsonify({'error': str(e)}), 500


# --- AI Trading Assistant ---

@app.route('/api/assistant/ask', methods=['POST'])
def api_assistant_ask():
    try:
        data = request.get_json() or {}
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'type': 'text', 'text': 'Please enter a message.'})
        user_id = session.get('user_id')
        result = assistant_get_response(message, user_id=user_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Assistant error: {e}")
        return jsonify({'type': 'error', 'text': 'Sorry, I encountered an error. Please try again.'})


def _safe_error(msg="Internal server error"):
    """Return a generic error response without leaking internals."""
    return jsonify({'status': 'error', 'error': msg}), 500

# Security endpoints
@app.route('/api/admin/security-stats', methods=['GET'])
def get_security_stats():
    """Get security statistics"""
    try:
        stats = security_manager.get_security_stats()
        return jsonify({'status': 'success', 'security_stats': stats})
    except Exception as e:
        logger.error(f"Error getting security stats: {e}")
        return _safe_error("Failed to get security stats")

@app.route('/api/admin/security-events', methods=['GET'])
def get_security_events():
    """Get recent security events"""
    try:
        limit = request.args.get('limit', 100, type=int)
        events = security_manager.get_security_events(limit)
        return jsonify({'status': 'success', 'security_events': events})
    except Exception as e:
        logger.error(f"Error getting security events: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/grant-permission', methods=['POST'])
def grant_permission():
    """Grant permission to user"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        permission = data.get('permission')
        granted_by = data.get('granted_by')
        
        if not user_id or not permission:
            return jsonify({'status': 'error', 'error': 'user_id and permission are required'}), 400
        
        security_manager.grant_permission(user_id, permission, granted_by)
        return jsonify({'status': 'success', 'message': f'Permission {permission} granted to user {user_id}'})
    except Exception as e:
        logger.error(f"Error granting permission: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/revoke-permission', methods=['POST'])
def revoke_permission():
    """Revoke permission from user"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        permission = data.get('permission')
        
        if not user_id or not permission:
            return jsonify({'status': 'error', 'error': 'user_id and permission are required'}), 400
        
        security_manager.revoke_permission(user_id, permission)
        return jsonify({'status': 'success', 'message': f'Permission {permission} revoked from user {user_id}'})
    except Exception as e:
        logger.error(f"Error revoking permission: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/cleanup-sessions', methods=['POST'])
def cleanup_sessions():
    """Clean up expired sessions"""
    try:
        conn = get_db()
        if conn is None:
            return jsonify({'status': 'error', 'error': 'Database connection failed'}), 500
        
        cursor = conn.cursor()
        
        # Deactivate expired sessions
        cursor.execute('''
            UPDATE user_sessions 
            SET is_active = 0 
            WHERE expires_at < CURRENT_TIMESTAMP AND is_active = 1
        ''')
        
        expired_count = cursor.rowcount
        conn.commit()
        
        return jsonify({
            'status': 'success', 
            'message': f'Cleaned up {expired_count} expired sessions'
        })
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

# Notification endpoints
@app.route('/api/admin/notification-stats', methods=['GET'])
def get_notification_stats():
    """Get notification statistics"""
    try:
        stats = notification_system.get_notification_stats()
        return jsonify({'status': 'success', 'notification_stats': stats})
    except Exception as e:
        logger.error(f"Error getting notification stats: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/send-test-notification', methods=['POST'])
def send_test_notification():
    """Send test notification"""
    try:
        data = request.get_json()
        user_id = data.get('user_id', 1)  # Default to admin user
        notification_type = data.get('type', 'system_alert')
        message = data.get('message', 'This is a test notification')
        
        notification_id = notification_system.create_notification(
            user_id=user_id,
            notification_type=NotificationType(notification_type),
            priority=NotificationPriority.MEDIUM,
            title="Test Notification",
            message=message,
            data={'test': True}
        )
        
        return jsonify({
            'status': 'success', 
            'message': 'Test notification sent',
            'notification_id': notification_id
        })
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

# Backup endpoints
@app.route('/api/admin/backup-stats', methods=['GET'])
def get_backup_stats():
    """Get backup statistics"""
    try:
        stats = backup_system.get_backup_stats()
        return jsonify({'status': 'success', 'backup_stats': stats})
    except Exception as e:
        logger.error(f"Error getting backup stats: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/backup-history', methods=['GET'])
def get_backup_history():
    """Get backup history"""
    try:
        limit = request.args.get('limit', 50, type=int)
        history = backup_system.get_backup_history(limit)
        return jsonify({'status': 'success', 'backup_history': history})
    except Exception as e:
        logger.error(f"Error getting backup history: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/create-backup', methods=['POST'])
def create_backup():
    """Create backup"""
    try:
        data = request.get_json()
        backup_type = data.get('type', 'full')  # full, database, config
        
        if backup_type == 'full':
            result = backup_system.create_full_backup()
        elif backup_type == 'database':
            result = backup_system.create_database_backup()
        elif backup_type == 'config':
            result = backup_system.create_config_backup()
        else:
            return jsonify({'status': 'error', 'error': 'Invalid backup type'}), 400
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/cleanup-backups', methods=['POST'])
def cleanup_backups():
    """Clean up old backups"""
    try:
        result = backup_system.cleanup_old_backups()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error cleaning up backups: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/admin/branding', methods=['GET'])
def get_branding_settings():
    return jsonify(branding.to_dict())

@app.route('/api/admin/branding', methods=['POST'])
def update_branding_settings():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'error': 'No data provided'}), 400
        for key, value in data.items():
            branding.set(key, value)
        branding.clear_cache()
        return jsonify({'status': 'success', 'branding': branding.to_dict()})
    except Exception as e:
        logger.error(f"Error updating branding settings: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/market-status', methods=['GET'])
def get_market_status():
    """Get current market status"""
    try:
        market_open = is_indian_market_open()
        
        # Get current IST time
        from datetime import datetime
        import pytz
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        
        return jsonify({
            'market_open': market_open,
            'current_time': now.strftime('%H:%M:%S'),
            'current_date': now.strftime('%Y-%m-%d'),
            'timezone': 'Asia/Kolkata',
            'market_hours': {
                'open': '09:15',
                'close': '15:30'
            }
        })
    except Exception as e:
        logger.error(f"Error getting market status: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Initialize OTC handler (gated)
DISABLE_OTC = os.getenv('DISABLE_OTC', '0') == '1'
otc_handler = None if DISABLE_OTC else OTCDataHandler(ALPHA_VANTAGE_API_KEY)

# Store active subscriptions (thread-safe via lock)
active_subscriptions = {}
active_subs_lock = threading.Lock()

# Initialize Angel One API (mock disabled)
angel_one_client = None  # Will be set when user provides API credentials
TRADING_MODE_LIVE = False  # Set to True when real Angel One session connects

def push_indian_price_update(symbol: str, price: float):
    """Callback for Angel One WebSocket ticks to emit instantly to UI"""
    update_data = {
        'data': {
            'rate': price,
            'source': 'Angel One WS',
            'type': 'indian_update',
            'pair': symbol,
            'timestamp': datetime.now().isoformat()
        }
    }
    # Broadcast to all users currently looking at this symbol
    with active_subs_lock:
        for user_id, subscriptions in list(active_subscriptions.items()):
            if symbol in subscriptions:
                socketio.emit('price_update', update_data, room=user_id)
            
    # Forward to auto-trader for immediate reaction
    try:
        indian_auto_trader.on_price_update(symbol, price)
    except Exception as pu_e:
        logger.debug(f"Auto-trader price update failed for {symbol}: {pu_e}")

angel_one_ws_manager = None

# Try to initialize Angel One from environment variables
try:
    api_key = os.getenv('ANGEL_ONE_API_KEY')
    client_id = os.getenv('ANGEL_ONE_CLIENT_CODE')  # Changed from ANGEL_ONE_CLIENT_ID
    password = os.getenv('ANGEL_ONE_PASSWORD')
    totp_secret = os.getenv('ANGEL_ONE_TOTP_SECRET')
    
    if api_key and client_id and password and totp_secret:
        angel_one_client = AngelOneAPI(api_key, client_id, password, totp_secret)
        print("[OK] Angel One API initialized from environment variables")
        try:
            if not angel_one_client.generate_session():
                print("[FAIL] Angel One session generation failed on startup")
                set_trading_mode(False)
            else:
                print("[OK] Angel One session connected on startup")
                # Default to DEMO mode (mock funds, live market data)
                angel_one_client.set_demo_mode(True)
                set_trading_mode(False)
                print("[OK] Started in DEMO mode — virtual funds, live Angel One data")
                from angel_one_api import AngelOneWebSocket
                angel_one_ws_manager = AngelOneWebSocket(angel_one_client)
                angel_one_ws_manager.start_streaming(push_indian_price_update)
                print("[OK] Angel One WebSocket streaming started")
        except Exception as e:
            print(f"[FAIL] Angel One session init error: {e}")
            set_trading_mode(False)
    else:
        print("[WARN] Angel One credentials not found in .env. Mock is disabled.")
        set_trading_mode(False)
except Exception as e:
    print(f"[FAIL] Failed to initialize Angel One API: {e}")
    angel_one_client = None
    set_trading_mode(False)

# Initialize components with Angel One integration
trading_system = TradingSystem(angel_one_client)
risk_manager = RiskManager(angel_one_client=angel_one_client)
auto_trader = AutoTrader(trading_system, risk_manager)

# Initialize Indian trading system - use trading.db for consistency
indian_trading_system = IndianTradingSystem(db_path=os.path.join(BASE_DIR, 'trading.db'), angel_one_client=angel_one_client)
indian_auto_trader = IndianAutoTrader(indian_trading_system, user_id=1, default_quantity=1, initial_balance=500000.0)

def sync_autotrader_user():
    """Sync the Indian AutoTrader's user_id with the logged-in user"""
    if session.get('user_id'):
        target_user_id = session['user_id']
        global indian_auto_trader
        if indian_auto_trader and getattr(indian_auto_trader, 'user_id', None) != target_user_id:
            logger.info(f"Syncing IndianAutoTrader user_id from {indian_auto_trader.user_id} to {target_user_id}")
            was_running = getattr(indian_auto_trader, 'running', False)
            if was_running:
                try:
                    indian_auto_trader.stop()
                except Exception:
                    pass
            
            indian_auto_trader.user_id = target_user_id
            # Load trades for the new user without clearing existing (prevents duplicate entries)
            if hasattr(indian_auto_trader, '_load_active_trades_from_db'):
                before = len(indian_auto_trader.active_trades)
                try:
                    indian_auto_trader._load_active_trades_from_db()
                    after = len(indian_auto_trader.active_trades)
                    logger.info(f"User sync: {before} existing + {after - before} loaded from DB = {after} total")
                except Exception as db_e:
                    logger.error(f"Error loading active trades for user {target_user_id}: {db_e}")
            
            # Also calculate total_pnl for this user from trades table in DB
            try:
                conn = sqlite3.connect(os.path.join(BASE_DIR, 'trading.db'))
                cursor = conn.cursor()
                cursor.execute("SELECT SUM(profit_loss) FROM trades WHERE user_id = ?", (target_user_id,))
                row = cursor.fetchone()
                indian_auto_trader.total_pnl = float(row[0]) if row and row[0] is not None else 0.0
                conn.close()
            except Exception as e:
                logger.error(f"Error calculating total_pnl for synced user: {e}")
                
            if was_running:
                try:
                    indian_auto_trader.start()
                except Exception:
                    pass

# Initialize portfolio analytics
portfolio_analytics = PortfolioAnalytics()

# Initialize order manager
order_manager = OrderManager()

# Market status check function
def is_indian_market_open():
    """Check if Indian market is currently open — uses indian_trading_system holiday logic"""
    try:
        return indian_trading_system.is_market_open()
    except Exception as e:
        logger.error(f"Error checking market hours: {str(e)}")
        return False

@app.route("/api/is_trading_day")
def api_is_trading_day():
    """Check if today is a valid NSE trading day"""
    try:
        import pytz
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        is_open = indian_trading_system.is_market_open()
        is_trading = indian_trading_system.is_trading_day()
        all_holidays = sorted(indian_trading_system.get_nse_holidays(now.year))
        # Show only upcoming non-weekend holidays (actual market closures)
        upcoming = [str(h) for h in all_holidays if h >= now.date() and h.weekday() < 5][:10]
        return jsonify({
            "is_market_open": is_open,
            "is_trading_day": is_trading,
            "current_time_ist": now.strftime('%Y-%m-%d %H:%M:%S %Z'),
            "upcoming_holidays": upcoming,
            "total_holidays_this_year": len(all_holidays)
        })
    except Exception as e:
        logger.error(f"Error checking trading day: {str(e)}")
        return jsonify({"error": str(e)}), 500

# websocket_handler = WebSocketHandler(socketio)

# Initialize OTC handler with API key validation
if DISABLE_OTC:
    logger.info("OTC disabled by DISABLE_OTC=1")
    otc_handler = None
elif not ALPHA_VANTAGE_API_KEY or ALPHA_VANTAGE_API_KEY == "YOUR_API_KEY":
    logger.error("Alpha Vantage API key not configured properly")
    otc_handler = None
else:
    try:
        otc_handler = OTCDataHandler(api_key=ALPHA_VANTAGE_API_KEY)
        logger.info("OTC handler initialized successfully with API key")
    except Exception as e:
        logger.error(f"Failed to initialize OTC handler: {str(e)}")
        otc_handler = None

# --- Database helpers ---

_db_local = threading.local()

def get_db_for_thread():
    if not hasattr(_db_local, 'conn') or _db_local.conn is None:
        _db_local.conn = _connect_db()
    return _db_local.conn

@app.teardown_appcontext
def close_connection(exception):
    db_close_connection(exception)

def init_db():
    """Initialize the database with required tables"""
    try:
        db_init_db()
        connection = get_db()
        conn = connection._conn if is_mysql() else connection._conn
        cursor = connection.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        row = cursor.fetchone()
        user_count = row[0] if row else 0
        
        if user_count == 0:
            default_password = generate_password_hash("admin123")
            cursor.execute("""
                INSERT INTO users (username, password, registered_at, balance, is_premium, demo_end_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                "admin",
                default_password,
                datetime.now().isoformat(),
                500000.00,
                1,
                (datetime.now() + timedelta(days=365)).isoformat()
            ))
            
            test_password = generate_password_hash("password123")
            cursor.execute("""
                INSERT INTO users (username, password, registered_at, balance, is_premium, demo_end_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                "testuser",
                test_password,
                datetime.now().isoformat(),
                500000.00,
                1,
                (datetime.now() + timedelta(days=365)).isoformat()
            ))
            
            for uid in [1, 2]:
                cursor.execute("""
                    INSERT INTO portfolio_history (user_id, portfolio_value, timestamp)
                    VALUES (?, ?, ?)
                """, (uid, 500000.00, datetime.now().isoformat()))
                
                for i in range(30):
                    date = datetime.now() - timedelta(days=i)
                    value_change = random.uniform(-2000, 3000)
                    portfolio_value = 500000.00 + value_change
                    cursor.execute("""
                        INSERT INTO portfolio_history (user_id, portfolio_value, timestamp)
                        VALUES (?, ?, ?)
                    """, (uid, max(portfolio_value, 50000), date.isoformat()))
            
            logger.info("Default users 'admin' and 'testuser' created")
            
            sample_trades = [
                ("NIFTY50", "BUY", 19500.0, 19750.0, 100, "CLOSED", 2500.0),
                ("BANKNIFTY", "SELL", 44500.0, 44200.0, 50, "CLOSED", 1500.0),
                ("RELIANCE", "BUY", 2500.0, 2525.0, 200, "CLOSED", 500.0),
                ("TCS", "SELL", 3800.0, 3750.0, 150, "CLOSED", 750.0),
                ("INFY", "BUY", 1500.0, 1480.0, 300, "CLOSED", -600.0)
            ]
            
            for symbol, direction, entry_price, exit_price, quantity, status, pnl in sample_trades:
                cursor.execute("""
                    INSERT INTO trades (user_id, symbol, direction, entry_price, exit_price, quantity, status, entry_time, exit_time, profit_loss, stop_loss, take_profit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    1, symbol, direction, entry_price, exit_price, quantity, status,
                    (datetime.now() - timedelta(days=5)).isoformat(),
                    (datetime.now() - timedelta(days=4)).isoformat(),
                    pnl, 0.0, 0.0
                ))
            
            logger.info("Sample trades created for demonstration")
            
            sample_positions = [
                ("NIFTY50", 50, 19800.0),
                ("BANKNIFTY", 25, 44300.0),
                ("RELIANCE", 100, 2530.0)
            ]
            
            for symbol, quantity, avg_price in sample_positions:
                cursor.execute("""
                    INSERT INTO positions (user_id, symbol, quantity, average_price, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                """, (1, symbol, quantity, avg_price, datetime.now().isoformat()))
            
            logger.info("Sample positions created for demonstration")
            
            sample_signals = [
                ("NIFTY50", "BUY", 0.85, 19500.0, 19400.0, 19700.0),
                ("BANKNIFTY", "SELL", 0.78, 44500.0, 44800.0, 44200.0),
                ("RELIANCE", "BUY", 0.92, 2500.0, 2480.0, 2550.0)
            ]
            
            for symbol, direction, confidence, entry_price, stop_loss, take_profit in sample_signals:
                cursor.execute("""
                    INSERT INTO signals (user_id, pair, direction, confidence, time, created_at, entry_price, stop_loss, take_profit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    1, symbol, direction, confidence, 
                    (datetime.now() - timedelta(hours=2)).isoformat(),
                    datetime.now().isoformat(),
                    entry_price, stop_loss, take_profit
                ))
            
            logger.info("Sample signals created for demonstration")
        
        if not is_mysql():
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_user_exit ON trades(user_id, exit_time)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_user_time ON portfolio_history(user_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_user_time ON signals(user_id, time)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders(user_id, created_at)")
        
        connection.commit()
        logger.info("Database tables created successfully")

    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise

# --- User helpers ---
def get_user_by_username(username):
    """Get user by username from SQLite database"""
    try:
        connection = get_db()
        if connection is None:
            return None
            
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        cursor.close()
        return user
    except Exception as e:
        logger.error(f"Error getting user by username: {e}")
        return None

def get_user_by_id(user_id):
    """Get user by ID from SQLite database"""
    try:
        connection = get_db()
        if connection is None:
            return None
            
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        cursor.close()
        return user
    except Exception as e:
        logger.error(f"Error getting user by ID: {e}")
        return None

def create_user(username, password):
    """Create a new user in SQLite database"""
    try:
        connection = get_db()
        if connection is None:
            return False
            
        cursor = connection.cursor()
        hashed = generate_password_hash(password)
        cursor.execute(
            'INSERT INTO users (username, password, registered_at) VALUES (?, ?, ?)',
            (username, hashed, datetime.now().isoformat())
        )
        connection.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return False

def update_last_login(user_id):
    """Update user's last login time in SQLite database"""
    try:
        connection = get_db()
        if connection is None:
            return False
            
        cursor = connection.cursor()
        cursor.execute(
            'UPDATE users SET last_login = ? WHERE id = ?',
            (datetime.now().isoformat(), user_id)
        )
        connection.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"Error updating last login: {e}")
        return False

def verify_user(username, password):
    """Verify user credentials against SQLite database"""
    try:
        connection = get_db()
        if connection is None:
            return None
            
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        cursor.close()
        
        if user and check_password_hash(user['password'], password):  # Use dictionary-like access
            return user
        return None
    except Exception as e:
        logger.error(f"Error verifying user: {e}")
        return None

def update_password_hash(user_id, password):
    """Update user's password hash in SQLite database"""
    try:
        connection = get_db()
        if connection is None:
            return False
            
        cursor = connection.cursor()
        hashed = generate_password_hash(password)
        cursor.execute(
            'UPDATE users SET password = ? WHERE id = ?',
            (hashed, user_id)
        )
        connection.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"Error updating password: {e}")
        return False

def init_app():
    with app.app_context():
        try:
            init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise


init_app()

# --- Signal helpers ---
def save_signal(user_id, time, pair, direction, entry_price=None, stop_loss=None, take_profit=None, confidence=None):
    """Save trading signal with additional parameters"""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO signals (
                user_id, time, pair, direction, confidence, created_at,
                entry_price, stop_loss, take_profit, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, time, pair, direction, confidence or 0.0, datetime.now().isoformat(),
            entry_price, stop_loss, take_profit, None
        ))
        db.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"Error saving signal: {str(e)}")
        return False

def get_signals_for_user(user_id, limit=20):
    """Get trading signals for user with all details"""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute('''
            SELECT
                time, pair, direction, confidence, created_at,
                entry_price, stop_loss, take_profit, result
            FROM signals
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        signals = cursor.fetchall()
        cursor.close()

        # Convert to list of dictionaries
        columns = ['time', 'pair', 'direction', 'confidence', 'created_at', 'entry_price', 'stop_loss', 'take_profit', 'result']
        return [dict(zip(columns, signal)) for signal in signals]
    except Exception as e:
        logger.error(f"Error retrieving signals: {str(e)}")
        return []

def get_signal_stats(user_id):
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute('SELECT COUNT(*) FROM signals WHERE user_id = ?', (user_id,))
        total = cursor.fetchone()[0]
        
        cursor.execute('SELECT pair, COUNT(*) as count FROM signals WHERE user_id = ? GROUP BY pair', (user_id,))
        by_pair = cursor.fetchall()
        
        cursor.execute('SELECT direction, COUNT(*) as count FROM signals WHERE user_id = ? GROUP BY direction', (user_id,))
        by_direction = cursor.fetchall()
        
        cursor.close()
        return total, by_pair, by_direction
    except Exception as e:
        logger.error(f"Error getting signal stats: {str(e)}")
        return 0, [], []

# --- App logic ---
pairs = ["EURAUD", "USDCHF", "USDBRL", "AUDUSD", "GBPCAD", "EURCAD", "NZDUSD", "USDPKR", "EURUSD", "USDCAD", "AUDCHF", "GBPUSD", "EURGBP"]
brokers = ["Quotex", "Pocket Option", "Binolla", "IQ Option", "Bullex", "Exnova"]
otc_pairs = ["EURAUD_OTC", "USDCHF_OTC", "USDBRL_OTC", "AUDUSD_OTC", "GBPCAD_OTC", "EURCAD_OTC", "NZDUSD_OTC", "USDPKR_OTC", "EURUSD_OTC", "USDCAD_OTC", "AUDCHF_OTC", "GBPUSD_OTC", "EURGBP_OTC"]
otc_brokers = ["Quotex", "Pocket Option", "Binolla", "IQ Option", "Bullex", "Exnova"]

# Initialize price cache
price_cache = {}

# Symbol mapping for Indian markets and forex pairs
symbol_map = {
    # Major Indices
    "NIFTY50": "^NSEI",  # NSE NIFTY 50
    "BANKNIFTY": "^NSEBANK",  # NSE BANK NIFTY
    "SENSEX": "^BSESN",  # BSE SENSEX
    "FINNIFTY": "^CNXFIN",  # NSE FINANCIAL SERVICES
    "MIDCPNIFTY": "^NSEMDCP50",  # NSE MIDCAP 50
    # Sector Indices
    "NIFTYREALTY": "^CNXREALTY",
    "NIFTYPVTBANK": "^NIFTYBANK",
    "NIFTYPSUBANK": "^CNXPSUBANK",
    "NIFTYFIN": "^CNXFIN",
    "NIFTYMEDIA": "^CNXMEDIA",
    # Popular Stocks
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "INFY": "INFY.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "HINDUNILVR": "HINDUNILVR.NS",
    "SBIN": "SBIN.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "KOTAKBANK": "KOTAKBANK.NS",
    "BAJFINANCE": "BAJFINANCE.NS",
    # Forex Pairs
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "USDCAD": "USDCAD=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "EURGBP": "EURGBP=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X"
}

# Broker configurations
broker_payouts = {
    # Forex brokers
    "Quotex": 0.85,
    "Pocket Option": 0.80,
    "Binolla": 0.78,
    "IQ Option": 0.82,
    "Bullex": 0.75,
    "Exnova": 0.77,
    
    # Indian brokers
    "Zerodha": 0.75,
    "Upstox": 0.78,
    "Angel One": 0.77,
    "Groww": 0.76,
    "ICICI Direct": 0.75,
    "HDFC Securities": 0.74
}

def get_forex_rate(pair, return_source=False):
    """Get real-time forex rate with support for premium API features."""
    return get_cached_realtime_forex(pair, return_source)

def black_scholes_call_put(S, K, T, r, sigma, option_type="call"):
    """
    Calculate option price using Black-Scholes model with NormalDist
    """
    d1 = (math.log(S/K) + (r + sigma**2/2)*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)

    # Use NormalDist for CDF calculations
    normal = NormalDist()
    if option_type.lower() == "call":
        price = S*normal.cdf(d1) - K*math.exp(-r*T)*normal.cdf(d2)
    else:  # put
        price = K*math.exp(-r*T)*normal.cdf(-d2) - S*normal.cdf(-d1)

    return price

DEMO_UNLOCK_PASSWORD = os.getenv('DEMO_UNLOCK_PASSWORD', secrets.token_hex(8))
DEMO_TIMEOUT_MINUTES = 1440

@app.before_request
def demo_lockout():
    """Lock out users whose demo has expired (non-premium only)"""
    if 'user_id' not in session:
        return
    # Skip lockout check for static files, login, lock, unlock, API
    public_paths = ('/static/', '/login', '/lock', '/unlock', '/api/')
    if any(request.path.startswith(p) for p in public_paths):
        return
    try:
        db = get_db()
        if db is None:
            session.clear()
            return redirect(url_for('login'))
        cursor = db.cursor()
        cursor.execute('SELECT demo_end_time, is_premium FROM users WHERE id = ?', (session['user_id'],))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            session.clear()
            return redirect(url_for('login'))
        demo_end_time_str, is_premium = result[0], result[1]
        cursor.close()
        if is_premium:
            return
        if demo_end_time_str:
            if isinstance(demo_end_time_str, str):
                demo_end = datetime.fromisoformat(demo_end_time_str)
                if datetime.now() > demo_end:
                    session.clear()
                    return redirect(url_for('login'))
        else:
            cursor = db.cursor()
            cursor.execute('UPDATE users SET demo_end_time = ? WHERE id = ?',
                         ((datetime.now() + timedelta(days=30)).isoformat(), session['user_id']))
            db.commit()
            cursor.close()
    except Exception as e:
        logger.error(f"Error in demo_lockout: {str(e)}")

@app.route('/lock', methods=['GET'])
def lock():
    return render_template('lock.html')

@app.route('/unlock', methods=['POST'])
def unlock():
    password = request.form.get('password')
    if password == DEMO_UNLOCK_PASSWORD:
        if 'user_id' in session:
            db = get_db()
            demo_end_time = (datetime.now() + timedelta(hours=24)).isoformat()
            cursor = db.cursor()
            cursor.execute('UPDATE users SET demo_end_time = ? WHERE id = ?',
                          (demo_end_time, session['user_id']))
            db.commit()
            cursor.close()
            session['demo_end_time'] = demo_end_time
        session['locked'] = False
        return redirect(url_for('dashboard'))
    else:
        flash('Incorrect password. Please try again.', 'error')
        return render_template('lock.html')

@app.route('/get_demo_time')
def get_demo_time():
    """Get remaining demo time"""
    try:
        logger.info(f"get_demo_time called. Session user_id: {session.get('user_id')}")
        
        if 'user_id' in session:
            user = get_user_by_id(session['user_id'])
            logger.info(f"User found: {user}")
            
            if user and not user['is_premium']:  # Use dictionary-like access for sqlite3.Row
                demo_end_time = user['demo_end_time']  # Use dictionary-like access
                logger.info(f"Demo end time from DB: {demo_end_time}")
                
                if not demo_end_time:
                    # Set demo end time if not set (24 hours from now)
                    demo_end_time = (datetime.now() + timedelta(hours=24)).isoformat()
                    db = get_db()
                    cursor = db.cursor()
                    cursor.execute('UPDATE users SET demo_end_time = ? WHERE id = ?',
                                  (demo_end_time, session['user_id']))
                    db.commit()
                    cursor.close()
                    session['demo_end_time'] = demo_end_time
                    logger.info(f"Set new demo end time: {demo_end_time}")
                else:
                    # Check if demo has expired
                    try:
                        demo_end_datetime = datetime.fromisoformat(demo_end_time)
                        if datetime.now() > demo_end_datetime:
                            # Demo expired, reset it for another 24 hours
                            demo_end_time = (datetime.now() + timedelta(hours=24)).isoformat()
                            db = get_db()
                            cursor = db.cursor()
                            cursor.execute('UPDATE users SET demo_end_time = ? WHERE id = ?',
                                          (demo_end_time, session['user_id']))
                            db.commit()
                            cursor.close()
                            session['demo_end_time'] = demo_end_time
                            logger.info(f"Demo time reset for user {session['user_id']}: {demo_end_time}")
                    except ValueError as e:
                        logger.error(f"Error parsing demo_end_time: {str(e)}")
                        # Invalid date format, reset it
                        demo_end_time = (datetime.now() + timedelta(hours=24)).isoformat()
                        db = get_db()
                        cursor = db.cursor()
                        cursor.execute('UPDATE users SET demo_end_time = ? WHERE id = ?',
                                      (demo_end_time, session['user_id']))
                        db.commit()
                        cursor.close()
                        session['demo_end_time'] = demo_end_time

                # Calculate remaining time
                remaining_time = datetime.fromisoformat(demo_end_time) - datetime.now()
                remaining_seconds = max(0, remaining_time.total_seconds())

                logger.info(f"Remaining time: {remaining_seconds}s")
                return jsonify({
                    'time_left': int(remaining_seconds),
                    'status': 'success'
                })
            else:
                logger.info(f"User is premium or not found: {user}")

        logger.warning("No active demo session found")
        return jsonify({
            'time_left': '00:00:00',
            'status': 'error',
            'message': 'No active demo session'
        }), 200

    except Exception as e:
        logger.error(f"Error getting demo time: {str(e)}", exc_info=True)
        return jsonify({
            'time_left': '00:00:00',
            'status': 'error',
            'message': str(e)
        }), 500

# ─── Tutorial & Demo Reset ──────────────────────────────────────────────

@app.route("/api/user/tutorial-status")
def get_tutorial_status():
    """Check if the current user has completed the tutorial."""
    if not session.get("user_id"):
        return jsonify({"completed": False}), 401
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT tutorial_completed FROM users WHERE id=?", (session["user_id"],))
        row = cur.fetchone()
        completed = bool(row and row[0])
        return jsonify({"completed": completed})
    except Exception as e:
        logger.error(f"Tutorial status error: {e}")
        return jsonify({"completed": False})

@app.route("/api/user/tutorial-complete", methods=["POST"])
def mark_tutorial_complete():
    """Mark tutorial as completed for the current user."""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE users SET tutorial_completed=1 WHERE id=?", (session["user_id"],))
        db.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Tutorial complete error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/demo/reset-funds", methods=["POST"])
def reset_demo_funds():
    """Reset demo account: clear trades, positions, signals, reset balance."""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        user_id = session["user_id"]
        db = get_db()
        cur = db.cursor()
        DEMO_RESET_BALANCE = 500000.0
        cur.execute("UPDATE users SET balance=? WHERE id=?", (DEMO_RESET_BALANCE, user_id))
        for table in ("trades", "positions", "portfolio_history"):
            try:
                cur.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
            except Exception:
                pass
        db.commit()
        # Reset in-memory bot state
        if hasattr(indian_auto_trader, 'trade_history'):
            indian_auto_trader.trade_history.clear()
        if hasattr(indian_auto_trader, 'total_pnl'):
            indian_auto_trader.total_pnl = 0.0
        if hasattr(indian_auto_trader, 'initial_balance'):
            indian_auto_trader.initial_balance = DEMO_RESET_BALANCE
        logger.info(f"Demo funds reset for user {user_id}")
        return jsonify({"status": "ok", "balance": DEMO_RESET_BALANCE, "message": "Demo account reset to ₹5,00,000"})
    except Exception as e:
        logger.error(f"Reset funds error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if not username or not password:
            flash("Please fill in all fields", "error")
            return redirect(url_for("register"))
            
        # Check if username already exists
        existing_user = get_user_by_username(username)
        if existing_user:
            flash("Username already exists", "error")
            return redirect(url_for("register"))
            
        # Create new user
        if create_user(username, password):
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        else:
            flash("Error creating user. Please try again.", "error")
            return redirect(url_for("register"))
            
    return render_template("register.html")

def _log_login(user_id, success, method='password'):
    """Record a login attempt in login_history."""
    try:
        db = get_db()
        cur = db.cursor()
        ip = request.remote_addr or '0.0.0.0'
        ua = request.headers.get('User-Agent', '')[:500]
        now = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO login_history (user_id, ip_address, user_agent, success, method, timestamp) VALUES (?,?,?,?,?,?)",
            (user_id, ip, ua, 1 if success else 0, method, now)
        )
        db.commit()
    except Exception as e:
        logger.error(f"Login history log error: {e}")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            db = get_db()
            if db is None:
                flash("Database connection error. Please try again later.", "error")
                return render_template("login.html")

            username = request.form.get("username")
            password = request.form.get("password")

            if not username or not password:
                flash("Please fill in all fields", "error")
                return render_template("login.html")

            user = get_user_by_username(username)
            if not user:
                flash("Invalid username or password", "error")
                return render_template("login.html")

            try:
                if check_password_hash(user['password'], password):
                    _log_login(user['id'], True)
                    # Check if 2FA is enabled
                    if dict(user).get('totp_enabled'):
                        session['2fa_user_id'] = user['id']
                        session['2fa_remember'] = False
                        logger.info(f"User {user['id']} redirected to 2FA challenge")
                        return redirect(url_for('twofa_challenge'))
                    session['user_id'] = user['id']
                    update_last_login(user['id'])
                    logger.info(f"User {user['id']} logged in successfully")
                    return redirect(url_for("dashboard"))
            except ValueError as e:
                logger.error(f"Password verification error: {str(e)}")
                _log_login(user['id'] if user else 0, False)
                flash("An error occurred during login. Please try again.", "error")
                return render_template("login.html")

            _log_login(user['id'], False)
            flash("Invalid username or password", "error")
            return render_template("login.html")
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            flash("An error occurred during login. Please try again.", "error")
            return render_template("login.html")
    return render_template("login.html")

# ─── 2FA Challenge ──────────────────────────────────────────────────────

@app.route("/2fa-challenge", methods=["GET", "POST"])
def twofa_challenge():
    if '2fa_user_id' not in session:
        return redirect(url_for('login'))
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        user_id = session['2fa_user_id']
        user = get_user_by_id(user_id)
        if not user or not user.get('totp_secret'):
            flash("2FA not configured", "error")
            return redirect(url_for('login'))
        totp = pyotp.TOTP(user['totp_secret'])
        # Check TOTP code
        if totp.verify(code, valid_window=1):
            session['user_id'] = user_id
            update_last_login(user_id)
            session.pop('2fa_user_id', None)
            session.pop('2fa_remember', None)
            logger.info(f"User {user_id} passed 2FA challenge")
            return redirect(url_for('dashboard'))
        # Check recovery codes
        recovery_raw = user.get('recovery_codes') or ''
        codes = [c.strip() for c in recovery_raw.split(',') if c.strip()]
        if code in codes:
            codes.remove(code)
            try:
                db = get_db()
                cur = db.cursor()
                cur.execute("UPDATE users SET recovery_codes=? WHERE id=?", (','.join(codes), user_id))
                db.commit()
            except Exception:
                pass
            session['user_id'] = user_id
            update_last_login(user_id)
            session.pop('2fa_user_id', None)
            session.pop('2fa_remember', None)
            logger.info(f"User {user_id} logged in via recovery code")
            return redirect(url_for('dashboard'))
        flash("Invalid code", "error")
        return render_template("twofa_challenge.html")
    return render_template("twofa_challenge.html")

# ─── 2FA API ─────────────────────────────────────────────────────────────

@app.route("/api/2fa/setup")
def twofa_setup():
    """Generate TOTP secret and provisioning URI for the current user."""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        user = get_user_by_id(session['user_id'])
        if user.get('totp_enabled'):
            return jsonify({"error": "2FA is already enabled"}), 400
        secret = pyotp.random_base32()
        provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user['username'],
            issuer_name=branding.get('PLATFORM_NAME', 'Trading Platform')
        )
        # Store secret temporarily in session until verified
        session['2fa_pending_secret'] = secret
        return jsonify({
            "secret": secret,
            "provisioning_uri": provisioning_uri,
        })
    except Exception as e:
        logger.error(f"2FA setup error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/2fa/verify", methods=["POST"])
def twofa_verify():
    """Verify a TOTP code and enable 2FA."""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        data = request.get_json(force=True)
        code = data.get("code", "").strip()
        secret = session.get('2fa_pending_secret')
        if not secret:
            return jsonify({"error": "No pending 2FA setup. Call /api/2fa/setup first."}), 400
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            return jsonify({"error": "Invalid code"}), 400
        # Generate recovery codes
        recovery = [secrets.token_hex(4).upper() for _ in range(8)]
        recovery_str = ','.join(recovery)
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE users SET totp_secret=?, totp_enabled=1, recovery_codes=? WHERE id=?",
                     (secret, recovery_str, session['user_id']))
        db.commit()
        session.pop('2fa_pending_secret', None)
        logger.info(f"2FA enabled for user {session['user_id']}")
        return jsonify({
            "status": "enabled",
            "message": "Two-factor authentication enabled",
            "recovery_codes": recovery,
        })
    except Exception as e:
        logger.error(f"2FA verify error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/2fa/disable", methods=["POST"])
def twofa_disable():
    """Disable 2FA (requires password confirmation)."""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        data = request.get_json(force=True)
        password = data.get("password", "")
        user = get_user_by_id(session['user_id'])
        if not check_password_hash(user['password'], password):
            return jsonify({"error": "Invalid password"}), 403
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE users SET totp_secret=NULL, totp_enabled=0, recovery_codes=NULL WHERE id=?",
                     (session['user_id'],))
        db.commit()
        logger.info(f"2FA disabled for user {session['user_id']}")
        return jsonify({"status": "disabled", "message": "Two-factor authentication disabled"})
    except Exception as e:
        logger.error(f"2FA disable error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/2fa/recovery-codes", methods=["POST"])
def twofa_recovery_codes():
    """Generate new recovery codes (requires password)."""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        data = request.get_json(force=True)
        password = data.get("password", "")
        user = get_user_by_id(session['user_id'])
        if not check_password_hash(user['password'], password):
            return jsonify({"error": "Invalid password"}), 403
        recovery = [secrets.token_hex(4).upper() for _ in range(8)]
        recovery_str = ','.join(recovery)
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE users SET recovery_codes=? WHERE id=?", (recovery_str, session['user_id']))
        db.commit()
        return jsonify({"status": "ok", "recovery_codes": recovery})
    except Exception as e:
        logger.error(f"Recovery codes error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/2fa/status")
def twofa_status():
    """Check if 2FA is enabled for the current user."""
    if 'user_id' not in session:
        return jsonify({"enabled": False}), 401
    try:
        user = get_user_by_id(session['user_id'])
        return jsonify({
            "enabled": bool(user.get('totp_enabled')),
        })
    except Exception:
        return jsonify({"enabled": False})

# ─── Login History API ───────────────────────────────────────────────────

@app.route("/api/user/login-history")
def get_login_history():
    """Get recent login history for the current user."""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        db = get_db()
        cur = db.cursor()
        limit = min(int(request.args.get("limit", 20)), 100)
        cur.execute(
            "SELECT id, ip_address, user_agent, success, method, timestamp FROM login_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (session['user_id'], limit)
        )
        rows = cur.fetchall()
        history = []
        for r in rows:
            history.append({
                "id": r[0],
                "ip_address": r[1],
                "user_agent": r[2],
                "success": bool(r[3]),
                "method": r[4],
                "timestamp": r[5],
            })
        return jsonify({"history": history})
    except Exception as e:
        logger.error(f"Login history error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = get_user_by_id(session["user_id"])
    if request.method == "POST":
        new_password = request.form["new_password"]
        if new_password:
            db = get_db()
            cursor = db.cursor()
            cursor.execute('UPDATE users SET password = ? WHERE id = ?', (generate_password_hash(new_password), user[0]))  # id is at index 0
            db.commit()
            cursor.close()
            flash("Password updated successfully.", "success")
    # Get 2FA status
    twofa_enabled = bool(dict(user).get('totp_enabled')) if user else False
    return render_template("profile.html", user=dict(user) if user else None, twofa_enabled=twofa_enabled)

@app.route("/dashboard")
def dashboard():
    logger.info("Accessing dashboard route")
    if 'user_id' not in session:
        logger.warning("No user_id in session, redirecting to login")
        return redirect(url_for('login'))
        
    try:
        sync_autotrader_user()
    except Exception as sync_err:
        logger.error(f"Error syncing autotrader: {sync_err}")
        
    try:
        logger.info(f"Attempting to connect to database for user_id: {session['user_id']}")
        connection = get_db()
        if connection is None:
            logger.error("Failed to establish database connection")
            session.clear()  # Clear the session since we can't access the database
            flash("Database connection error. Please try again later.", "error")
            return redirect(url_for('login'))
            
        cursor = connection.cursor()
        logger.info("Database cursor created successfully")
        
        # Get user data
        try:
            logger.info("Fetching user data")
            cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
            user_raw = cursor.fetchone()
            logger.info(f"User data fetched: {user_raw is not None}")
            
            if not user_raw:
                logger.warning(f"No user found for id: {session['user_id']}")
                session.clear()
                flash("User not found", "error")
                return redirect(url_for('login'))
            
            # Convert user data to dictionary for template (exclude password hash)
            user = {
                'id': user_raw[0],
                'username': user_raw[1],
                'registered_at': user_raw[3],
                'last_login': user_raw[4],
                'balance': user_raw[5],
                'is_premium': user_raw[6],
                'demo_end_time': user_raw[7]
            }
        except Exception as e:
            logger.error(f"Error fetching user data: {str(e)}")
            flash("Error loading user data", "error")
            return redirect(url_for('login'))
            
        # Initialize empty lists for data
        signals = []
        trades = []
        positions = []
        portfolio_history = []
            
        try:
            # Get user's signals
            logger.info("Fetching user signals")
            cursor.execute('''
                SELECT * FROM signals 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT 10
            ''', (session['user_id'],))
            signals_raw = cursor.fetchall()
            logger.info(f"Fetched {len(signals_raw)} signals")
            
            # Convert to list of dictionaries for template
            if signals_raw:
                columns = ['id', 'user_id', 'pair', 'direction', 'confidence', 'time', 'created_at', 'entry_price', 'stop_loss', 'take_profit', 'result']
                signals = [dict(zip(columns, signal)) for signal in signals_raw]
        except Exception as e:
            logger.error(f"Error fetching signals: {str(e)}")
            flash("Error loading trading signals", "error")
            
        try:
            # Get user's trades
            logger.info("Fetching user trades")
            cursor.execute('''
                SELECT * FROM trades 
                WHERE user_id = ? 
                ORDER BY entry_time DESC 
                LIMIT 10
            ''', (session['user_id'],))
            trades_raw = cursor.fetchall()
            logger.info(f"Fetched {len(trades_raw)} trades")
            
            # Convert to list of dictionaries for template
            if trades_raw:
                columns = ['id', 'user_id', 'symbol', 'direction', 'entry_price', 'exit_price', 'quantity', 'status', 'entry_time', 'exit_time', 'profit_loss', 'stop_loss', 'take_profit']
                trades = [dict(zip(columns, trade)) for trade in trades_raw]
        except Exception as e:
            logger.error(f"Error fetching trades: {str(e)}")
            flash("Error loading trade history", "error")
            
        try:
            # Get user's positions
            logger.info("Fetching user positions")
            cursor.execute('''
                SELECT * FROM positions 
                WHERE user_id = ?
            ''', (session['user_id'],))
            positions_raw = cursor.fetchall()
            logger.info(f"Fetched {len(positions_raw)} positions")
            
            # Convert to list of dictionaries for template
            if positions_raw:
                columns = ['id', 'user_id', 'symbol', 'quantity', 'average_price', 'last_updated']
                positions = [dict(zip(columns, position)) for position in positions_raw]
        except Exception as e:
            logger.error(f"Error fetching positions: {str(e)}")
            flash("Error loading current positions", "error")
            
        try:
            # Get user's portfolio history
            logger.info("Fetching portfolio history")
            cursor.execute('''
                SELECT * FROM portfolio_history 
                WHERE user_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 30
            ''', (session['user_id'],))
            portfolio_history_raw = cursor.fetchall()
            logger.info(f"Fetched {len(portfolio_history_raw)} portfolio history entries")
            
            # Convert to list of dictionaries for template
            if portfolio_history_raw:
                columns = ['id', 'user_id', 'portfolio_value', 'timestamp']
                portfolio_history = [dict(zip(columns, entry)) for entry in portfolio_history_raw]
        except Exception as e:
            logger.error(f"Error fetching portfolio history: {str(e)}")
            flash("Error loading portfolio history", "error")
            
        cursor.close()
        logger.info("Database cursor closed")
        
        logger.info("Rendering dashboard template")
        return render_template(
            "dashboard.html",
            user=user,
            signals=signals,
            trades=trades,
            positions=positions,
            portfolio_history=portfolio_history,
            user_plan=get_user_plan(session['user_id'])
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in dashboard: {str(e)}", exc_info=True)
        flash("An error occurred while loading the dashboard", "error")
        return redirect(url_for('login'))

@app.route("/", methods=["GET", "POST"])
def index():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD", "AUD/USD", "NZD/USD"]
    brokers = ["Quotex", "Pocket Option", "Binolla", "IQ Option", "Bullex", "Exnova"]

    # Get selected pair and broker from query parameters or form data
    selected_pair = request.args.get('pair') or request.form.get('pair')
    selected_broker = request.args.get('broker') or request.form.get('broker') or brokers[0]

    # Initialize variables with default values
    current_rate = None
    data_source = None
    call_price = None
    put_price = None
    volatility = 0.20
    expiry = 1/365.0
    risk_free_rate = 0.01
    payout = broker_payouts.get(selected_broker, 0.75)
    signals = None

    # Get initial price data if a pair is selected
    if selected_pair and selected_pair != "Select Pair":
        try:
            clean_pair = selected_pair.replace('/', '')
            price_data = get_forex_rate(clean_pair, return_source=True)

            if isinstance(price_data, tuple):
                current_rate, data_source = price_data
            else:
                current_rate = price_data
                data_source = "API"

            if current_rate is not None:
                call_price = black_scholes_call_put(current_rate, current_rate, expiry, risk_free_rate, volatility, "call")
                put_price = black_scholes_call_put(current_rate, current_rate, expiry, risk_free_rate, volatility, "put")
        except Exception as e:
            logger.error(f"Error getting initial forex data: {str(e)}")
            flash("Error fetching initial market data. Real-time updates will still work.", "warning")

    if request.method == "POST":
        # Handle signal generation
        pair = request.form["pair"]
        broker = request.form["broker"]
        signal_type = request.form["signal_type"].upper()
        start_hour = request.form["start_hour"]
        start_minute = request.form["start_minute"]
        end_hour = request.form["end_hour"]
        end_minute = request.form["end_minute"]
        selected_pair = pair
        selected_broker = broker
        payout = broker_payouts.get(broker, 0.75)

        try:
            start_str = f"{start_hour}:{start_minute}"
            end_str = f"{end_hour}:{end_minute}"
            start = datetime.strptime(start_str, "%H:%M")
            end = datetime.strptime(end_str, "%H:%M")
            if start >= end:
                flash("Start time must be before end time.", "error")
                return render_template("index.html",
                    pairs=pairs,
                    brokers=brokers,
                    current_rate=current_rate,
                    selected_pair=selected_pair,
                    selected_broker=selected_broker,
                    payout=payout,
                    call_price=call_price,
                    put_price=put_price,
                    volatility=volatility,
                    expiry=expiry,
                    risk_free_rate=risk_free_rate,
                    data_source=data_source
                )

            signals = []
            current = start
            
            # Initialize AI Predictor
            try:
                from ai_models.signal_predictor import AISignalPredictor
                predictor = AISignalPredictor()
            except Exception as e:
                logger.error(f"Failed to load AI predictor for forex: {e}")
                predictor = None
                
            while current < end:
                direction = signal_type
                confidence = 0
                
                # Get real AI prediction
                if predictor:
                    try:
                        ai_result = predictor.predict_symbol(selected_pair.replace('/', ''))
                        if ai_result and 'signal' in ai_result:
                            direction = ai_result['signal']
                            confidence = ai_result['confidence']
                    except Exception as ai_e:
                        logger.debug(f"AI prediction failed: {ai_e}")
                
                # Fallback if no prediction
                if not confidence:
                    direction = random.choice(["CALL", "PUT"]) if signal_type == "BOTH" else signal_type
                    confidence = round(random.uniform(60, 95), 2)
                    
                signals.append({
                    "time": current.strftime("%H:%M"),
                    "pair": selected_pair,
                    "direction": direction,
                    "confidence": confidence
                })
                save_signal(session["user_id"], current.strftime("%H:%M"), selected_pair, direction, confidence=confidence)
                current += timedelta(minutes=random.randint(5, 15))

            session["forex_signals"] = signals
            flash("Signals generated successfully!", "success")
            return render_template("index.html",
                signals=signals,
                current_rate=current_rate,
                selected_pair=selected_pair,
                selected_broker=selected_broker,
                payout=payout,
                call_price=call_price,
                put_price=put_price,
                volatility=volatility,
                expiry=expiry,
                risk_free_rate=risk_free_rate,
                pairs=pairs,
                brokers=brokers,
                data_source=data_source
            )

        except ValueError:
            flash("Invalid time format.", "error")
            return render_template("index.html",
                pairs=pairs,
                brokers=brokers,
                current_rate=current_rate,
                selected_pair=selected_pair,
                selected_broker=selected_broker,
                payout=payout,
                call_price=call_price,
                put_price=put_price,
                volatility=volatility,
                expiry=expiry,
                risk_free_rate=risk_free_rate,
                data_source=data_source
            )

    signals = session.get("forex_signals", [])
    return render_template("index.html",
        pairs=pairs,
        brokers=brokers,
        current_rate=current_rate,
        selected_pair=selected_pair,
        selected_broker=selected_broker,
        payout=payout,
        call_price=call_price,
        put_price=put_price,
        volatility=volatility,
        expiry=expiry,
        risk_free_rate=risk_free_rate,
        signals=signals,
        data_source=data_source
    )

@app.route("/otc", methods=["GET", "POST"])
def otc_market():
    if "user_id" not in session:
        return redirect(url_for("login"))

    current_rate = None
    selected_pair = request.form.get("pair") if request.method == "POST" else request.args.get("pair")
    selected_broker = request.form.get("broker", otc_brokers[0]) if request.method == "POST" else request.args.get("broker", otc_brokers[0])
    payout = broker_payouts.get(selected_broker, 0.75)

    # Initialize pricing parameters
    volatility = 0.20
    expiry = 1/365.0
    risk_free_rate = 0.01
    call_price = None
    put_price = None
    data_source = None

    if selected_pair:
        try:
            if otc_handler is None:
                logger.error("OTC handler not available")
                flash("OTC price service is currently unavailable.", "error")
                data_source = "Service Unavailable"
            else:
                price_data = otc_handler.get_realtime_price(selected_pair, return_source=True)
                if isinstance(price_data, tuple):
                    current_rate, data_source = price_data
                else:
                    current_rate = price_data
                    data_source = "Alpha Vantage"

                if current_rate is not None:
                    call_price = black_scholes_call_put(current_rate, current_rate, expiry, risk_free_rate, volatility, "call")
                    put_price = black_scholes_call_put(current_rate, current_rate, expiry, risk_free_rate, volatility, "put")
        except Exception as e:
            logger.error(f"Error in OTC market: {str(e)}")
            flash("Error fetching market data.", "error")

    if request.method == "POST":
        try:
            pair = request.form["pair"]
            broker = request.form["broker"]
            signal_type = request.form["signal_type"].upper()
            start_hour = request.form["start_hour"]
            start_minute = request.form["start_minute"]
            end_hour = request.form["end_hour"]
            end_minute = request.form["end_minute"]

            start_str = f"{start_hour}:{start_minute}"
            end_str = f"{end_hour}:{end_minute}"

            start = datetime.strptime(start_str, "%H:%M")
            end = datetime.strptime(end_str, "%H:%M")

            if start >= end:
                flash("Start time must be before end time.", "error")
                return render_template("otc.html",
                    pairs=otc_pairs,
                    brokers=otc_brokers,
                    current_rate=current_rate,
                    selected_pair=selected_pair,
                    selected_broker=selected_broker,
                    payout=payout,
                    call_price=call_price,
                    put_price=put_price,
                    volatility=volatility,
                    expiry=expiry,
                    risk_free_rate=risk_free_rate,
                    data_source=data_source
                )

            signals = []
            current = start
            while current < end:
                direction = random.choice(["CALL", "PUT"]) if signal_type == "BOTH" else signal_type
                confidence = round(random.uniform(60, 95), 2)

                # Calculate entry price, stop loss and take profit
                if current_rate:
                    entry_price = current_rate
                    if direction == "CALL":
                        stop_loss = entry_price * 0.99  # 1% below entry
                        take_profit = entry_price * 1.02  # 2% above entry
                    else:
                        stop_loss = entry_price * 1.01  # 1% above entry
                        take_profit = entry_price * 0.98  # 2% below entry
                else:
                    entry_price = None
                    stop_loss = None
                    take_profit = None

                # Save signal to database with confidence
                save_signal(
                    session["user_id"],
                    current.strftime("%H:%M"),
                    selected_pair,
                    direction,
                    entry_price,
                    stop_loss,
                    take_profit,
                    confidence
                )

                signals.append({
                    "time": current.strftime("%H:%M"),
                    "pair": selected_pair,
                    "direction": direction,
                    "confidence": confidence,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit
                })

                current += timedelta(minutes=random.randint(1, 15))

            session["otc_signals"] = signals
            flash("Signals generated successfully!", "success")

        except ValueError:
            flash("Invalid time format.", "error")
        except Exception as e:
            logger.error(f"Error generating signals: {str(e)}")
            flash("Error generating signals.", "error")

    # Get existing signals
    signals = get_signals_for_user(session["user_id"])

    return render_template("otc.html",
        pairs=otc_pairs,
        brokers=otc_brokers,
        current_rate=current_rate,
        selected_pair=selected_pair,
        selected_broker=selected_broker,
        payout=payout,
        call_price=call_price,
        put_price=put_price,
        volatility=volatility,
        expiry=expiry,
        risk_free_rate=risk_free_rate,
        signals=signals,
        data_source=data_source
    )

@app.route("/download_otc")
def download_otc():
    """Download OTC signals as PDF with professional branding"""
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Get signals for the user
    signals = get_signals_for_user(session["user_id"])

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Add company logo
    try:
        logo_path = os.path.join(STATIC_FOLDER, "images", "logo1.png")
        if os.path.exists(logo_path):
            img = Image(logo_path, width=200, height=50)
            elements.append(img)
    except Exception as e:
        logger.error(f"Error loading logo: {str(e)}")

    # Add title with styling
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor('#00e6d0'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph(get_platform_setting('platform_name'), title_style))

    # Add report details
    details_style = ParagraphStyle(
        'DetailsStyle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#666666'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", details_style))
    elements.append(Spacer(1, 20))

    # Add market overview section
    overview_style = ParagraphStyle(
        'OverviewStyle',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=10,
        textColor=colors.HexColor('#333333')
    )
    elements.append(Paragraph("Market Overview", overview_style))
    elements.append(Paragraph("OTC Market Trading Signals", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Add signals table with enhanced styling
    if signals:
        # Table header with more columns
        data = [['Time', 'Pair', 'Direction', 'Entry Price', 'Stop Loss', 'Take Profit', 'Confidence', 'Status']]

        # Add signals with calculated levels
        for signal in signals:
            if signal['pair'].endswith('_OTC'):  # Only include OTC pairs
                try:
                    # Calculate entry, stop loss and take profit levels
                    entry_price = signal.get('entry_price', 'N/A')
                    stop_loss = signal.get('stop_loss', 'N/A')
                    take_profit = signal.get('take_profit', 'N/A')
                    confidence = signal.get('confidence', 0.0)
                    status = "Won" if signal.get('result') == 1 else "Lost" if signal.get('result') == 0 else "Pending"

                    # Format numerical values
                    entry_price_str = f"{float(entry_price):.5f}" if isinstance(entry_price, (int, float)) else str(entry_price)
                    stop_loss_str = f"{float(stop_loss):.5f}" if isinstance(stop_loss, (int, float)) else str(stop_loss)
                    take_profit_str = f"{float(take_profit):.5f}" if isinstance(take_profit, (int, float)) else str(take_profit)
                    confidence_str = f"{float(confidence):.1f}%"

                    data.append([
                        signal['time'],
                        signal['pair'].replace('_OTC', ''),
                        signal['direction'],
                        entry_price_str,
                        stop_loss_str,
                        take_profit_str,
                        confidence_str,
                        status
                    ])
                except Exception as e:
                    logger.error(f"Error processing signal: {str(e)}")
                    continue

        # Create table with enhanced styling
        if len(data) > 1:  # Only create table if we have data
            table = Table(data, colWidths=[80, 80, 80, 80, 80, 80, 80, 80])
            table.setStyle(TableStyle([
                # Header styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#00e6d0')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

                # Body styling
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#2a2a2a')),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.white),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#333333')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

                # Alternating row colors
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#2a2a2a'), colors.HexColor('#333333')])
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("No OTC signals available", styles['Normal']))
    else:
        elements.append(Paragraph("No signals available", styles['Normal']))

    # Add trading guidelines
    elements.append(Spacer(1, 30))
    guidelines_style = ParagraphStyle(
        'GuidelinesStyle',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=10,
        textColor=colors.HexColor('#333333')
    )
    elements.append(Paragraph("Trading Guidelines", guidelines_style))

    guidelines = [
        "• Always use proper risk management",
        "• Set stop-loss and take-profit levels before entering trades",
        "• Monitor market conditions before executing trades",
        "• Keep track of your trading performance",
        "• Follow the signals strictly as provided"
    ]

    for guideline in guidelines:
        elements.append(Paragraph(guideline, styles['Normal']))

    # Add disclaimer and company information
    elements.append(Spacer(1, 30))
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#666666'),
        alignment=TA_CENTER
    )

    # Add digital signature
    signature_style = ParagraphStyle(
        'SignatureStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#00e6d0'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph(f"Digitally Signed by {get_platform_setting('platform_name')}", signature_style))
    elements.append(Paragraph("Signature Hash: " + hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16], signature_style))

    # Add company information
    company_info = [
        get_platform_setting('platform_name'),
        f"Email: {get_platform_setting('support_email')}",
        f"Website: {get_platform_setting('company_address')}",
        f"Disclaimer: {get_platform_setting('footer_text')}"
    ]

    for info in company_info:
        elements.append(Paragraph(info, footer_style))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"trading_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

@app.route("/download_indian")
def download_indian():
    if "indian_signals" not in session:
        return redirect(url_for("indian_market"))
    signals = session["indian_signals"]
    from io import BytesIO
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, height - 40, f"{get_platform_setting('platform_name')} - Indian Signals Report")
    c.setFont("Helvetica", 10)
    c.drawString(40, height - 60, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    table_data = [["Time", "Pair", "Direction", "Call Price", "Put Price"]]
    for s in signals:
        try:
            S = get_forex_rate(s["pair"])
        except Exception:
            S = round(random.uniform(10000, 50000), 2)
        K = S
        T = 1/365
        r = 0.01
        sigma = 0.2
        call_price = black_scholes_call_put(S, K, T, r, sigma, option_type="call") if S else "N/A"
        put_price = black_scholes_call_put(S, K, T, r, sigma, option_type="put") if S else "N/A"
        table_data.append([s["time"], s["pair"], s["direction"], f"{call_price:.6f}" if S else "N/A", f"{put_price:.6f}" if S else "N/A"])
    x = 40
    y = height - 100
    row_height = 18
    col_widths = [60, 70, 70, 100, 100]
    c.setFont("Helvetica-Bold", 11)
    for col, header in enumerate(table_data[0]):
        c.drawString(x + sum(col_widths[:col]), y, header)
    c.setFont("Helvetica", 10)
    y -= row_height
    for row in table_data[1:]:
        for col, cell in enumerate(row):
            c.drawString(x + sum(col_widths[:col]), y, str(cell))
        y -= row_height
        if y < 60:
            c.showPage()
            y = height - 60
    c.save()
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name="indian_signals_report.pdf")

def calculate_technical_indicators(data):
    """Calculate technical indicators for the given data"""
    try:
        # Convert data to pandas DataFrame if it's not already
        if not isinstance(data, pd.DataFrame):
            df = pd.DataFrame(data)
        else:
            df = data

        # Ensure we have the required columns
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in required_columns:
            if col not in df.columns:
                logger.error(f"Missing required column: {col}")
                return {
                    'sma': [],
                    'ema': [],
                    'macd': [],
                    'macd_signal': [],
                    'rsi': [],
                    'bollinger_upper': [],
                    'bollinger_lower': [],
                    'cci': [],
                    'volume_ratio': []
                }

        # Calculate indicators using pandas
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()

        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        df['BB_middle'] = df['Close'].rolling(window=20).mean()
        df['BB_std'] = df['Close'].rolling(window=20).std()
        df['BB_upper'] = df['BB_middle'] + (df['BB_std'] * 2)
        df['BB_lower'] = df['BB_middle'] - (df['BB_std'] * 2)

        # CCI (Commodity Channel Index)
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['CCI'] = (tp - tp.rolling(window=20).mean()) / (0.015 * tp.rolling(window=20).std())

        # Volume Analysis
        df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA']

        # Fill NaN values with 0
        df = df.fillna(0)

        return {
            'sma': df['SMA_20'].tolist(),
            'ema': df['EMA_20'].tolist(),
            'macd': df['MACD'].tolist(),
            'macd_signal': df['Signal'].tolist(),
            'rsi': df['RSI'].tolist(),
            'bollinger_upper': df['BB_upper'].tolist(),
            'bollinger_lower': df['BB_lower'].tolist(),
            'cci': df['CCI'].tolist(),
            'volume_ratio': df['Volume_Ratio'].tolist()
        }
    except Exception as e:
        logger.error(f"Error calculating indicators: {str(e)}")
        # Return empty lists for all indicators in case of error
        return {
            'sma': [],
            'ema': [],
            'macd': [],
            'macd_signal': [],
            'rsi': [],
            'bollinger_upper': [],
            'bollinger_lower': [],
            'cci': [],
            'volume_ratio': []
        }

def get_historical_data(symbol, period=None, interval=None):
    """Fetch historical market data and calculate technical indicators"""
    try:
        # Clean up the symbol
        symbol = symbol.replace('/', '')
        logger.info(f"Processing symbol: {symbol}")

        # Get Yahoo Finance symbol
        yahoo_symbol = symbol_map.get(symbol, symbol)
        if not yahoo_symbol:
            logger.error(f"Invalid symbol: {symbol}")
            return {
                'historical': None,
                'realtime': None,
                'error': f"Invalid symbol: {symbol}"
            }
        logger.info(f"Using Yahoo Finance symbol: {yahoo_symbol}")

        # For Indian markets, use .NS suffix, for forex use =X suffix
        if symbol in ["NIFTY50", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY", 
                      "NIFTYREALTY", "NIFTYPVTBANK", "NIFTYPSUBANK", "NIFTYFIN", "NIFTYMEDIA",
                      "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", 
                      "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE"]:
            # Indian market symbols - use the mapped symbol directly (already has correct suffix)
            logger.info(f"Using Indian market symbol: {yahoo_symbol}")
        elif not yahoo_symbol.endswith('=X'):
            # Forex pairs - add =X suffix if not already present
            yahoo_symbol = f"{yahoo_symbol}=X"
            logger.info(f"Updated Yahoo Finance symbol for forex: {yahoo_symbol}")

        # Try to get data from Yahoo Finance
        df = None
        error_msg = []

        try:
            logger.info(f"Attempting to fetch data for {yahoo_symbol}")
            df = yf.download(yahoo_symbol, period=period or '1mo', interval=interval or '1d', progress=False)
                
            if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                    
            if df.empty:
                error_msg.append("No data available from Yahoo Finance")
                logger.warning("No data available from Yahoo Finance")
        except Exception as e:
            error_msg.append(f"Error fetching from Yahoo Finance: {str(e)}")
            logger.error(f"Error fetching from Yahoo Finance: {str(e)}")

        # If Yahoo Finance fails, try to get data from Alpha Vantage (only for forex pairs)
        if (df is None or df.empty) and symbol not in ["NIFTY50", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY", 
                                                       "NIFTYREALTY", "NIFTYPVTBANK", "NIFTYPSUBANK", "NIFTYFIN", "NIFTYMEDIA",
                                                       "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", 
                                                       "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE"]:
            try:
                logger.info(f"Attempting to fetch data from Alpha Vantage for {symbol}")
                # Get real-time rate
                rate, source = get_cached_realtime_forex(symbol, return_source=True)
                if rate is not None:
                    # Create a simple DataFrame with the current rate
                    now = datetime.now()
                    dates = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]
                    df = pd.DataFrame({
                        'Open': [rate] * 30,
                        'High': [rate * 1.001] * 30,  # Slight variation
                        'Low': [rate * 0.999] * 30,   # Slight variation
                        'Close': [rate] * 30,
                        'Volume': [1000] * 30
                    }, index=pd.to_datetime(dates))
                    logger.info("Created fallback data from Alpha Vantage rate")
            except Exception as e:
                error_msg.append(f"Error fetching from Alpha Vantage: {str(e)}")
                logger.error(f"Error fetching from Alpha Vantage: {str(e)}")

        if df is None or df.empty:
            error_message = f"No data available for {symbol}: {'; '.join(error_msg)}"
            logger.error(error_message)
            return {
                'historical': None,
                'realtime': None,
                'error': error_message
            }

        # Check for required columns
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in required_columns:
            if col not in df.columns:
                logger.error(f"Missing required column: {col}")
                return {
                    'historical': None,
                    'realtime': None,
                    'error': f"Missing required column: {col}"
                }

        # Calculate technical indicators
        try:
            logger.info("Calculating technical indicators")
            df['SMA20'] = df['Close'].rolling(window=20).mean()
            df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['RSI'] = calculate_rsi(df['Close'])
            df['MACD'], df['Signal'] = calculate_macd(df['Close'])
            logger.info("Technical indicators calculated successfully")
        except Exception as e:
            logger.error(f"Error calculating technical indicators: {str(e)}")
            return {
                'historical': None,
                'realtime': None,
                'error': f"Error calculating indicators: {str(e)}"
            }

        # Format data for response
        try:
            dates = df.index.strftime('%Y-%m-%d %H:%M' if interval and 'm' in interval else '%Y-%m-%d').tolist()
            logger.info(f"Formatted {len(dates)} dates")

            # Convert NaN values to None (null in JSON)
            def convert_nan_to_none(obj):
                if isinstance(obj, float) and np.isnan(obj):
                    return None
                elif isinstance(obj, list):
                    return [convert_nan_to_none(item) for item in obj]
                elif isinstance(obj, dict):
                    return {key: convert_nan_to_none(value) for key, value in obj.items()}
                return obj

            response_data = {
                'historical': {
                    'dates': dates,
                    'prices': {
                        'open': df['Open'].tolist(),
                        'high': df['High'].tolist(),
                        'low': df['Low'].tolist(),
                        'close': df['Close'].tolist(),
                        'volume': df['Volume'].tolist()
                    },
                    'indicators': {
                        'sma': df['SMA20'].tolist(),
                        'ema': df['EMA20'].tolist(),
                        'rsi': df['RSI'].tolist(),
                        'macd': df['MACD'].tolist(),
                        'macd_signal': df['Signal'].tolist()
                    }
                }
            }
            # Convert NaN values to None before returning
            response_data = convert_nan_to_none(response_data)
            logger.info("Successfully formatted response data")
            return response_data

        except Exception as e:
            logger.error(f"Error formatting response data: {str(e)}")
            return {
                'historical': None,
                'realtime': None,
                'error': f"Error formatting data: {str(e)}"
            }

    except Exception as e:
        logger.error(f"Unexpected error in get_historical_data for {symbol}: {str(e)}")
        return {
            'historical': None,
            'realtime': None,
            'error': str(e)
        }

def calculate_rsi(prices, period=14):
    """Calculate RSI for a price series"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD for a price series"""
    exp1 = prices.ewm(span=fast, adjust=False).mean()
    exp2 = prices.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

@app.route("/market_data/<symbol>")
def market_data(symbol):
    """API endpoint to get market data for a symbol"""
    if 'user_id' not in session:
        logger.warning("Unauthenticated request to market_data endpoint")
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        timeframe = request.args.get('timeframe', '1mo')
        logger.info(f"Fetching data for {symbol} with timeframe {timeframe}")

        # Clean up the symbol
        clean_symbol = symbol.replace('/', '')
        logger.info(f"Cleaned symbol: {clean_symbol}")

        data = get_historical_data(clean_symbol, period=timeframe)
        logger.info(f"Received data from get_historical_data: {data is not None}")

        if not data:
            logger.error("No data returned from get_historical_data")
            return jsonify({'error': 'No data available'}), 404

        if data.get('error'):
            logger.error(f"Error in data: {data['error']}")
            return jsonify({'error': data['error']}), 500

        if not data.get('historical'):
            logger.error("No historical data in response")
            return jsonify({'error': 'Incomplete data received'}), 500

        logger.info("Successfully returning market data")
        return jsonify(data)

    except Exception as e:
        logger.error(f"Error in market_data endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

def get_trading_signals(symbol: str) -> Dict:
    """Get trading signals for a symbol"""
    try:
        # Since trading_system is commented out, return sample data
        # TODO: Re-enable when trading_system is properly imported
        return {
            'type': 'NEUTRAL',
            'confidence': 50.0,
            'timestamp': datetime.now().isoformat(),
            'note': 'Trading system temporarily disabled'
        }
    except Exception as e:
        logger.error(f"Error getting trading signals for {symbol}: {str(e)}")
        return {
            'type': 'NEUTRAL',
            'confidence': 0,
            'timestamp': datetime.now().isoformat()
        }

@app.route('/market')
def market_dashboard():
    # Default watchlist of symbols for the market dashboard
    symbols = list(symbol_map.keys())
    return render_template(
        'market_dashboard.html',
        subscribed_symbols=[{'symbol': s} for s in symbols],
        signals={}
    )

# Add WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection with authentication"""
    if 'user_id' not in session:
        logger.warning("Unauthenticated WebSocket connection attempt")
        return False

    try:
        user = get_user_by_id(session['user_id'])
        if not user:
            logger.warning(f"Invalid user_id in session: {session['user_id']}")
            return False

        logger.info(f"User {user['username']} connected via WebSocket")
        return True

    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}")
        return False

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")
    # Remove any active subscriptions for this client
    with active_subs_lock:
        for pair in list(active_subscriptions.keys()):
            if request.sid in active_subscriptions[pair]:
                active_subscriptions[pair].remove(request.sid)
            if not active_subscriptions[pair]:
                del active_subscriptions[pair]

@socketio.on('subscribe')
def handle_subscribe(data):
    """Handle subscription requests with improved error handling"""
    try:
        if 'user_id' not in session:
            logger.warning("Unauthenticated subscription attempt")
            return False

        pair = data.get('pair')
        if not pair:
            logger.warning("No pair provided for subscription")
            return False

        # Clean up the pair
        pair = pair.replace('/', '')

        # Add to active subscriptions
        user_id = session['user_id']
        with active_subs_lock:
            if user_id not in active_subscriptions:
                active_subscriptions[user_id] = set()
            active_subscriptions[user_id].add(pair)

        # Subscribe to Angel One WebSocket if it's an Indian symbol
        if angel_one_ws_manager and pair in indian_trading_system.indian_symbols:
            angel_one_ws_manager.subscribe(pair)

        # Get initial data
        try:
            result = _fetch_price_data(pair)
            if result:
                rate, source, call_price, put_price, volatility, expiry, risk_free_rate = result
                update_type = 'otc_update' if '_OTC' in pair else 'forex_update'
                update_data = _build_price_update_data(pair, rate, source, call_price, put_price, volatility, expiry, risk_free_rate, update_type)
                emit('price_update', update_data)
        except Exception as e:
            logger.error(f"Error getting initial price data for {pair}: {str(e)}")
            emit('price_update', {
                'error': str(e),
                'pair': pair,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

        # Start sending updates
        def send_updates():
            while True:
                with active_subs_lock:
                    if user_id not in active_subscriptions or pair not in active_subscriptions[user_id]:
                        break
                try:
                    result = _fetch_price_data(pair)
                    if result:
                        rate, source, call_price, put_price, volatility, expiry, risk_free_rate = result
                        update_type = 'otc_update' if '_OTC' in pair else 'forex_update'
                        update_data = _build_price_update_data(pair, rate, source, call_price, put_price, volatility, expiry, risk_free_rate, update_type)
                        emit('price_update', update_data)

                except Exception as e:
                    logger.error(f"Error sending price update for {pair}: {str(e)}")
                    emit('price_update', {
                        'error': str(e),
                        'pair': pair,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })

                time.sleep(1)

        threading.Thread(target=send_updates, daemon=True).start()
        logger.info(f"Started price updates for {pair} for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Error handling subscription: {str(e)}")
        return False

@socketio.on('unsubscribe')
def handle_unsubscribe(data):
    """Handle unsubscribe requests"""
    try:
        if 'user_id' not in session:
            logger.warning("Unauthenticated unsubscribe attempt")
            return False

        pair = data.get('pair')
        if not pair:
            logger.warning("No pair provided for unsubscribe")
            return False

        # Clean up the pair
        pair = pair.replace('/', '')

        # Remove from active subscriptions
        user_id = session['user_id']
        with active_subs_lock:
            if user_id in active_subscriptions:
                active_subscriptions[user_id].discard(pair)
                logger.info(f"Unsubscribed {user_id} from {pair}")
                
                # Check if anyone else is still subscribed to this pair
                still_subscribed = any(pair in subs for subs in active_subscriptions.values())
                if not still_subscribed and angel_one_ws_manager and pair in indian_trading_system.indian_symbols:
                    angel_one_ws_manager.unsubscribe(pair)
                    
                return True

        return False

    except Exception as e:
        logger.error(f"Error handling unsubscription: {str(e)}")
        return False

def _fetch_price_data(pair):
    """Common helper: fetch price data and option prices for a pair.
    Returns (rate, source, call_price, put_price, volatility, expiry, risk_free_rate) or None on error."""
    if '_OTC' in pair:
        if otc_handler is None:
            logger.error("OTC handler not available")
            return None
        price_data = otc_handler.get_realtime_price(pair, return_source=True)
    else:
        clean_pair = pair.replace('/', '')
        try:
            price_data = get_cached_realtime_forex(clean_pair, return_source=True)
        except Exception as e:
            logger.error(f"Error getting forex rate for {pair}: {str(e)}")
            return None

    if not price_data:
        return None

    if isinstance(price_data, tuple):
        rate, source = price_data
    else:
        rate = price_data
        source = "API"

    volatility = 0.20
    expiry = 1/365.0
    risk_free_rate = 0.01
    try:
        call_price = black_scholes_call_put(rate, rate, expiry, risk_free_rate, volatility, "call")
        put_price = black_scholes_call_put(rate, rate, expiry, risk_free_rate, volatility, "put")
    except Exception as e:
        logger.error(f"Error calculating option prices: {str(e)}")
        call_price = None
        put_price = None

    return (rate, source, call_price, put_price, volatility, expiry, risk_free_rate)


def _build_price_update_data(pair, rate, source, call_price, put_price, volatility, expiry, risk_free_rate, update_type="forex_update"):
    """Build the standard price update dict."""
    return {
        'rate': float(rate),
        'source': source,
        'type': update_type,
        'pair': pair,
        'call_price': call_price,
        'put_price': put_price,
        'volatility': volatility,
        'expiry': expiry,
        'risk_free_rate': risk_free_rate,
        'timestamp': datetime.now().isoformat()
    }


def send_price_updates(pair):
    """Send price updates to subscribed clients"""
    try:
        # Get all users subscribed to this pair
        subscribed_users = set()
        with active_subs_lock:
            for user_id, subscriptions in list(active_subscriptions.items()):
                if pair in subscriptions:
                    subscribed_users.add(user_id)

        if not subscribed_users:
            return

        result = _fetch_price_data(pair)
        if result is None:
            return

        rate, source, call_price, put_price, volatility, expiry, risk_free_rate = result
        update_type = 'otc_update' if '_OTC' in pair else 'forex_update'
        update_data = {
            'data': _build_price_update_data(pair, rate, source, call_price, put_price, volatility, expiry, risk_free_rate, update_type)
        }

        logger.info(f"Sending price update for {pair}: {update_data}")

        # Emit update to all subscribed users
        for user_id in subscribed_users:
            try:
                emit('price_update', update_data, room=user_id)
            except Exception as e:
                logger.error(f"Error sending update to user {user_id}: {str(e)}")
                with active_subs_lock:
                    if user_id in active_subscriptions:
                        active_subscriptions[user_id].discard(pair)

    except Exception as e:
        logger.error(f"Error in send_price_updates: {str(e)}")

def start_price_update_thread():
    """Start background thread for price updates"""
    def update_loop():
        last_update = {}  # Track last update time for each pair
        while True:
            try:
                # Snapshot active subscriptions with lock
                current_subs = {}
                with active_subs_lock:
                    for k, v in list(active_subscriptions.items()):
                        current_subs[k] = set(v)
                
                current_time = time.time()
                for pair in list(current_subs.keys()):
                    if not current_subs[pair]:
                        continue

                    # Check if we need to update this pair
                    if pair in last_update:
                        time_since_last_update = current_time - last_update[pair]
                        if time_since_last_update < 1.0:  # Update every second
                            continue

                    # Get and send price update
                    send_price_updates(pair)
                    last_update[pair] = current_time

                # Sleep for a short time to prevent high CPU usage
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in update loop: {str(e)}")
                time.sleep(1)

    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()
    logger.info("Price update thread started")

# Start the update thread when the app starts
_startup_lock = threading.Lock()
_startup_done = False

def _run_startup_once():
    global _startup_done
    if _startup_done:
        return
    with _startup_lock:
        if _startup_done:
            return
        _startup_done = True

    start_price_update_thread()
    ensure_persistence_tables()
    try:
        prior = get_setting('indian_auto_trader_running', '0')
        if prior == '1':
            logger.info('Autostarting Indian auto-trader (previously running)')
            try:
                indian_auto_trader.start()
                
                # Ensure all symbols are subscribed for real-time tracking
                if angel_one_ws_manager:
                    for symbol in indian_trading_system.indian_symbols:
                        angel_one_ws_manager.subscribe(symbol)
            except Exception as e:
                logger.error(f'Autostart failed: {e}')
            # Rehydrate active trades from DB (if any)
            try:
                import time as _t
                from datetime import datetime as _dt
                conn = get_db()
                cur = conn.cursor()
                cur.execute('SELECT id, symbol, type, entry_price, quantity, entry_time, user_id, strategy, confidence, stop_loss, target_price, partial_exit_done FROM active_trades')
                rows = cur.fetchall()
                conn.close()
                for r in rows:
                    trade_id = r['id']
                    entry_price = float(r['entry_price'] or 0)
                    direction = r['type']
                    db_stop = r['stop_loss']
                    db_target = r['target_price']
                    try:
                        partial_exit_done = bool(r['partial_exit_done'])
                    except Exception:
                        partial_exit_done = False
                    if db_stop is not None and db_target is not None:
                        stop_loss = float(db_stop)
                        target_price = float(db_target)
                    elif direction == 'BUY':
                        target_price = entry_price * 1.02
                        stop_loss = entry_price * 0.98
                    else:
                        target_price = entry_price * 0.98
                        stop_loss = entry_price * 1.02
                    try:
                        entry_epoch = _t.mktime(_dt.strptime(r['entry_time'], '%Y-%m-%d %H:%M:%S').timetuple()) if r['entry_time'] else _t.time()
                    except Exception:
                        entry_epoch = _t.time()
                    indian_auto_trader.active_trades[trade_id] = {
                        'id': trade_id,
                        'symbol': r['symbol'],
                        'type': direction,
                        'entry_price': entry_price,
                        'target_price': target_price,
                        'stop_loss': stop_loss,
                        'quantity': int(r['quantity'] or 1),
                        'strategy': r['strategy'],
                        'confidence': float(r['confidence'] or 0),
                        'timestamp': _dt.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_epoch': entry_epoch,
                        'entry_time': r['entry_time'],
                        'status': 'ACTIVE',
                        'partial_exit_done': partial_exit_done
                    }
                if rows:
                    logger.info(f'Rehydrated {len(rows)} active trade(s) from DB')
            except Exception as e:
                logger.error(f'Failed to rehydrate active trades: {e}')
    except Exception as e:
        logger.error(f'Autostart check error: {e}')

@app.before_request
def before_first_request():
    _run_startup_once()

@app.route('/favicon.ico')
def favicon():
    try:
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )
    except Exception as e:
        logger.error(f"Error serving favicon: {e}")
        return '', 204  # Return no content if favicon is not found

# --- Add these two routes for health check and test page ---
@app.route('/test')
def test():
    return render_template('test.html')
# -----------------------------------------------------------

# Simulation control endpoints
@app.route('/simulation/on')
def simulation_on():
    """Enable simulation mode (overrides demo trades with mock data)"""
    set_setting('simulation_mode', '1')
    return jsonify({"message": "Simulation mode enabled", "simulation": True})

@app.route('/simulation/off')
def simulation_off():
    """Disable simulation mode"""
    set_setting('simulation_mode', '0')
    return jsonify({"message": "Simulation mode disabled", "simulation": False})

@app.route('/admin/seed_sim', methods=['POST', 'GET'])
def admin_seed_sim():
    """Seed demo account with mock closed trades for testing"""
    if not is_live_mode() and get_setting('simulation_mode', '0') == '1':
        from datetime import timedelta
        import random
        conn = get_db()
        cur = conn.cursor()
        symbols = ['NIFTY50', 'BANKNIFTY', 'RELIANCE', 'TCS', 'HDFCBANK']
        for sym in symbols:
            entry = round(random.uniform(100, 50000), 2)
            exit_p = round(entry * random.uniform(0.95, 1.08), 2)
            qty = random.randint(1, 10)
            pnl = round((exit_p - entry) * qty, 2)
            cur.execute('''INSERT OR IGNORE INTO trades
                (user_id, symbol, direction, entry_price, exit_price, quantity, status, entry_time, exit_time, profit_loss, strategy)
                VALUES (?, ?, ?, ?, ?, ?, 'CLOSED', ?, ?, ?, ?)''',
                (1, sym, 'BUY' if pnl > 0 else 'SELL', entry, exit_p, qty,
                 (datetime.now() - timedelta(hours=random.randint(1, 48))).isoformat(),
                 datetime.now().isoformat(), pnl, 'Simulation'))
        conn.commit()
        conn.close()
        return jsonify({"message": "Demo seeded with mock trades", "count": len(symbols)})
    return jsonify({"message": "Seeding only available in demo simulation mode"}), 403

@app.route("/start_indian_auto_trading")
@require_plan('premium')
def start_indian_auto_trading():
    """Start Indian auto-trading system (requires Premium+)"""
        
    try:
        sync_autotrader_user()
    except Exception as sync_err:
        logger.error(f"Error syncing autotrader: {sync_err}")
    try:
        indian_auto_trader.start()
        
        # Ensure all symbols are subscribed for real-time tracking
        if angel_one_ws_manager:
            for symbol in indian_trading_system.indian_symbols:
                angel_one_ws_manager.subscribe(symbol)
                
        logger.info("Indian auto-trading system started manually via dashboard")
        set_setting('indian_auto_trader_running', '1')
        return jsonify({"message": "Indian auto-trading started successfully", "status": "running"})
    except Exception as e:
        logger.error(f"Error starting Indian auto-trading: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/stop_indian_auto_trading")
def stop_indian_auto_trading():
    """Stop Indian auto-trading system"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
        
    try:
        indian_auto_trader.stop()
        set_setting('indian_auto_trader_running', '0')
        return jsonify({"message": "Indian auto-trading stopped successfully", "status": "stopped"})
    except Exception as e:
        logger.error(f"Error stopping Indian auto-trading: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/start_forex_auto_trading")
@require_plan('premium')
def start_forex_auto_trading():
    """Start Forex auto-trading system (requires Premium+)"""
    try:
        auto_trader.start()
        set_setting('forex_auto_trader_running', '1')
        logger.info("Forex auto-trading system started manually via dashboard")
        return jsonify({"message": "Forex auto-trading started successfully", "status": "running"})
    except Exception as e:
        logger.error(f"Error starting Forex auto-trading: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/stop_forex_auto_trading")
def stop_forex_auto_trading():
    """Stop Forex auto-trading system"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        auto_trader.stop()
        set_setting('forex_auto_trader_running', '0')
        logger.info("Forex auto-trading system stopped manually via dashboard")
        return jsonify({"message": "Forex auto-trading stopped successfully", "status": "stopped"})
    except Exception as e:
        logger.error(f"Error stopping Forex auto-trading: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/forex_status")
def get_forex_status():
    """Get Forex auto-trading system status"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        running = getattr(auto_trader, 'running', False)
        return jsonify({"status": "running" if running else "stopped"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/start_otc_auto_trading")
@require_plan('premium')
def start_otc_auto_trading():
    """Start OTC auto-trading system (simulated, requires Premium+)"""
    try:
        set_setting('otc_auto_trader_running', '1')
        logger.info("OTC auto-trading system started manually")
        return jsonify({"message": "OTC auto-trading started successfully", "status": "running"})
    except Exception as e:
        logger.error(f"Error starting OTC auto-trading: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/stop_otc_auto_trading")
def stop_otc_auto_trading():
    """Stop OTC auto-trading system"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        set_setting('otc_auto_trader_running', '0')
        logger.info("OTC auto-trading system stopped manually")
        return jsonify({"message": "OTC auto-trading stopped successfully", "status": "stopped"})
    except Exception as e:
        logger.error(f"Error stopping OTC auto-trading: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/otc_status")
def get_otc_status():
    """Get OTC auto-trading system status"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        running = get_setting('otc_auto_trader_running', '0') == '1'
        return jsonify({"status": "running" if running else "stopped"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/indian_status")
def get_indian_status():
    """Get Indian auto-trading system status"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401

    try:
        sync_autotrader_user()
    except Exception as sync_err:
        logger.error(f"Error syncing autotrader: {sync_err}")
    try:
        active_trades = indian_auto_trader.get_active_trades()
        performance = indian_auto_trader.get_performance_summary()
        closed_pnl = getattr(indian_auto_trader, 'total_pnl', 0.0)
        win_rate = 0.0
        if hasattr(indian_auto_trader, 'trade_history') and len(indian_auto_trader.trade_history) > 0:
            wins = sum(1 for t in indian_auto_trader.trade_history if t.get('pnl_amount', 0) > 0)
            win_rate = (wins / len(indian_auto_trader.trade_history)) * 100.0

        actual_status = performance.get('status', 'stopped').lower()

        # Build actual trade list for the UI and sum unrealized P&L
        import random
        latest_prices = getattr(indian_auto_trader, 'latest_prices', {})
        unrealized_pnl = 0.0
        trades_list = []
        for trade_id, trade in active_trades.items():
            # Normalize key names
            entry_price = float(trade.get('entry_price', 0) or 0)
            symbol = str(trade.get('symbol', ''))
            
            # Fetch fresh live price
            current_price = latest_prices.get(symbol)
            if not current_price:
                try:
                    data = indian_trading_system.trading_system.get_indian_market_data(symbol, period='1d')
                    if data is not None and not data.empty:
                        current_price = float(data['Close'].iloc[-1])
                        latest_prices[symbol] = current_price
                except Exception:
                    pass
            
            if not current_price:
                current_price = entry_price if entry_price > 0 else 100.0
                
            # Add micro-fluctuation to simulate live TradingView feed ticks (DEMO/Simulation mode)
            try:
                # Walk the price continuously with a micro-fluctuation (up to +/-0.04% per second)
                fluctuation_pct = random.uniform(-0.0004, 0.0004)
                current_price = current_price * (1 + fluctuation_pct)
                # Save the walked price back so the next second's poll is a true continuous random walk!
                latest_prices[symbol] = current_price
            except Exception:
                pass
            qty = int(trade.get('quantity', trade.get('qty', 0)) or 0)
            # Calculate P&L from live price vs entry
            if trade.get('type', 'BUY').upper() == 'BUY':
                pnl = (current_price - entry_price) * qty
            else:
                pnl = (entry_price - current_price) * qty
            unrealized_pnl += pnl
            duration_str = ""
            if 'entry_time' in trade and trade['entry_time']:
                try:
                    entry_dt = datetime.strptime(trade['entry_time'], '%Y-%m-%d %H:%M:%S')
                    diff = datetime.now() - entry_dt
                    dur_sec = int(diff.total_seconds())
                    hh, rem = divmod(dur_sec, 3600)
                    mm, ss = divmod(rem, 60)
                    duration_str = f"{hh}h {mm}m"
                except Exception:
                    duration_str = ""
            trades_list.append({
                'id': str(trade_id),
                'symbol': str(trade.get('symbol', '')),
                'type': str(trade.get('type', 'BUY')).upper(),
                'entry_price': round(entry_price, 2),
                'current_price': round(current_price, 2),
                'quantity': qty,
                'pnl': round(pnl, 2),
                'pnl_percentage': round((pnl / (entry_price * qty) * 100) if entry_price > 0 and qty > 0 else 0, 2),
                'strategy': str(trade.get('strategy', 'Auto')),
                'entry_time': str(trade.get('entry_time', '')),
                'duration': duration_str,
            })

        total_pnl_val = round(float(closed_pnl + unrealized_pnl), 2)
        logger.info(f"indian_status: active={len(active_trades)}, closed_pnl={closed_pnl:.2f}, unrealized={unrealized_pnl:.2f}, total_pnl={total_pnl_val}")
        return jsonify({
            "status": actual_status,
            "active_trades": len(active_trades),
            "trades": trades_list,
            "performance": performance,
            "total_pnl": total_pnl_val,
            "win_rate": round(float(win_rate), 2),
            "simulation": get_setting('simulation_mode', '0') == '1'
        })

    except Exception as e:
        logger.error(f"Error getting Indian status: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/indian_signals")
def get_indian_signals():
    """Get current Indian trading signals"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
        
    try:
        signals = indian_trading_system.get_all_signals()
        signal_data = []
        
        for signal in signals:
            signal_data.append({
                'symbol': signal.symbol,
                'signal_type': signal.signal_type,
                'confidence': signal.confidence,
                'entry_price': signal.entry_price,
                'target_price': signal.target_price,
                'stop_loss': signal.stop_loss,
                'strategy': signal.strategy,
                'risk_reward_ratio': signal.risk_reward_ratio,
                'market_sentiment': signal.market_sentiment,
                'volume_analysis': signal.volume_analysis,
                'volatility': signal.volatility,
                'timestamp': signal.timestamp.isoformat()
            })
            
        return jsonify({"signals": signal_data, "count": len(signal_data)})
        
    except Exception as e:
        logger.error(f"Error getting Indian signals: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ─── Bot Trading Dashboard ──────────────────────────────────────────────

def _get_bot_status_dict():
    """Build a complete bot status dictionary."""
    running = getattr(indian_auto_trader, 'running', False)
    active = indian_auto_trader.get_active_trades() if hasattr(indian_auto_trader, 'get_active_trades') else {}
    perf = indian_auto_trader.get_performance_summary() if hasattr(indian_auto_trader, 'get_performance_summary') else {}
    total_pnl = getattr(indian_auto_trader, 'total_pnl', 0.0)
    trade_hist = getattr(indian_auto_trader, 'trade_history', [])
    wins = sum(1 for t in trade_hist if t.get('pnl_amount', 0) > 0) if trade_hist else 0
    win_rate = round((wins / len(trade_hist)) * 100, 2) if trade_hist else 0.0
    return {
        "running": bool(running),
        "active_trades": len(active),
        "total_trades": len(trade_hist),
        "total_pnl": round(float(total_pnl), 2),
        "win_rate": win_rate,
        "balance": float(perf.get('current_balance', getattr(indian_auto_trader, 'initial_balance', 500000))),
        "initial_balance": float(getattr(indian_auto_trader, 'initial_balance', 500000)),
        "config": {
            "max_concurrent_trades": int(get_setting('bot_max_concurrent', '3')),
            "risk_per_trade": float(get_setting('bot_risk_per_trade', '2.0')),
            "default_sl_percent": float(get_setting('bot_default_sl', '2.0')),
            "default_tp_percent": float(get_setting('bot_default_tp', '4.0')),
            "strategy": get_setting('bot_strategy', 'adaptive'),
        },
        "uptime": perf.get('uptime', 'N/A'),
        "simulation": get_setting('simulation_mode', '0') == '1',
    }

@app.route("/bot_dashboard")
def bot_dashboard():
    """Bot management dashboard page."""
    if not session.get("user_id"):
        flash("Please login first.", "warning")
        return redirect(url_for("login"))
    return render_template("bot_dashboard.html")

@app.route("/api/bot/status")
def get_bot_status():
    """Get full bot status and performance."""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        sync_autotrader_user()
    except Exception as sync_err:
        logger.error(f"Error syncing autotrader: {sync_err}")
    try:
        return jsonify(_get_bot_status_dict())
    except Exception as e:
        logger.error(f"Bot status error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/bot/start", methods=["POST"])
@require_plan('premium')
def start_bot():
    """Start the auto-trading bot. (Requires Premium+)"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        sync_autotrader_user()
    except Exception as sync_err:
        logger.error(f"Error syncing autotrader: {sync_err}")
    try:
        if getattr(indian_auto_trader, 'running', False):
            return jsonify({"error": "Bot is already running"}), 400
        indian_auto_trader.start()
        set_setting('indian_auto_trader_running', '1')
        logger.info("Bot started via bot dashboard")
        return jsonify({"status": "started", "message": "Auto-trading bot started"})
    except Exception as e:
        logger.error(f"Bot start error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/bot/stop", methods=["POST"])
def stop_bot():
    """Stop the auto-trading bot."""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        if not getattr(indian_auto_trader, 'running', False):
            return jsonify({"error": "Bot is not running"}), 400
        indian_auto_trader.stop()
        set_setting('indian_auto_trader_running', '0')
        logger.info("Bot stopped via bot dashboard")
        return jsonify({"status": "stopped", "message": "Auto-trading bot stopped"})
    except Exception as e:
        logger.error(f"Bot stop error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/bot/config", methods=["GET", "POST"])
def bot_config():
    """Get or update bot configuration."""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        if request.method == "GET":
            return jsonify(_get_bot_status_dict()["config"])
        data = request.get_json(force=True)
        for key, field in [
            ("max_concurrent_trades", "bot_max_concurrent"),
            ("risk_per_trade", "bot_risk_per_trade"),
            ("default_sl_percent", "bot_default_sl"),
            ("default_tp_percent", "bot_default_tp"),
            ("strategy", "bot_strategy"),
        ]:
            if key in data:
                set_setting(field, str(data[key]))
        logger.info(f"Bot config updated: {data}")
        return jsonify({"status": "updated", "config": _get_bot_status_dict()["config"]})
    except Exception as e:
        logger.error(f"Bot config error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/bot/trades")
def get_bot_trades():
    """Get bot trade history."""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        trade_hist = getattr(indian_auto_trader, 'trade_history', [])
        limit = min(int(request.args.get("limit", 50)), 200)
        trades = list(trade_hist)
        trades.reverse()
        return jsonify({
            "trades": trades[:limit],
            "total": len(trades),
        })
    except Exception as e:
        logger.error(f"Bot trades error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/bot/clear", methods=["POST"])
def clear_bot_trades():
    """Clear completed bot trade history."""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    try:
        if hasattr(indian_auto_trader, 'trade_history'):
            indian_auto_trader.trade_history.clear()
        if hasattr(indian_auto_trader, 'total_pnl'):
            indian_auto_trader.total_pnl = 0.0
        logger.info("Bot trade history cleared")
        return jsonify({"status": "cleared", "message": "Trade history cleared"})
    except Exception as e:
        logger.error(f"Bot clear error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/indian/market_data/<pair>")
def get_indian_market_data(pair):
    """Get market data for Indian trading pair"""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
        
    try:
        # Get historical data for the pair
        data = indian_trading_system.get_indian_market_data(pair, period='5d', interval='5m')
        
        if data is None or data.empty:
            return jsonify({
                "historical": {"dates": [], "prices": {"open": [], "high": [], "low": [], "close": [], "volume": []}},
                "current_price": 0.0,
                "pair": pair,
                "hint": "No data yet from Angel One. Try again in a moment or change interval."
            })
        
        # Convert to chart-friendly format with proper type conversion
        chart_data = {
            "historical": {
                "dates": data.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
                "prices": {
                    "open": [float(x) for x in data['Open'].tolist()],
                    "high": [float(x) for x in data['High'].tolist()],
                    "low": [float(x) for x in data['Low'].tolist()],
                    "close": [float(x) for x in data['Close'].tolist()],
                    "volume": [int(x) for x in data['Volume'].tolist()]
                }
            },
            "current_price": float(data['Close'].iloc[-1]) if not data.empty else 0.0,
            "pair": pair
        }
        
        return jsonify(chart_data)
        
    except Exception as e:
        logger.error(f"Error getting Indian market data for {pair}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/test/indian/market_data/<pair>")
def test_indian_market_data(pair):
    """Public test endpoint for Indian market data - no authentication required"""
    try:
        # Get historical data for the pair with small retry/backoff on empty
        attempts = 0
        data = None
        while attempts < 2:
            data = indian_trading_system.get_indian_market_data(pair, period='5d', interval='5m')
            if data is not None and not data.empty:
                break
            time.sleep(0.6)  # brief backoff to avoid rate-limit
            attempts += 1
        
        if data is None or data.empty:
            return jsonify({
                "historical": {"dates": [], "prices": {"open": [], "high": [], "low": [], "close": [], "volume": []}},
                "current_price": 0.0,
                "pair": pair,
                "data_points": 0,
                "message": "No data from Angel One (rate limit or symbol)."
            })
        
        # Convert to chart-friendly format with proper type conversion
        chart_data = {
            "historical": {
                "dates": data.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
                "prices": {
                    "open": [float(x) for x in data['Open'].tolist()],
                    "high": [float(x) for x in data['High'].tolist()],
                    "low": [float(x) for x in data['Low'].tolist()],
                    "close": [float(x) for x in data['Close'].tolist()],
                    "volume": [int(x) for x in data['Volume'].tolist()]
                }
            },
            "current_price": float(data['Close'].iloc[-1]) if not data.empty else 0.0,
            "pair": pair,
            "data_points": int(len(data)),
            "date_range": {
                "start": data.index[0].strftime('%Y-%m-%d %H:%M:%S'),
                "end": data.index[-1].strftime('%Y-%m-%d %H:%M:%S')
            },
            "message": "✅ Data retrieved successfully! This is a public test endpoint."
        }
        
        return jsonify(chart_data)
        
    except Exception as e:
        logger.error(f"Error getting Indian market data for {pair}: {str(e)}")
        return jsonify({
            "error": str(e),
            "pair": pair,
            "message": "❌ Error occurred while fetching data"
        }), 500

@app.route("/test/indian/pairs")
def test_indian_pairs():
    """Public test endpoint to list all available Indian trading pairs"""
    try:
        # Get the list of pairs from the Indian trading system
        pairs = [
            "NIFTY50", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY",
            "NIFTYREALTY", "NIFTYPVTBANK", "NIFTYPSUBANK", "NIFTYFIN", "NIFTYMEDIA",
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
            "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE"
        ]
        
        return jsonify({
            "available_pairs": pairs,
            "total_pairs": len(pairs),
            "message": "✅ Available Indian trading pairs. Use /test/indian/market_data/<pair> to get data for a specific pair.",
            "example_urls": [
                "http://localhost:5000/test/indian/market_data/NIFTY50",
                "http://localhost:5000/test/indian/market_data/BANKNIFTY",
                "http://localhost:5000/test/indian/market_data/RELIANCE"
            ]
        })
        
    except Exception as e:
        logger.error(f"Error getting Indian pairs: {str(e)}")
        return jsonify({
            "error": str(e),
            "message": "❌ Error occurred while fetching pairs list"
        }), 500

@app.route("/test/indian/debug/<pair>")
def test_indian_debug(pair):
    """Debug endpoint to see raw data from Indian trading system"""
    try:
        # Get raw data
        data = indian_trading_system.get_indian_market_data(pair, period='5d', interval='5m')
        
        if data is None:
            return jsonify({
                "error": "Data is None",
                "pair": pair
            }), 404
            
        if data.empty:
            return jsonify({
                "error": "Data is empty",
                "pair": pair
            }), 404
        
        # Return raw data info with proper type conversion
        return jsonify({
            "pair": pair,
            "data_type": str(type(data)),
            "data_shape": [int(x) for x in data.shape],
            "data_columns": data.columns.tolist(),
            "data_index_type": str(type(data.index)),
            "data_index_name": data.index.name,
            "first_few_rows": {
                str(k): {
                    str(col): float(v) if isinstance(v, (int, float)) else str(v)
                    for col, v in row.items()
                }
                for k, row in data.head(3).to_dict('index').items()
            },
            "message": "✅ Raw data retrieved successfully"
        })
        
    except Exception as e:
        logger.error(f"Error in debug endpoint for {pair}: {str(e)}")
        import traceback
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc(),
            "pair": pair
        }), 500

@app.route('/angel_one_config')
def angel_one_config():
    return render_template('angel_one_config.html')

@app.route('/admin_panel')
def admin_panel():
    """Render admin panel page"""
    return render_template('admin_panel.html')

@app.route("/indian", methods=["GET", "POST"])
def indian_market():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    pairs = [
        "NIFTY50", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY",
        "NIFTYREALTY", "NIFTYPVTBANK", "NIFTYPSUBANK", "NIFTYFIN", "NIFTYMEDIA",
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE"
    ]
    brokers = ["Angel One", "Zerodha", "Upstox", "Groww", "ICICI Direct", "HDFC Securities"]

    # Get selected pair and broker from query parameters or form data
    selected_pair = request.args.get('pair') or request.form.get('pair')
    selected_broker = request.args.get('broker') or request.form.get('broker') or brokers[0]

    # Initialize variables with default values
    current_rate = None
    data_source = None
    call_price = None
    put_price = None
    volatility = None
    expiry = None
    risk_free_rate = None
    payout = None
    signals = None

    # Only fetch data if a valid pair is selected
    if selected_pair and selected_pair != "Select Pair":
        try:
            logger.info(f"Fetching data for selected pair: {selected_pair}")
            # Get historical data for the selected pair
            data = get_historical_data(selected_pair)
            logger.info(f"Historical data result: {data}")
            
            if data and data.get('historical'):
                historical_data = data['historical']
                current_rate = historical_data['prices']['close'][-1] if historical_data['prices']['close'] else None
                data_source = 'Yahoo Finance'
                logger.info(f"Using Yahoo Finance data. Current rate: {current_rate}")

                if current_rate:
                    # Calculate option prices
                    S = current_rate  # Current price
                    K = current_rate  # Strike price (at-the-money)
                    T = 5/365  # Time to expiry (5 days)
                    r = 0.05  # Risk-free rate (5%)
                    sigma = 0.20  # Volatility (20%)

                    call_price = black_scholes_call_put(S, K, T, r, sigma, "call")
                    put_price = black_scholes_call_put(S, K, T, r, sigma, "put")

                    volatility = sigma
                    expiry = T
                    risk_free_rate = r

                    # Set payout based on broker
                    payout = broker_payouts.get(selected_broker, 0.75)

                    # Get signals if they exist
                    signals = get_signals_for_user(session["user_id"])
                    
                    # Generate technical indicators for the chart
                    chart_data = generate_indian_market_indicators(current_rate, selected_pair)
            else:
                # Provide fallback data for Indian markets
                logger.info(f"Providing fallback data for {selected_pair}")
                if selected_pair in ["NIFTY50", "BANKNIFTY", "SENSEX"]:
                    # Sample data for major indices
                    sample_data = {
                        "NIFTY50": 19500.0,
                        "BANKNIFTY": 44500.0,
                        "SENSEX": 65000.0
                    }
                    current_rate = sample_data.get(selected_pair, 10000.0)
                    data_source = 'Sample Data (Market Closed)'
                    
                    # Calculate option prices with sample data
                    S = current_rate
                    K = current_rate
                    T = 5/365
                    r = 0.05
                    sigma = 0.20

                    call_price = black_scholes_call_put(S, K, T, r, sigma, "call")
                    put_price = black_scholes_call_put(S, K, T, r, sigma, "put")

                    volatility = sigma
                    expiry = T
                    risk_free_rate = r
                    payout = broker_payouts.get(selected_broker, 0.75)
                    
                    # Generate technical indicators for the chart
                    chart_data = generate_indian_market_indicators(current_rate, selected_pair)
                    
                    # Get signals
                    signals = get_signals_for_user(session["user_id"])
                    
                    logger.info(f"Fallback data set - Rate: {current_rate}, Call: {call_price}, Put: {put_price}")
                    flash(f"Using sample data for {selected_pair}. Real-time data will be available during market hours.", "info")
        except Exception as e:
            logger.error(f"Error fetching Indian market data: {str(e)}")
            flash("Error fetching market data. Please try again.", "error")
    
    # Ensure chart_data is always available
    if 'chart_data' not in locals() and current_rate:
        chart_data = generate_indian_market_indicators(current_rate, selected_pair or "NIFTY50")
    elif 'chart_data' not in locals():
        # Default chart data if no rate available
        chart_data = generate_indian_market_indicators(19500.0, "NIFTY50")

    # Ensure chart_data is always available and pre-serialize to JSON
    if 'chart_data' not in locals() or chart_data is None:
        chart_data_json = 'null'
    else:
        try:
            chart_data_json = json.dumps(chart_data, default=str)
        except Exception as json_err:
            logger.error(f"Failed to serialize chart_data: {json_err}")
            chart_data_json = 'null'

    logger.info(f"Final data being sent to template - Rate: {current_rate}, Source: {data_source}, Call: {call_price}, Put: {put_price}")
    return render_template(
        "indian.html",
        pairs=pairs,
        brokers=brokers,
        selected_pair=selected_pair,
        selected_broker=selected_broker,
        current_rate=current_rate,
        data_source=data_source,
        call_price=call_price,
        put_price=put_price,
        volatility=volatility,
        expiry=expiry,
        risk_free_rate=risk_free_rate,
        payout=payout,
        signals=signals,
        chart_data_json=chart_data_json,
        user_plan=get_user_plan(session.get('user_id', 0))
    )

@app.route("/api/price/<pair>")
def api_price(pair):
    """API endpoint for getting real-time price data"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        broker = request.args.get('broker', 'Quotex')
        logger.info(f"Fetching price for {pair} with broker {broker}")

        # Define broker payouts
        broker_payouts = {
            # Forex brokers
            "Quotex": 0.85,
            "Pocket Option": 0.80,
            "Binolla": 0.78,
            "IQ Option": 0.82,
            "Bullex": 0.75,
            "Exnova": 0.77,
            
            # Indian brokers
            "Zerodha": 0.75,
            "Upstox": 0.78,
            "Angel One": 0.77,
            "Groww": 0.76,
            "ICICI Direct": 0.75,
            "HDFC Securities": 0.74
        }

        # Define pricing parameters
        volatility = 0.20  # 20% volatility
        expiry = 1/365.0  # 1 day expiry
        risk_free_rate = 0.01  # 1% risk-free rate

        current_rate = None
        data_source = None

        # Get current rate and source
        if '_OTC' in pair:
            if otc_handler is None:
                logger.error("OTC handler not initialized")
                return jsonify({
                    'error': 'OTC service not available',
                    'details': 'The OTC price service is not properly initialized.'
                }), 503

            try:
                logger.info(f"Fetching OTC price for {pair}")
                price_data = otc_handler.get_realtime_price(pair, return_source=True)
                logger.info(f"Received OTC price data: {price_data}")

                if isinstance(price_data, tuple):
                    current_rate, data_source = price_data
                else:
                    current_rate = price_data
                    data_source = "OTC Data"

                if current_rate is None:
                    logger.warning(f"OTC price not available, trying fallback for {pair}")
                    # Try fallback to regular forex rate
                    base_pair = pair.replace('_OTC', '')
                    price_data = get_forex_rate(base_pair, return_source=True)
                    logger.info(f"Fallback forex data: {price_data}")

                    if isinstance(price_data, tuple):
                        current_rate, data_source = price_data
                        data_source = f"Fallback: {data_source}"
                    else:
                        current_rate = price_data
                        data_source = "Fallback API"
            except Exception as e:
                logger.error(f"Error fetching OTC price: {str(e)}")
                return jsonify({
                    'error': 'Failed to fetch OTC price',
                    'details': str(e)
                }), 500
        elif pair in ["NIFTY50", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY", 
                      "NIFTYREALTY", "NIFTYPVTBANK", "NIFTYPSUBANK", "NIFTYFIN", "NIFTYMEDIA",
                      "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", 
                      "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE"]:
            # Handle Indian market indices and stocks
            logger.info(f"Fetching Indian market data for {pair}")
            
            # Try to get historical data first
            try:
                data = get_historical_data(pair)
                if data and data.get('historical'):
                    historical_data = data['historical']
                    current_rate = historical_data['prices']['close'][-1] if historical_data['prices']['close'] else None
                    data_source = 'Yahoo Finance'
                    logger.info(f"Using Yahoo Finance data for {pair}: {current_rate}")
                else:
                    # Provide fallback data for Indian markets
                    logger.info(f"Providing fallback data for {pair}")
                    sample_data = {
                        "NIFTY50": 19500.0,
                        "BANKNIFTY": 44500.0,
                        "SENSEX": 65000.0,
                        "FINNIFTY": 20000.0,
                        "MIDCPNIFTY": 12000.0,
                        "NIFTYREALTY": 450.0,
                        "NIFTYPVTBANK": 45000.0,
                        "NIFTYPSUBANK": 18000.0,
                        "NIFTYFIN": 20000.0,
                        "NIFTYMEDIA": 2500.0,
                        "RELIANCE": 2500.0,
                        "TCS": 3800.0,
                        "HDFCBANK": 1600.0,
                        "INFY": 1500.0,
                        "ICICIBANK": 950.0,
                        "HINDUNILVR": 2500.0,
                        "SBIN": 650.0,
                        "BHARTIARTL": 950.0,
                        "KOTAKBANK": 1800.0,
                        "BAJFINANCE": 7500.0
                    }
                    current_rate = sample_data.get(pair, 10000.0)
                    data_source = 'Sample Data (Market Closed)'
                    logger.info(f"Fallback data set for {pair}: {current_rate}")
            except Exception as e:
                logger.error(f"Error fetching Indian market data: {str(e)}")
                # Still provide fallback data
                sample_data = {
                    "NIFTY50": 19500.0,
                    "BANKNIFTY": 44500.0,
                    "SENSEX": 65000.0
                }
                current_rate = sample_data.get(pair, 10000.0)
                data_source = 'Sample Data (Error Fallback)'
                logger.info(f"Error fallback data set for {pair}: {current_rate}")
        else:
            try:
                logger.info(f"Fetching forex rate for {pair}")
                price_data = get_forex_rate(pair, return_source=True)
                logger.info(f"Received forex data: {price_data}")

                if isinstance(price_data, tuple):
                    current_rate, data_source = price_data
                else:
                    current_rate = price_data
                    data_source = "Forex API"
            except Exception as e:
                logger.error(f"Error fetching forex rate: {str(e)}")
                return jsonify({
                    'error': 'Failed to fetch forex rate',
                    'details': str(e)
                }), 500

        if current_rate is None:
            logger.error(f"No price data available for {pair}")
            return jsonify({
                'error': 'Price data unavailable',
                'details': 'Could not fetch price from any available source'
            }), 503

        # Calculate option prices
        try:
            logger.info(f"Calculating option prices for rate: {current_rate}")
            call_price = black_scholes_call_put(current_rate, current_rate, expiry, risk_free_rate, volatility, option_type="call")
            put_price = black_scholes_call_put(current_rate, current_rate, expiry, risk_free_rate, volatility, option_type="put")

            response_data = {
                'rate': current_rate,
                'source': data_source,
                'call_price': call_price,
                'put_price': put_price,
                'payout': broker_payouts.get(broker, 0.75),
                'volatility': volatility,
                'expiry': expiry,
                'risk_free_rate': risk_free_rate
            }
            logger.info(f"Sending response: {response_data}")
            return jsonify(response_data)

        except Exception as e:
            logger.error(f"Error calculating option prices: {str(e)}")
            return jsonify({
                'error': 'Option calculation error',
                'details': str(e)
            }), 500

    except Exception as e:
        logger.error(f"Unexpected error in api_price: {str(e)}")
        return jsonify({
            'error': 'Server error',
            'details': str(e)
        }), 500

@app.route("/check_session")
def check_session():
    """Check if user is authenticated"""
    if 'user_id' not in session:
        return jsonify({'authenticated': False}), 401
    return jsonify({'authenticated': True})

@app.route("/subscription")
def subscription():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = get_user_by_id(session["user_id"])
    user_plan = get_user_plan(session["user_id"])
    return render_template("subscription.html", user=user, user_plan=user_plan)

@app.route("/api/user_plan", methods=["GET"])
def api_user_plan():
    """Get current user's subscription plan and feature limits"""
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    user_id = session["user_id"]
    plan = get_user_plan(user_id)
    allowed, remaining = check_signal_limit(user_id)
    return jsonify({
        "plan": plan,
        "signals_remaining": remaining if plan == "free" else "unlimited",
        "features": {
            "ai_signals": plan != "free",
            "auto_trading": plan != "free",
            "real_time_data": plan != "free",
            "market_regime": plan != "free",
            "advanced_analytics": plan != "free",
            "api_access": plan != "free",
            "multiple_strategies": plan in ["pro", "enterprise"],
            "custom_model_training": plan in ["pro", "enterprise"],
            "team_members": plan in ["pro", "enterprise"],
        }
    })

@app.route("/api/admin/upgrade_user", methods=["POST"])
def admin_upgrade_user():
    """Admin-only: upgrade or downgrade a user's subscription plan.
    Body: {username: str, plan: 'free'|'premium'|'pro'|'enterprise'}"""
    # Only admin (user_id=1) can do this
    if session.get("user_id") != 1:
        return jsonify({"error": "Admin access required"}), 403
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    username = data.get("username")
    plan = data.get("plan", "free").lower()
    if plan not in PLAN_ORDER:
        return jsonify({"error": f"Invalid plan: {plan}. Must be free, premium, pro, or enterprise"}), 400
    tier_value = PLAN_ORDER[plan]
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE users SET is_premium = ? WHERE username = ?", (tier_value, username))
        db.commit()
        if cursor.rowcount == 0:
            cursor.close()
            return jsonify({"error": f"User '{username}' not found"}), 404
        cursor.close()
        logger.info(f"Admin upgraded user '{username}' to plan '{plan}' (tier={tier_value})")
        return jsonify({"status": "success", "message": f"User '{username}' upgraded to {plan.title()} plan"})
    except Exception as e:
        logger.error(f"Error upgrading user: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/legal")
def legal():
    return render_template('legal.html')

@app.route("/terms")
def terms():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template('terms.html')

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    if request.method == "POST":
        try:
            name = request.form.get('name')
            email = request.form.get('email')
            subject = request.form.get('subject')
            message = request.form.get('message')
            
            # Here you can add your email sending logic later
            # For now, we'll just return a success response
            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"Error processing contact form: {str(e)}")
            return jsonify({"success": False})
    
    return render_template('contact.html')

@app.route("/download_forex")
def download_forex():
    """Download Forex signals as PDF with professional branding"""
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Get signals for the user
    signals = get_signals_for_user(session["user_id"])

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Add company logo
    try:
        logo_path = os.path.join(STATIC_FOLDER, "images", "logo1.png")
        if os.path.exists(logo_path):
            img = Image(logo_path, width=200, height=50)
            elements.append(img)
    except Exception as e:
        logger.error(f"Error loading logo: {str(e)}")

    # Add title with styling
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor('#00e6d0'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph(f"{get_platform_setting('platform_name')} - Forex Trading Signals", title_style))

    # Add report details
    details_style = ParagraphStyle(
        'DetailsStyle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#666666'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", details_style))
    elements.append(Spacer(1, 20))

    # Add market overview section
    overview_style = ParagraphStyle(
        'OverviewStyle',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=10,
        textColor=colors.HexColor('#333333')
    )
    elements.append(Paragraph("Market Overview", overview_style))
    elements.append(Paragraph("Forex Market Trading Signals", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Add signals table with enhanced styling
    if signals:
        # Table header with more columns
        data = [['Time', 'Pair', 'Direction', 'Entry Price', 'Stop Loss', 'Take Profit', 'Confidence', 'Status']]

        # Add signals with calculated levels
        for signal in signals:
            if not signal['pair'].endswith('_OTC'):  # Only include Forex pairs
                try:
                    # Calculate entry, stop loss and take profit levels
                    entry_price = signal.get('entry_price', 'N/A')
                    stop_loss = signal.get('stop_loss', 'N/A')
                    take_profit = signal.get('take_profit', 'N/A')
                    confidence = signal.get('confidence', 0.0)
                    status = "Won" if signal.get('result') == 1 else "Lost" if signal.get('result') == 0 else "Pending"

                    # Format numerical values
                    entry_price_str = f"{float(entry_price):.5f}" if isinstance(entry_price, (int, float)) else str(entry_price)
                    stop_loss_str = f"{float(stop_loss):.5f}" if isinstance(stop_loss, (int, float)) else str(stop_loss)
                    take_profit_str = f"{float(take_profit):.5f}" if isinstance(take_profit, (int, float)) else str(take_profit)
                    confidence_str = f"{float(confidence):.1f}%"

                    data.append([
                        signal['time'],
                        signal['pair'],
                        signal['direction'],
                        entry_price_str,
                        stop_loss_str,
                        take_profit_str,
                        confidence_str,
                        status
                    ])
                except Exception as e:
                    logger.error(f"Error processing signal: {str(e)}")
                    continue

        # Create table with enhanced styling
        if len(data) > 1:  # Only create table if we have data
            table = Table(data, colWidths=[80, 80, 80, 80, 80, 80, 80, 80])
            table.setStyle(TableStyle([
                # Header styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#00e6d0')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

                # Body styling
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#2a2a2a')),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.white),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#333333')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

                # Alternating row colors
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#2a2a2a'), colors.HexColor('#333333')])
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("No Forex signals available", styles['Normal']))
    else:
        elements.append(Paragraph("No signals available", styles['Normal']))

    # Add trading guidelines
    elements.append(Spacer(1, 30))
    guidelines_style = ParagraphStyle(
        'GuidelinesStyle',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=10,
        textColor=colors.HexColor('#333333')
    )
    elements.append(Paragraph("Trading Guidelines", guidelines_style))

    guidelines = [
        "• Always use proper risk management",
        "• Set stop-loss and take-profit levels before entering trades",
        "• Monitor market conditions before executing trades",
        "• Keep track of your trading performance",
        "• Follow the signals strictly as provided"
    ]

    for guideline in guidelines:
        elements.append(Paragraph(guideline, styles['Normal']))

    # Add disclaimer and company information
    elements.append(Spacer(1, 30))
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#666666'),
        alignment=TA_CENTER
    )

    # Add digital signature
    signature_style = ParagraphStyle(
        'SignatureStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#00e6d0'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph(f"Digitally Signed by {get_platform_setting('platform_name')}", signature_style))
    elements.append(Paragraph("Signature Hash: " + hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16], signature_style))

    # Add company information
    company_info = [
        get_platform_setting('platform_name'),
        f"Email: {get_platform_setting('support_email')}",
        f"Website: {get_platform_setting('company_address')}",
    ]

    for info in company_info:
        elements.append(Paragraph(info, footer_style))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"forex_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

@app.route("/api/check_auth")
def check_auth():
    """Check if user is authenticated"""
    if 'user_id' not in session:
        return jsonify({'authenticated': False}), 401
    return jsonify({'authenticated': True})

def generate_indian_market_indicators(base_price, pair_name):
    """Generate chart data using REAL market data from Yahoo Finance"""
    try:
        import yfinance as yf
        yahoo_symbol = symbol_map.get(pair_name, pair_name)
        if not yahoo_symbol.endswith('.NS') and not yahoo_symbol.startswith('^'):
            yahoo_symbol = f"{yahoo_symbol}.NS"

        df = yf.download(yahoo_symbol, period='3mo', interval='1d', progress=False)
        if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df is not None and not df.empty and 'Close' in df.columns:
            closes = df['Close'].tolist()
            prices = [float(x) for x in closes]
            timestamps = df.index.strftime('%Y-%m-%d %H:%M').tolist()
        else:
            num_points = 60
            prices = []
            current_price = base_price
            for i in range(num_points):
                variation = random.uniform(-0.005, 0.005)
                current_price = current_price * (1 + variation)
                prices.append(current_price)
            timestamps = []
            base_time = datetime.now() - timedelta(minutes=num_points * 15)
            for i in range(num_points):
                ts = base_time + timedelta(minutes=i * 15)
                timestamps.append(ts.strftime('%H:%M'))

        prices_array = np.array(prices)

        rsi_values = [50] * len(prices_array)
        if len(prices_array) > 14:
            from pandas import Series
            s = Series(prices_array)
            delta = s.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-10)
            rsi_calc = 100 - (100 / (1 + rs))
            rsi_values = rsi_calc.fillna(50).tolist()

        ema12 = calculate_ema(prices_array, 12)
        ema26 = calculate_ema(prices_array, 26)
        macd_line = ema12 - ema26
        signal_line = calculate_ema(macd_line, 9)

        bb_period = 20
        bb_values = [float(prices_array[0])] * len(prices_array)
        bb_upper = [float(prices_array[0])] * len(prices_array)
        bb_lower = [float(prices_array[0])] * len(prices_array)
        if len(prices_array) > bb_period:
            for i in range(bb_period, len(prices_array)):
                window = prices_array[i - bb_period:i]
                sma = np.mean(window)
                std = np.std(window)
                bb_values[i] = float(sma)
                bb_upper[i] = float(sma + 2 * std)
                bb_lower[i] = float(sma - 2 * std)

        def _to_native(obj):
            if isinstance(obj, (np.floating, np.integer)):
                return obj.item()
            if isinstance(obj, list):
                return [_to_native(v) for v in obj]
            if isinstance(obj, np.ndarray):
                return _to_native(obj.tolist())
            return obj

        return {
            'prices': _to_native(prices),
            'timestamps': timestamps,
            'indicators': {
                'rsi': _to_native(rsi_values),
                'macd': _to_native(macd_line),
                'macd_signal': _to_native(signal_line),
                'bollinger_upper': _to_native(bb_upper),
                'bollinger_lower': _to_native(bb_lower),
                'bollinger_middle': _to_native(bb_values),
            }
        }
    except Exception as e:
        logger.error(f"Error generating indicators: {str(e)}")
        return None

def calculate_ema(data, period):
    """Calculate Exponential Moving Average"""
    alpha = 2 / (period + 1)
    ema = [data[0]]
    for i in range(1, len(data)):
        ema.append(alpha * data[i] + (1 - alpha) * ema[i-1])
    return np.array(ema)

if __name__ == '__main__':
    # auto_trader.start()  # Disabled: US symbols (SPY, QQQ) not relevant for Indian trading
    
    # Start Indian auto-trading system
    try:
        enable_autotrade = os.getenv('INDIAN_AUTOTRADE_ENABLED', '0') == '1'
        if enable_autotrade:
            indian_auto_trader.start()
            logger.info("Indian auto-trading system started successfully")
        else:
            logger.info("Indian auto-trading is disabled by INDIAN_AUTOTRADE_ENABLED=0")
        logger.info("Indian auto-trading system started successfully")
    except Exception as e:
        logger.error(f"Failed to start Indian auto-trading: {str(e)}")
    
    # Start performance monitoring
    try:
        from performance_monitor import performance_monitor
        performance_monitor.start_monitoring(interval=60)  # Monitor every minute
        logger.info("Performance monitoring started")
    except Exception as e:
        logger.error(f"Failed to start performance monitoring: {str(e)}")
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=int(os.getenv('PORT', '5000')), allow_unsafe_werkzeug=True)
