import hashlib
import secrets
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from functools import wraps
import jwt
from flask import request, jsonify, session, current_app
import sqlite3
import os

logger = logging.getLogger(__name__)

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), _get_db_path())

class SecurityManager:
    """Manages security, authentication, and authorization"""
    
    def __init__(self, secret_key: str = None):
        key = secret_key or os.environ.get('SECRET_KEY') or os.environ.get('FLASK_SECRET_KEY')
        if not key:
            key = secrets.token_hex(32)
            logger.warning("No SECRET_KEY set; generated ephemeral key. Sessions will invalidate on restart.")
        self.secret_key = key
        self.session_timeout = 3600  # 1 hour
        self.max_login_attempts = 5
        self.lockout_duration = 900  # 15 minutes
        self.password_min_length = 8
        self.rate_limit_requests = 100  # per hour
        self.rate_limit_window = 3600  # 1 hour
        
        # Initialize security tables
        self._init_security_tables()
    
    def _init_security_tables(self):
        """Initialize security-related database tables"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            # Login attempts tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    user_agent TEXT
                )
            ''')
            
            # User sessions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # API rate limiting
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_rate_limits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    request_count INTEGER DEFAULT 1,
                    window_start DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_request DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Security events log
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    user_id INTEGER,
                    ip_address TEXT,
                    details TEXT,
                    severity TEXT DEFAULT 'INFO',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # User permissions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    permission TEXT NOT NULL,
                    granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    granted_by INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(user_id, permission)
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Security tables initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing security tables: {e}")
    
    def hash_password(self, password: str) -> str:
        """Hash password using PBKDF2"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return f"{salt}:{password_hash.hex()}"
    
    def verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify password against stored hash"""
        try:
            salt, password_hash = stored_hash.split(':')
            password_hash_bytes = bytes.fromhex(password_hash)
            computed_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
            return secrets.compare_digest(password_hash_bytes, computed_hash)
        except Exception as e:
            logger.error(f"Error verifying password: {e}")
            return False
    
    def generate_session_token(self) -> str:
        """Generate a secure session token"""
        return secrets.token_urlsafe(32)
    
    def create_session(self, user_id: int, ip_address: str, user_agent: str = None) -> str:
        """Create a new user session"""
        try:
            session_token = self.generate_session_token()
            expires_at = datetime.now() + timedelta(seconds=self.session_timeout)
            
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            # Deactivate old sessions for this user
            cursor.execute('UPDATE user_sessions SET is_active = 0 WHERE user_id = ?', (user_id,))
            
            # Create new session
            cursor.execute('''
                INSERT INTO user_sessions (user_id, session_token, ip_address, user_agent, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, session_token, ip_address, user_agent, expires_at))
            
            conn.commit()
            conn.close()
            
            self.log_security_event('SESSION_CREATED', user_id, ip_address, 
                                  f"New session created for user {user_id}")
            
            return session_token
            
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return None
    
    def validate_session(self, session_token: str, ip_address: str = None) -> Optional[int]:
        """Validate session and return user_id if valid"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()

            if ip_address:
                cursor.execute('''
                    SELECT user_id, expires_at FROM user_sessions 
                    WHERE session_token = ? AND ip_address = ? AND is_active = 1
                ''', (session_token, ip_address))
            else:
                cursor.execute('''
                    SELECT user_id, expires_at FROM user_sessions 
                    WHERE session_token = ? AND is_active = 1
                ''', (session_token,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                user_id, expires_at = result
                if datetime.now() < datetime.fromisoformat(expires_at):
                    return user_id
                else:
                    self.logout_session(session_token)
            
            return None
            
        except Exception as e:
            logger.error(f"Error validating session: {e}")
            return None
    
    def logout_session(self, session_token: str):
        """Logout a session"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            cursor.execute('UPDATE user_sessions SET is_active = 0 WHERE session_token = ?', 
                         (session_token,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging out session: {e}")
    
    def check_login_attempts(self, username: str, ip_address: str) -> bool:
        """Check if user/IP is locked out due to too many failed attempts"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            # Check recent failed attempts
            cutoff_time = datetime.now() - timedelta(seconds=self.lockout_duration)
            cursor.execute('''
                SELECT COUNT(*) FROM login_attempts 
                WHERE (username = ? OR ip_address = ?) 
                AND success = 0 
                AND timestamp > ?
            ''', (username, ip_address, cutoff_time))
            
            failed_attempts = cursor.fetchone()[0]
            conn.close()
            
            return failed_attempts < self.max_login_attempts
            
        except Exception as e:
            logger.error(f"Error checking login attempts: {e}")
            return True
    
    def record_login_attempt(self, username: str, ip_address: str, success: bool, user_agent: str = None):
        """Record a login attempt"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO login_attempts (username, ip_address, success, user_agent)
                VALUES (?, ?, ?, ?)
            ''', (username, ip_address, success, user_agent))
            
            conn.commit()
            conn.close()
            
            # Log security event
            event_type = 'LOGIN_SUCCESS' if success else 'LOGIN_FAILED'
            self.log_security_event(event_type, None, ip_address, 
                                  f"Login attempt for user {username}")
            
        except Exception as e:
            logger.error(f"Error recording login attempt: {e}")
    
    def check_rate_limit(self, ip_address: str, endpoint: str) -> bool:
        """Check if IP is within rate limits for endpoint"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            # Clean old entries
            cutoff_time = datetime.now() - timedelta(seconds=self.rate_limit_window)
            cursor.execute('DELETE FROM api_rate_limits WHERE window_start < ?', (cutoff_time,))
            
            # Check current rate limit
            cursor.execute('''
                SELECT request_count FROM api_rate_limits 
                WHERE ip_address = ? AND endpoint = ? AND window_start > ?
            ''', (ip_address, endpoint, cutoff_time))
            
            result = cursor.fetchone()
            
            if result:
                request_count = result[0]
                if request_count >= self.rate_limit_requests:
                    conn.close()
                    return False
                
                # Update count
                cursor.execute('''
                    UPDATE api_rate_limits 
                    SET request_count = request_count + 1, last_request = CURRENT_TIMESTAMP
                    WHERE ip_address = ? AND endpoint = ?
                ''', (ip_address, endpoint))
            else:
                # Create new entry
                cursor.execute('''
                    INSERT INTO api_rate_limits (ip_address, endpoint, request_count)
                    VALUES (?, ?, 1)
                ''', (ip_address, endpoint))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True
    
    def log_security_event(self, event_type: str, user_id: int, ip_address: str, 
                          details: str, severity: str = 'INFO'):
        """Log a security event"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO security_events (event_type, user_id, ip_address, details, severity)
                VALUES (?, ?, ?, ?, ?)
            ''', (event_type, user_id, ip_address, details, severity))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Security event: {event_type} - {details}")
            
        except Exception as e:
            logger.error(f"Error logging security event: {e}")
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            # Active sessions
            cursor.execute('SELECT COUNT(*) FROM user_sessions WHERE is_active = 1')
            active_sessions = cursor.fetchone()[0]
            
            # Failed login attempts (last 24 hours)
            cutoff_time = datetime.now() - timedelta(hours=24)
            cursor.execute('''
                SELECT COUNT(*) FROM login_attempts 
                WHERE success = 0 AND timestamp > ?
            ''', (cutoff_time,))
            failed_logins = cursor.fetchone()[0]
            
            # Security events (last 24 hours)
            cursor.execute('''
                SELECT COUNT(*) FROM security_events 
                WHERE timestamp > ?
            ''', (cutoff_time,))
            security_events = cursor.fetchone()[0]
            
            # Rate limit violations (last hour)
            rate_cutoff = datetime.now() - timedelta(hours=1)
            cursor.execute('''
                SELECT COUNT(DISTINCT ip_address) FROM api_rate_limits 
                WHERE request_count >= ? AND last_request > ?
            ''', (self.rate_limit_requests, rate_cutoff))
            rate_violations = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'active_sessions': active_sessions,
                'failed_logins_24h': failed_logins,
                'security_events_24h': security_events,
                'rate_violations_1h': rate_violations,
                'max_login_attempts': self.max_login_attempts,
                'session_timeout': self.session_timeout,
                'rate_limit_requests': self.rate_limit_requests
            }
            
        except Exception as e:
            logger.error(f"Error getting security stats: {e}")
            return {'error': str(e)}
    
    def get_security_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent security events"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT event_type, user_id, ip_address, details, severity, timestamp
                FROM security_events 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
            
            events = []
            for row in cursor.fetchall():
                events.append({
                    'event_type': row[0],
                    'user_id': row[1],
                    'ip_address': row[2],
                    'details': row[3],
                    'severity': row[4],
                    'timestamp': row[5]
                })
            
            conn.close()
            return events
            
        except Exception as e:
            logger.error(f"Error getting security events: {e}")
            return []
    
    def check_user_permission(self, user_id: int, permission: str) -> bool:
        """Check if user has specific permission"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) FROM user_permissions 
                WHERE user_id = ? AND permission = ?
            ''', (user_id, permission))
            
            has_permission = cursor.fetchone()[0] > 0
            conn.close()
            
            return has_permission
            
        except Exception as e:
            logger.error(f"Error checking user permission: {e}")
            return False
    
    def grant_permission(self, user_id: int, permission: str, granted_by: int = None):
        """Grant permission to user"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR IGNORE INTO user_permissions (user_id, permission, granted_by)
                VALUES (?, ?, ?)
            ''', (user_id, permission, granted_by))
            
            conn.commit()
            conn.close()
            
            self.log_security_event('PERMISSION_GRANTED', user_id, None, 
                                  f"Permission {permission} granted to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error granting permission: {e}")
    
    def revoke_permission(self, user_id: int, permission: str):
        """Revoke permission from user"""
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM user_permissions 
                WHERE user_id = ? AND permission = ?
            ''', (user_id, permission))
            
            conn.commit()
            conn.close()
            
            self.log_security_event('PERMISSION_REVOKED', user_id, None, 
                                  f"Permission {permission} revoked from user {user_id}")
            
        except Exception as e:
            logger.error(f"Error revoking permission: {e}")

# Security decorators
def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_token = request.cookies.get('session_token')
        ip_address = request.remote_addr
        
        if not session_token:
            return jsonify({'error': 'Authentication required'}), 401
        
        user_id = security_manager.validate_session(session_token, ip_address)
        if not user_id:
            return jsonify({'error': 'Invalid or expired session'}), 401
        
        # Add user_id to request context
        request.user_id = user_id
        return f(*args, **kwargs)
    
    return decorated_function

def require_permission(permission: str):
    """Decorator to require specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(request, 'user_id'):
                return jsonify({'error': 'Authentication required'}), 401
            
            # Check permission (simplified - in production, implement proper permission checking)
            if not security_manager.check_user_permission(request.user_id, permission):
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def rate_limit(f):
    """Decorator to apply rate limiting"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip_address = request.remote_addr
        endpoint = request.endpoint
        
        if not security_manager.check_rate_limit(ip_address, endpoint):
            return jsonify({'error': 'Rate limit exceeded'}), 429
        
        return f(*args, **kwargs)
    
    return decorated_function

# Global security manager instance
security_manager = SecurityManager()
