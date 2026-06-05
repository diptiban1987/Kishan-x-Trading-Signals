import os
import shutil
import sqlite3
import json
import zipfile
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import threading
import time
import schedule

logger = logging.getLogger(__name__)

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

class BackupSystem:
    """Comprehensive backup system for trading data and system files"""
    
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = backup_dir
        self.db_file = _get_db_path()
        self.config_files = [
            "config.py",
            "requirements.txt",
            "symbols.py",
            "symbols.json"
        ]
        self.system_files = [
            "trading_system.py",
            "risk_manager.py",
            "auto_trader.py",
            "indian_trading_system.py",
            "portfolio_analytics.py",
            "angel_one_api.py",
            "security_manager.py",
            "notification_system.py",
            "cache_manager.py",
            "rate_limiter.py",
            "performance_monitor.py"
        ]
        
        # Create backup directory
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            logger.info(f"Created backup directory: {backup_dir}")
        
        # Initialize backup tables
        self._init_backup_tables()
        
        # Start backup scheduler
        self._start_backup_scheduler()
    
    def _init_backup_tables(self):
        """Initialize backup-related database tables"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Backup history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS backup_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_type TEXT NOT NULL,
                    backup_path TEXT NOT NULL,
                    backup_size INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'completed',
                    error_message TEXT
                )
            ''')
            
            # Backup settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS backup_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_name TEXT UNIQUE NOT NULL,
                    setting_value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insert default settings
            default_settings = [
                ('auto_backup_enabled', 'true'),
                ('backup_frequency', 'daily'),
                ('backup_retention_days', '30'),
                ('backup_compression', 'true'),
                ('backup_encryption', 'false')
            ]
            
            for setting_name, setting_value in default_settings:
                cursor.execute('''
                    INSERT OR IGNORE INTO backup_settings (setting_name, setting_value)
                    VALUES (?, ?)
                ''', (setting_name, setting_value))
            
            conn.commit()
            conn.close()
            logger.info("Backup tables initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing backup tables: {e}")
    
    def _start_backup_scheduler(self):
        """Start automatic backup scheduler"""
        def scheduler_worker():
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Error in backup scheduler: {e}")
                    time.sleep(300)  # Wait 5 minutes on error
        
        # Schedule automatic backups
        schedule.every().day.at("02:00").do(self.create_full_backup)
        schedule.every().hour.do(self.create_database_backup)
        
        scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
        scheduler_thread.start()
        logger.info("Backup scheduler started")
    
    def create_full_backup(self) -> Dict[str, Any]:
        """Create a full system backup"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"full_backup_{timestamp}"
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            # Create backup directory
            os.makedirs(backup_path, exist_ok=True)
            
            # Backup database
            db_backup_path = os.path.join(backup_path, "database")
            os.makedirs(db_backup_path, exist_ok=True)
            shutil.copy2(self.db_file, os.path.join(db_backup_path, os.path.basename(self.db_file)))
            
            # Backup configuration files
            config_backup_path = os.path.join(backup_path, "config")
            os.makedirs(config_backup_path, exist_ok=True)
            for config_file in self.config_files:
                if os.path.exists(config_file):
                    shutil.copy2(config_file, os.path.join(config_backup_path, config_file))
            
            # Backup system files
            system_backup_path = os.path.join(backup_path, "system")
            os.makedirs(system_backup_path, exist_ok=True)
            for system_file in self.system_files:
                if os.path.exists(system_file):
                    shutil.copy2(system_file, os.path.join(system_backup_path, system_file))
            
            # Backup templates and static files
            if os.path.exists("templates"):
                shutil.copytree("templates", os.path.join(backup_path, "templates"))
            
            if os.path.exists("static"):
                shutil.copytree("static", os.path.join(backup_path, "static"))
            
            # Create backup metadata
            metadata = {
                'backup_type': 'full',
                'created_at': datetime.now().isoformat(),
                'files_included': {
                    'database': [self.db_file],
                    'config': self.config_files,
                    'system': self.system_files,
                    'templates': os.listdir("templates") if os.path.exists("templates") else [],
                    'static': os.listdir("static") if os.path.exists("static") else []
                },
                'backup_size': self._get_directory_size(backup_path)
            }
            
            with open(os.path.join(backup_path, "backup_metadata.json"), 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Compress backup if enabled
            if self._get_setting('backup_compression') == 'true':
                compressed_path = f"{backup_path}.zip"
                self._compress_directory(backup_path, compressed_path)
                shutil.rmtree(backup_path)
                backup_path = compressed_path
            
            # Record backup in database
            self._record_backup('full', backup_path, metadata['backup_size'])
            
            logger.info(f"Full backup created: {backup_path}")
            return {
                'status': 'success',
                'backup_path': backup_path,
                'backup_size': metadata['backup_size'],
                'created_at': metadata['created_at']
            }
            
        except Exception as e:
            logger.error(f"Error creating full backup: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def create_database_backup(self) -> Dict[str, Any]:
        """Create a database-only backup"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"db_backup_{timestamp}.db"
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            # Copy database file
            shutil.copy2(self.db_file, backup_path)
            
            # Get file size
            backup_size = os.path.getsize(backup_path)
            
            # Record backup in database
            self._record_backup('database', backup_path, backup_size)
            
            logger.info(f"Database backup created: {backup_path}")
            return {
                'status': 'success',
                'backup_path': backup_path,
                'backup_size': backup_size,
                'created_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating database backup: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def create_config_backup(self) -> Dict[str, Any]:
        """Create a configuration-only backup"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"config_backup_{timestamp}"
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            # Create backup directory
            os.makedirs(backup_path, exist_ok=True)
            
            # Backup configuration files
            for config_file in self.config_files:
                if os.path.exists(config_file):
                    shutil.copy2(config_file, os.path.join(backup_path, config_file))
            
            # Create backup metadata
            metadata = {
                'backup_type': 'config',
                'created_at': datetime.now().isoformat(),
                'files_included': self.config_files,
                'backup_size': self._get_directory_size(backup_path)
            }
            
            with open(os.path.join(backup_path, "backup_metadata.json"), 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Compress backup if enabled
            if self._get_setting('backup_compression') == 'true':
                compressed_path = f"{backup_path}.zip"
                self._compress_directory(backup_path, compressed_path)
                shutil.rmtree(backup_path)
                backup_path = compressed_path
            
            # Record backup in database
            self._record_backup('config', backup_path, metadata['backup_size'])
            
            logger.info(f"Configuration backup created: {backup_path}")
            return {
                'status': 'success',
                'backup_path': backup_path,
                'backup_size': metadata['backup_size'],
                'created_at': metadata['created_at']
            }
            
        except Exception as e:
            logger.error(f"Error creating configuration backup: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def restore_backup(self, backup_path: str, restore_type: str = 'full') -> Dict[str, Any]:
        """Restore from backup"""
        try:
            if not os.path.exists(backup_path):
                return {'status': 'error', 'error': 'Backup file not found'}
            
            # Extract if compressed
            if backup_path.endswith('.zip'):
                extract_path = backup_path.replace('.zip', '_extracted')
                self._extract_archive(backup_path, extract_path)
                backup_path = extract_path
            
            if restore_type == 'full':
                return self._restore_full_backup(backup_path)
            elif restore_type == 'database':
                return self._restore_database_backup(backup_path)
            elif restore_type == 'config':
                return self._restore_config_backup(backup_path)
            else:
                return {'status': 'error', 'error': 'Invalid restore type'}
                
        except Exception as e:
            logger.error(f"Error restoring backup: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _restore_full_backup(self, backup_path: str) -> Dict[str, Any]:
        """Restore full backup"""
        try:
            # Read backup metadata
            metadata_path = os.path.join(backup_path, "backup_metadata.json")
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
            else:
                return {'status': 'error', 'error': 'Backup metadata not found'}
            
            # Restore database
            db_backup_path = os.path.join(backup_path, "database", os.path.basename(self.db_file))
            if os.path.exists(db_backup_path):
                shutil.copy2(db_backup_path, self.db_file)
            
            # Restore configuration files
            config_backup_path = os.path.join(backup_path, "config")
            if os.path.exists(config_backup_path):
                for config_file in os.listdir(config_backup_path):
                    shutil.copy2(os.path.join(config_backup_path, config_file), config_file)
            
            # Restore system files
            system_backup_path = os.path.join(backup_path, "system")
            if os.path.exists(system_backup_path):
                for system_file in os.listdir(system_backup_path):
                    shutil.copy2(os.path.join(system_backup_path, system_file), system_file)
            
            # Restore templates and static files
            if os.path.exists(os.path.join(backup_path, "templates")):
                if os.path.exists("templates"):
                    shutil.rmtree("templates")
                shutil.copytree(os.path.join(backup_path, "templates"), "templates")
            
            if os.path.exists(os.path.join(backup_path, "static")):
                if os.path.exists("static"):
                    shutil.rmtree("static")
                shutil.copytree(os.path.join(backup_path, "static"), "static")
            
            logger.info(f"Full backup restored from: {backup_path}")
            return {
                'status': 'success',
                'message': 'Full backup restored successfully',
                'restored_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error restoring full backup: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _restore_database_backup(self, backup_path: str) -> Dict[str, Any]:
        """Restore database backup"""
        try:
            if backup_path.endswith('.db'):
                shutil.copy2(backup_path, self.db_file)
            else:
                db_backup_path = os.path.join(backup_path, "database", os.path.basename(self.db_file))
                if os.path.exists(db_backup_path):
                    shutil.copy2(db_backup_path, self.db_file)
                else:
                    return {'status': 'error', 'error': 'Database backup not found'}
            
            logger.info(f"Database backup restored from: {backup_path}")
            return {
                'status': 'success',
                'message': 'Database backup restored successfully',
                'restored_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error restoring database backup: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _restore_config_backup(self, backup_path: str) -> Dict[str, Any]:
        """Restore configuration backup"""
        try:
            for config_file in os.listdir(backup_path):
                if config_file != "backup_metadata.json":
                    shutil.copy2(os.path.join(backup_path, config_file), config_file)
            
            logger.info(f"Configuration backup restored from: {backup_path}")
            return {
                'status': 'success',
                'message': 'Configuration backup restored successfully',
                'restored_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error restoring configuration backup: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def cleanup_old_backups(self) -> Dict[str, Any]:
        """Clean up old backups based on retention policy"""
        try:
            retention_days = int(self._get_setting('backup_retention_days'))
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Get old backups
            cursor.execute('''
                SELECT id, backup_path FROM backup_history
                WHERE created_at < ? AND status = 'completed'
            ''', (cutoff_date,))
            
            old_backups = cursor.fetchall()
            deleted_count = 0
            
            for backup_id, backup_path in old_backups:
                try:
                    if os.path.exists(backup_path):
                        if os.path.isfile(backup_path):
                            os.remove(backup_path)
                        else:
                            shutil.rmtree(backup_path)
                    
                    # Remove from database
                    cursor.execute('DELETE FROM backup_history WHERE id = ?', (backup_id,))
                    deleted_count += 1
                    
                except Exception as e:
                    logger.warning(f"Error deleting backup {backup_path}: {e}")
            
            conn.commit()
            conn.close()
            
            logger.info(f"Cleaned up {deleted_count} old backups")
            return {
                'status': 'success',
                'deleted_count': deleted_count,
                'retention_days': retention_days
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up old backups: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def get_backup_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get backup history"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, backup_type, backup_path, backup_size, created_at, status, error_message
                FROM backup_history
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))
            
            backups = []
            for row in cursor.fetchall():
                backups.append({
                    'id': row[0],
                    'backup_type': row[1],
                    'backup_path': row[2],
                    'backup_size': row[3],
                    'created_at': row[4],
                    'status': row[5],
                    'error_message': row[6]
                })
            
            conn.close()
            return backups
            
        except Exception as e:
            logger.error(f"Error getting backup history: {e}")
            return []
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """Get backup statistics"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Total backups
            cursor.execute('SELECT COUNT(*) FROM backup_history')
            total_backups = cursor.fetchone()[0]
            
            # Successful backups
            cursor.execute('SELECT COUNT(*) FROM backup_history WHERE status = "completed"')
            successful_backups = cursor.fetchone()[0]
            
            # Failed backups
            cursor.execute('SELECT COUNT(*) FROM backup_history WHERE status = "failed"')
            failed_backups = cursor.fetchone()[0]
            
            # Total backup size
            cursor.execute('SELECT SUM(backup_size) FROM backup_history WHERE status = "completed"')
            total_size = cursor.fetchone()[0] or 0
            
            # Backups by type (last 30 days)
            cursor.execute('''
                SELECT backup_type, COUNT(*) 
                FROM backup_history 
                WHERE created_at > datetime('now', '-30 days')
                GROUP BY backup_type
            ''')
            backups_by_type = dict(cursor.fetchall())
            
            conn.close()
            
            return {
                'total_backups': total_backups,
                'successful_backups': successful_backups,
                'failed_backups': failed_backups,
                'total_size': total_size,
                'backups_by_type_30d': backups_by_type,
                'retention_days': int(self._get_setting('backup_retention_days')),
                'auto_backup_enabled': self._get_setting('auto_backup_enabled') == 'true'
            }
            
        except Exception as e:
            logger.error(f"Error getting backup stats: {e}")
            return {'error': str(e)}
    
    def _get_setting(self, setting_name: str) -> str:
        """Get backup setting value"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('SELECT setting_value FROM backup_settings WHERE setting_name = ?', (setting_name,))
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else ''
            
        except Exception as e:
            logger.error(f"Error getting setting {setting_name}: {e}")
            return ''
    
    def _set_setting(self, setting_name: str, setting_value: str):
        """Set backup setting value"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO backup_settings (setting_name, setting_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (setting_name, setting_value))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error setting {setting_name}: {e}")
    
    def _record_backup(self, backup_type: str, backup_path: str, backup_size: int):
        """Record backup in database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO backup_history (backup_type, backup_path, backup_size, status)
                VALUES (?, ?, ?, 'completed')
            ''', (backup_type, backup_path, backup_size))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error recording backup: {e}")
    
    def _get_directory_size(self, directory: str) -> int:
        """Get total size of directory"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
        return total_size
    
    def _compress_directory(self, source_dir: str, target_zip: str):
        """Compress directory to zip file"""
        with zipfile.ZipFile(target_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)
    
    def _extract_archive(self, zip_path: str, extract_path: str):
        """Extract zip archive"""
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(extract_path)

# Global backup system instance
backup_system = BackupSystem()
