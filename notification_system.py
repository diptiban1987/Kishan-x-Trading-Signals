import smtplib
import logging
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

def _get_branding_config():
    try:
        from branding_config import branding
        return branding
    except ImportError:
        return None

def _get_platform_name():
    bc = _get_branding_config()
    if bc:
        return bc.get('platform_name', 'Trading Platform')
    return 'Trading Platform'

def _get_notification_sender():
    bc = _get_branding_config()
    if bc:
        return bc.get('notification_sender_name', 'Trading Platform')
    return 'Trading Platform'

def _get_db_path():
    bc = _get_branding_config()
    if bc:
        return bc.db_path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

class NotificationType(Enum):
    TRADE_SIGNAL = "trade_signal"
    TRADE_EXECUTED = "trade_executed"
    TRADE_CLOSED = "trade_closed"
    PORTFOLIO_ALERT = "portfolio_alert"
    SYSTEM_ALERT = "system_alert"
    SECURITY_ALERT = "security_alert"
    PERFORMANCE_REPORT = "performance_report"
    ERROR_NOTIFICATION = "error_notification"

class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class Notification:
    id: Optional[int]
    user_id: int
    type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    data: Dict[str, Any]
    created_at: datetime
    sent_at: Optional[datetime]
    read_at: Optional[datetime]
    delivery_methods: List[str]  # ['email', 'sms', 'push', 'in_app']
    status: str  # 'pending', 'sent', 'failed', 'read'

class NotificationSystem:
    """Comprehensive notification system for trading alerts and system notifications"""
    
    def __init__(self, smtp_config: Dict[str, str] = None):
        self.smtp_config = smtp_config or {
            'host': os.environ.get('SMTP_HOST', 'smtp.gmail.com'),
            'port': int(os.environ.get('SMTP_PORT', 587)),
            'username': os.environ.get('SMTP_USERNAME', ''),
            'password': os.environ.get('SMTP_PASSWORD', ''),
            'use_tls': True
        }
        
        # Initialize notification tables
        self._init_notification_tables()
        
        # Start notification worker thread
        self._start_notification_worker()
    
    def _init_notification_tables(self):
        """Initialize notification-related database tables"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            # Notifications table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data TEXT,  -- JSON data
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sent_at DATETIME,
                    read_at DATETIME,
                    delivery_methods TEXT,  -- JSON array
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # User notification preferences
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_notification_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    notification_type TEXT NOT NULL,
                    email_enabled BOOLEAN DEFAULT 1,
                    sms_enabled BOOLEAN DEFAULT 0,
                    push_enabled BOOLEAN DEFAULT 1,
                    in_app_enabled BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(user_id, notification_type)
                )
            ''')
            
            # Notification templates
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notification_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    title_template TEXT NOT NULL,
                    message_template TEXT NOT NULL,
                    email_template TEXT,
                    sms_template TEXT,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Insert default templates
            self._insert_default_templates(cursor)
            
            conn.commit()
            conn.close()
            logger.info("Notification tables initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing notification tables: {e}")
    
    def _insert_default_templates(self, cursor):
        """Insert default notification templates"""
        templates = [
            {
                'type': 'trade_signal',
                'priority': 'medium',
                'title_template': 'New Trading Signal: {symbol}',
                'message_template': 'Signal: {action} {symbol} at {price}. Strategy: {strategy}',
                'email_template': '''
                <h2>Trading Signal Alert</h2>
                <p><strong>Symbol:</strong> {symbol}</p>
                <p><strong>Action:</strong> {action}</p>
                <p><strong>Price:</strong> {price}</p>
                <p><strong>Strategy:</strong> {strategy}</p>
                <p><strong>Confidence:</strong> {confidence}%</p>
                <p><strong>Time:</strong> {timestamp}</p>
                ''',
                'sms_template': 'Signal: {action} {symbol} at {price}'
            },
            {
                'type': 'trade_executed',
                'priority': 'high',
                'title_template': 'Trade Executed: {symbol}',
                'message_template': 'Trade executed: {action} {quantity} {symbol} at {price}',
                'email_template': '''
                <h2>Trade Executed</h2>
                <p><strong>Symbol:</strong> {symbol}</p>
                <p><strong>Action:</strong> {action}</p>
                <p><strong>Quantity:</strong> {quantity}</p>
                <p><strong>Price:</strong> {price}</p>
                <p><strong>Order ID:</strong> {order_id}</p>
                <p><strong>Time:</strong> {timestamp}</p>
                ''',
                'sms_template': 'Trade: {action} {quantity} {symbol} at {price}'
            },
            {
                'type': 'trade_closed',
                'priority': 'high',
                'title_template': 'Trade Closed: {symbol}',
                'message_template': 'Trade closed: {action} {symbol}. P&L: {pnl}',
                'email_template': '''
                <h2>Trade Closed</h2>
                <p><strong>Symbol:</strong> {symbol}</p>
                <p><strong>Action:</strong> {action}</p>
                <p><strong>P&L:</strong> {pnl}</p>
                <p><strong>Return:</strong> {return_percent}%</p>
                <p><strong>Duration:</strong> {duration}</p>
                <p><strong>Time:</strong> {timestamp}</p>
                ''',
                'sms_template': 'Closed: {action} {symbol}. P&L: {pnl}'
            },
            {
                'type': 'portfolio_alert',
                'priority': 'medium',
                'title_template': 'Portfolio Alert: {alert_type}',
                'message_template': 'Portfolio alert: {message}',
                'email_template': '''
                <h2>Portfolio Alert</h2>
                <p><strong>Alert Type:</strong> {alert_type}</p>
                <p><strong>Message:</strong> {message}</p>
                <p><strong>Current Value:</strong> {portfolio_value}</p>
                <p><strong>Time:</strong> {timestamp}</p>
                ''',
                'sms_template': 'Portfolio: {alert_type} - {message}'
            },
            {
                'type': 'system_alert',
                'priority': 'high',
                'title_template': 'System Alert: {alert_type}',
                'message_template': 'System alert: {message}',
                'email_template': '''
                <h2>System Alert</h2>
                <p><strong>Alert Type:</strong> {alert_type}</p>
                <p><strong>Message:</strong> {message}</p>
                <p><strong>Severity:</strong> {severity}</p>
                <p><strong>Time:</strong> {timestamp}</p>
                ''',
                'sms_template': 'System: {alert_type} - {message}'
            }
        ]
        
        for template in templates:
            cursor.execute('''
                INSERT OR IGNORE INTO notification_templates 
                (type, priority, title_template, message_template, email_template, sms_template)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                template['type'], template['priority'], template['title_template'],
                template['message_template'], template['email_template'], template['sms_template']
            ))
    
    def _start_notification_worker(self):
        """Start background worker for processing notifications"""
        def worker():
            while True:
                try:
                    self._process_pending_notifications()
                    time.sleep(30)  # Check every 30 seconds
                except Exception as e:
                    logger.error(f"Error in notification worker: {e}")
                    time.sleep(60)  # Wait longer on error
        
        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()
        logger.info("Notification worker started")
    
    def create_notification(self, user_id: int, notification_type: NotificationType,
                          priority: NotificationPriority, title: str, message: str,
                          data: Dict[str, Any] = None, delivery_methods: List[str] = None) -> int:
        """Create a new notification"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            # Get user's delivery preferences
            if delivery_methods is None:
                delivery_methods = self._get_user_delivery_preferences(cursor, user_id, notification_type.value)
            
            cursor.execute('''
                INSERT INTO notifications 
                (user_id, type, priority, title, message, data, delivery_methods)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, notification_type.value, priority.value, title, message,
                json.dumps(data or {}), json.dumps(delivery_methods)
            ))
            
            notification_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            logger.info(f"Created notification {notification_id} for user {user_id}")
            return notification_id
            
        except Exception as e:
            logger.error(f"Error creating notification: {e}")
            return None
    
    def _get_user_delivery_preferences(self, cursor, user_id: int, notification_type: str) -> List[str]:
        """Get user's delivery preferences for notification type"""
        cursor.execute('''
            SELECT email_enabled, sms_enabled, push_enabled, in_app_enabled
            FROM user_notification_preferences
            WHERE user_id = ? AND notification_type = ?
        ''', (user_id, notification_type))
        
        result = cursor.fetchone()
        if result:
            email_enabled, sms_enabled, push_enabled, in_app_enabled = result
            methods = []
            if email_enabled:
                methods.append('email')
            if sms_enabled:
                methods.append('sms')
            if push_enabled:
                methods.append('push')
            if in_app_enabled:
                methods.append('in_app')
            return methods
        
        # Default preferences if not set
        return ['email', 'in_app']
    
    def _process_pending_notifications(self):
        """Process pending notifications"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            # Get pending notifications
            cursor.execute('''
                SELECT id, user_id, type, priority, title, message, data, delivery_methods
                FROM notifications
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 10
            ''')
            
            notifications = cursor.fetchall()
            
            for notification in notifications:
                notification_id, user_id, notification_type, priority, title, message, data_json, delivery_methods_json = notification
                
                try:
                    data = json.loads(data_json) if data_json else {}
                    delivery_methods = json.loads(delivery_methods_json) if delivery_methods_json else []
                    
                    # Send notification via each method
                    success = True
                    for method in delivery_methods:
                        if method == 'email':
                            if not self._send_email_notification(user_id, title, message, data):
                                success = False
                        elif method == 'sms':
                            if not self._send_sms_notification(user_id, message):
                                success = False
                        elif method == 'push':
                            if not self._send_push_notification(user_id, title, message, data):
                                success = False
                        elif method == 'in_app':
                            # In-app notifications are automatically available
                            pass
                    
                    # Update notification status
                    status = 'sent' if success else 'failed'
                    cursor.execute('''
                        UPDATE notifications 
                        SET status = ?, sent_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (status, notification_id))
                    
                except Exception as e:
                    logger.error(f"Error processing notification {notification_id}: {e}")
                    cursor.execute('''
                        UPDATE notifications 
                        SET status = 'failed'
                        WHERE id = ?
                    ''', (notification_id,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error processing pending notifications: {e}")
    
    def _send_email_notification(self, user_id: int, title: str, message: str, data: Dict[str, Any]) -> bool:
        """Send email notification"""
        try:
            # Get user email
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            cursor.execute('SELECT email FROM users WHERE id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            
            if not result or not result[0]:
                logger.warning(f"No email found for user {user_id}")
                return False
            
            user_email = result[0]
            
            # Create email
            msg = MIMEMultipart()
            msg['From'] = self.smtp_config['username']
            msg['To'] = user_email
            msg['Subject'] = f"{_get_platform_name()}: {title}"
            
            # Create HTML body
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #00e6d0, #0099cc); color: white; padding: 20px; border-radius: 10px 10px 0 0;">
                        <h1 style="margin: 0; font-size: 24px;">{_get_platform_name()} Alert</h1>
                    </div>
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px;">
                        <h2 style="color: #0099cc; margin-top: 0;">{title}</h2>
                        <p style="font-size: 16px;">{message}</p>
                        <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                        <p style="font-size: 12px; color: #666;">
                            This is an automated message from {_get_platform_name()}.<br>
                            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send email
            if self.smtp_config['username'] and self.smtp_config['password']:
                server = smtplib.SMTP(self.smtp_config['host'], self.smtp_config['port'])
                if self.smtp_config['use_tls']:
                    server.starttls()
                server.login(self.smtp_config['username'], self.smtp_config['password'])
                server.send_message(msg)
                server.quit()
                
                logger.info(f"Email notification sent to {user_email}")
                return True
            else:
                logger.warning("SMTP credentials not configured")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False
    
    def _send_sms_notification(self, user_id: int, message: str) -> bool:
        """Send SMS notification (placeholder - requires SMS service integration)"""
        # This would integrate with services like Twilio, AWS SNS, etc.
        logger.info(f"SMS notification for user {user_id}: {message}")
        return True  # Placeholder
    
    def _send_push_notification(self, user_id: int, title: str, message: str, data: Dict[str, Any]) -> bool:
        """Send push notification (placeholder - requires push service integration)"""
        # This would integrate with services like Firebase, OneSignal, etc.
        logger.info(f"Push notification for user {user_id}: {title} - {message}")
        return True  # Placeholder
    
    def get_user_notifications(self, user_id: int, limit: int = 50, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Get notifications for a user"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            query = '''
                SELECT id, type, priority, title, message, data, created_at, sent_at, read_at, status
                FROM notifications
                WHERE user_id = ?
            '''
            
            if unread_only:
                query += ' AND read_at IS NULL'
            
            query += ' ORDER BY created_at DESC LIMIT ?'
            
            cursor.execute(query, (user_id, limit))
            
            notifications = []
            for row in cursor.fetchall():
                notifications.append({
                    'id': row[0],
                    'type': row[1],
                    'priority': row[2],
                    'title': row[3],
                    'message': row[4],
                    'data': json.loads(row[5]) if row[5] else {},
                    'created_at': row[6],
                    'sent_at': row[7],
                    'read_at': row[8],
                    'status': row[9]
                })
            
            conn.close()
            return notifications
            
        except Exception as e:
            logger.error(f"Error getting user notifications: {e}")
            return []
    
    def mark_notification_read(self, notification_id: int, user_id: int) -> bool:
        """Mark notification as read"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE notifications 
                SET read_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            ''', (notification_id, user_id))
            
            conn.commit()
            conn.close()
            
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return False
    
    def get_notification_stats(self) -> Dict[str, Any]:
        """Get notification statistics"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            # Total notifications
            cursor.execute('SELECT COUNT(*) FROM notifications')
            total_notifications = cursor.fetchone()[0]
            
            # Pending notifications
            cursor.execute('SELECT COUNT(*) FROM notifications WHERE status = "pending"')
            pending_notifications = cursor.fetchone()[0]
            
            # Unread notifications
            cursor.execute('SELECT COUNT(*) FROM notifications WHERE read_at IS NULL')
            unread_notifications = cursor.fetchone()[0]
            
            # Notifications by type (last 24 hours)
            cursor.execute('''
                SELECT type, COUNT(*) 
                FROM notifications 
                WHERE created_at > datetime('now', '-1 day')
                GROUP BY type
            ''')
            notifications_by_type = dict(cursor.fetchall())
            
            conn.close()
            
            return {
                'total_notifications': total_notifications,
                'pending_notifications': pending_notifications,
                'unread_notifications': unread_notifications,
                'notifications_by_type_24h': notifications_by_type
            }
            
        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return {'error': str(e)}

# Global notification system instance
notification_system = NotificationSystem()
