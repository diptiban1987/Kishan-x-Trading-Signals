"""
Order Management System
Handles market, limit, stop-loss, and take-profit orders with matching engine.
"""
import os
import sqlite3
import threading
import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

ORDER_TYPES = {'market', 'limit', 'stop_loss', 'take_profit'}
ORDER_STATUSES = {'pending', 'executed', 'cancelled', 'rejected'}

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

class OrderManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or _get_db_path()
        self._lock = threading.Lock()
        self._ensure_table()

    def _ensure_table(self):
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        symbol TEXT NOT NULL,
                        order_type TEXT NOT NULL CHECK(order_type IN ('market','limit','stop_loss','take_profit')),
                        direction TEXT NOT NULL CHECK(direction IN ('buy','sell')),
                        quantity REAL NOT NULL,
                        price REAL,
                        stop_price REAL,
                        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','executed','cancelled','rejected')),
                        created_at TEXT NOT NULL,
                        executed_at TEXT,
                        trade_id INTEGER,
                        reject_reason TEXT,
                        notes TEXT
                    )
                """)
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to ensure orders table: {e}")

    def place_order(self, user_id: int, symbol: str, order_type: str, direction: str,
                    quantity: float, price: float = None, stop_price: float = None) -> Dict:
        if order_type not in ORDER_TYPES:
            return {'success': False, 'error': f'Invalid order type: {order_type}'}
        if direction not in ('buy', 'sell'):
            return {'success': False, 'error': 'Direction must be buy or sell'}
        if quantity <= 0:
            return {'success': False, 'error': 'Quantity must be positive'}
        if order_type == 'limit' and price is None:
            return {'success': False, 'error': 'Limit price required for limit orders'}
        if order_type in ('stop_loss', 'take_profit') and stop_price is None:
            return {'success': False, 'error': f'Stop price required for {order_type} orders'}

        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO orders (user_id, symbol, order_type, direction, quantity, price, stop_price, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """, (user_id, symbol, order_type, direction, quantity, price, stop_price, datetime.now().isoformat()))
                order_id = cur.lastrowid
                conn.commit()
                conn.close()

                if order_type == 'market':
                    return self._execute_order(order_id)
                return {'success': True, 'order_id': order_id, 'status': 'pending', 'message': f'{order_type.capitalize()} order placed'}
            except Exception as e:
                logger.error(f"Error placing order: {e}")
                return {'success': False, 'error': str(e)}

    def cancel_order(self, order_id: int, user_id: int = None) -> Dict:
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                if user_id:
                    cur.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, user_id))
                else:
                    cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
                row = cur.fetchone()
                if not row:
                    conn.close()
                    return {'success': False, 'error': 'Order not found'}
                if row['status'] != 'pending':
                    conn.close()
                    return {'success': False, 'error': f'Cannot cancel order with status: {row["status"]}'}
                cur.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
                conn.commit()
                conn.close()
                return {'success': True, 'message': 'Order cancelled'}
            except Exception as e:
                logger.error(f"Error cancelling order: {e}")
                return {'success': False, 'error': str(e)}

    def get_orders(self, user_id: int = None, status: str = None, symbol: str = None,
                   order_type: str = None, limit: int = 50) -> List[Dict]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            sql = "SELECT * FROM orders WHERE 1=1"
            params = []
            if user_id:
                sql += " AND user_id=?"
                params.append(user_id)
            if status:
                sql += " AND status=?"
                params.append(status)
            if symbol:
                sql += " AND symbol=?"
                params.append(symbol)
            if order_type:
                sql += " AND order_type=?"
                params.append(order_type)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return []

    def check_pending_orders(self, market_prices: Dict[str, float]) -> List[Dict]:
        executed = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM orders WHERE status='pending' AND order_type IN ('limit','stop_loss','take_profit')")
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()

            for order in rows:
                price = market_prices.get(order['symbol'])
                if price is None:
                    continue
                should_execute = False
                if order['order_type'] == 'limit':
                    if order['direction'] == 'buy' and price <= order['price']:
                        should_execute = True
                    elif order['direction'] == 'sell' and price >= order['price']:
                        should_execute = True
                elif order['order_type'] == 'stop_loss':
                    if order['direction'] == 'buy' and price >= order['stop_price']:
                        should_execute = True
                    elif order['direction'] == 'sell' and price <= order['stop_price']:
                        should_execute = True
                elif order['order_type'] == 'take_profit':
                    if order['direction'] == 'buy' and price <= order['stop_price']:
                        should_execute = True
                    elif order['direction'] == 'sell' and price >= order['stop_price']:
                        should_execute = True
                if should_execute:
                    result = self._execute_order(order['id'], execution_price=price)
                    if result['success']:
                        executed.append(result)
            return executed
        except Exception as e:
            logger.error(f"Error checking pending orders: {e}")
            return []

    def _execute_order(self, order_id: int, execution_price: float = None) -> Dict:
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
                order = cur.fetchone()
                if not order:
                    conn.close()
                    return {'success': False, 'error': 'Order not found'}
                if order['status'] != 'pending':
                    conn.close()
                    return {'success': False, 'error': f'Order already {order["status"]}'}

                entry_price = execution_price or order['price']
                if entry_price is None:
                    entry_price = self._fetch_market_price(order['symbol'])
                if entry_price is None:
                    cur.execute("UPDATE orders SET status='rejected', reject_reason='Unable to determine price' WHERE id=?", (order_id,))
                    conn.commit()
                    conn.close()
                    return {'success': False, 'error': 'Unable to determine market price for symbol'}

                sl_price = order.get('stop_price') if order['order_type'] == 'stop_loss' else None
                tp_price = order.get('stop_price') if order['order_type'] == 'take_profit' else None
                trade_id = self._create_trade(
                    user_id=order['user_id'],
                    symbol=order['symbol'],
                    direction=order['direction'],
                    entry_price=entry_price,
                    quantity=order['quantity'],
                    stop_loss=sl_price,
                    take_profit=tp_price
                )

                now = datetime.now().isoformat()
                cur.execute("""
                    UPDATE orders SET status='executed', executed_at=?, trade_id=? WHERE id=?
                """, (now, trade_id, order_id))
                conn.commit()
                conn.close()
                return {
                    'success': True,
                    'order_id': order_id,
                    'trade_id': trade_id,
                    'price': entry_price,
                    'message': f'{order["order_type"].capitalize()} {order["direction"]} order for {order["symbol"]} executed at {entry_price}'
                }
            except Exception as e:
                logger.error(f"Error executing order {order_id}: {e}")
                return {'success': False, 'error': str(e)}

    def _create_trade(self, user_id: int, symbol: str, direction: str,
                      entry_price: float, quantity: float, stop_loss: float = None,
                      take_profit: float = None) -> int:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        # Prevent duplicate active trades for the same user+symbol
        cur.execute("SELECT id FROM trades WHERE user_id=? AND symbol=? AND status='ACTIVE' LIMIT 1", (user_id, symbol))
        if cur.fetchone():
            logger.warning(f"Duplicate prevention: active trade already exists for {symbol} (user {user_id})")
            conn.close()
            return -1
        cur.execute("""
            INSERT INTO trades (user_id, symbol, direction, entry_price, quantity, status, entry_time, stop_loss, take_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, symbol, direction, entry_price, quantity, 'ACTIVE', datetime.now().isoformat(), stop_loss, take_profit))
        trade_id = cur.lastrowid
        conn.commit()
        conn.close()
        return trade_id

    def _fetch_market_price(self, symbol: str) -> Optional[float]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT price FROM market_data WHERE symbol=? ORDER BY timestamp DESC LIMIT 1", (symbol,))
            row = cur.fetchone()
            conn.close()
            return float(row['price']) if row else None
        except Exception:
            return None
