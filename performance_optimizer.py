#!/usr/bin/env python3
"""
Performance Optimization Script
This script helps optimize system performance by:
1. Cleaning up temporary files
2. Optimizing database
3. Managing cache
4. Monitoring system resources
"""

import os
import sys
import sqlite3
import shutil
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

class PerformanceOptimizer:
    """Performance optimization utilities"""
    
    def __init__(self):
        self.db_file = _get_db_path()
        self.cache_dir = "cache"
        self.backup_dir = "backups"
        
    def cleanup_temp_files(self):
        """Clean up temporary files and logs"""
        try:
            temp_dirs = ['__pycache__', '.pytest_cache', 'logs']
            cleaned_files = 0
            
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    if os.path.isdir(temp_dir):
                        shutil.rmtree(temp_dir)
                        cleaned_files += 1
                        logger.info(f"Cleaned directory: {temp_dir}")
            
            # Clean up Python cache files
            for root, dirs, files in os.walk('.'):
                for dir_name in dirs:
                    if dir_name == '__pycache__':
                        cache_path = os.path.join(root, dir_name)
                        shutil.rmtree(cache_path)
                        cleaned_files += 1
                        logger.info(f"Cleaned cache: {cache_path}")
            
            return cleaned_files
            
        except Exception as e:
            logger.error(f"Error cleaning temp files: {e}")
            return 0
    
    def optimize_database(self):
        """Optimize SQLite database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # VACUUM database to reclaim space
            cursor.execute("VACUUM")
            
            # ANALYZE for query optimization
            cursor.execute("ANALYZE")
            
            # Get database size before optimization
            db_size_before = os.path.getsize(self.db_file)
            
            conn.commit()
            conn.close()
            
            # Get database size after optimization
            db_size_after = os.path.getsize(self.db_file)
            space_saved = db_size_before - db_size_after
            
            logger.info(f"Database optimized. Space saved: {space_saved} bytes")
            return space_saved
            
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")
            return 0
    
    def cleanup_old_cache(self, days_old=7):
        """Clean up old cache files"""
        try:
            if not os.path.exists(self.cache_dir):
                return 0
            
            cutoff_date = datetime.now() - timedelta(days=days_old)
            cleaned_files = 0
            
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.cache_dir, filename)
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    if file_time < cutoff_date:
                        os.remove(file_path)
                        cleaned_files += 1
                        logger.info(f"Cleaned old cache: {filename}")
            
            return cleaned_files
            
        except Exception as e:
            logger.error(f"Error cleaning cache: {e}")
            return 0
    
    def cleanup_old_backups(self, days_old=30):
        """Clean up old backup files"""
        try:
            if not os.path.exists(self.backup_dir):
                return 0
            
            cutoff_date = datetime.now() - timedelta(days=days_old)
            cleaned_files = 0
            
            for filename in os.listdir(self.backup_dir):
                file_path = os.path.join(self.backup_dir, filename)
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                if file_time < cutoff_date:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    else:
                        shutil.rmtree(file_path)
                    cleaned_files += 1
                    logger.info(f"Cleaned old backup: {filename}")
            
            return cleaned_files
            
        except Exception as e:
            logger.error(f"Error cleaning backups: {e}")
            return 0
    
    def get_disk_usage(self):
        """Get disk usage statistics"""
        try:
            total_size = 0
            file_count = 0
            
            for root, dirs, files in os.walk('.'):
                # Skip certain directories
                dirs[:] = [d for d in dirs if d not in ['.git', 'venv', '__pycache__']]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(file_path)
                        file_count += 1
                    except:
                        pass
            
            return {
                'total_size': total_size,
                'file_count': file_count,
                'total_size_mb': total_size / (1024 * 1024)
            }
            
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return {'total_size': 0, 'file_count': 0, 'total_size_mb': 0}
    
    def optimize_all(self):
        """Run all optimization tasks"""
        logger.info("Starting performance optimization...")
        
        results = {
            'temp_files_cleaned': self.cleanup_temp_files(),
            'db_space_saved': self.optimize_database(),
            'cache_files_cleaned': self.cleanup_old_cache(),
            'backup_files_cleaned': self.cleanup_old_backups(),
            'disk_usage': self.get_disk_usage()
        }
        
        logger.info("Performance optimization completed:")
        logger.info(f"  - Temp files cleaned: {results['temp_files_cleaned']}")
        logger.info(f"  - Database space saved: {results['db_space_saved']} bytes")
        logger.info(f"  - Cache files cleaned: {results['cache_files_cleaned']}")
        logger.info(f"  - Backup files cleaned: {results['backup_files_cleaned']}")
        logger.info(f"  - Total disk usage: {results['disk_usage']['total_size_mb']:.2f} MB")
        
        return results

def main():
    """Main function"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    optimizer = PerformanceOptimizer()
    results = optimizer.optimize_all()
    
    print("\n" + "="*50)
    print("PERFORMANCE OPTIMIZATION COMPLETED")
    print("="*50)
    print(f"Temp files cleaned: {results['temp_files_cleaned']}")
    print(f"Database space saved: {results['db_space_saved']} bytes")
    print(f"Cache files cleaned: {results['cache_files_cleaned']}")
    print(f"Backup files cleaned: {results['backup_files_cleaned']}")
    print(f"Total disk usage: {results['disk_usage']['total_size_mb']:.2f} MB")
    print("="*50)

if __name__ == "__main__":
    main()
