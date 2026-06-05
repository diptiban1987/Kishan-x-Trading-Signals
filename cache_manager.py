import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import pandas as pd

logger = logging.getLogger(__name__)

class CacheManager:
    """File-based cache manager for market data and other frequently accessed information"""
    
    def __init__(self, cache_dir: str = "cache", default_ttl: int = 3600):
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl
        
        # Create cache directory if it doesn't exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            logger.info(f"Created cache directory: {cache_dir}")
    
    def _get_cache_path(self, key: str) -> str:
        """Get the file path for a cache key"""
        # Sanitize key for filename
        safe_key = "".join(c for c in key if c.isalnum() or c in ('-', '_', '.'))
        return os.path.join(self.cache_dir, f"{safe_key}.json")
    
    def _serialize_data(self, data: Any) -> Any:
        """Recursively serialize data to JSON-compatible format"""
        if isinstance(data, dict):
            return {str(k): self._serialize_data(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._serialize_data(item) for item in data]
        elif isinstance(data, pd.Timestamp):
            return data.isoformat()
        elif isinstance(data, pd.DataFrame):
            # Convert DataFrame to dict with string index
            # Convert index to strings to avoid Timestamp key issues
            data_dict = {}
            for idx, row in data.iterrows():
                data_dict[str(idx)] = {col: self._serialize_data(val) for col, val in row.items()}
            
            return {
                '_is_dataframe': True,
                'data': data_dict,
                'columns': list(data.columns),
                'index': [str(idx) for idx in data.index]
            }
        elif hasattr(data, 'isoformat'):  # datetime objects
            return data.isoformat()
        elif pd.isna(data):
            return None
        else:
            return data
    
    def _deserialize_data(self, data: Any) -> Any:
        """Recursively deserialize data from JSON-compatible format"""
        if isinstance(data, dict):
            if data.get('_is_dataframe', False):
                # Reconstruct DataFrame
                try:
                    df_data = data['data']
                    columns = data['columns']
                    index = data['index']
                    
                    # Convert index back to timestamps
                    parsed_index = []
                    for idx_str in index:
                        try:
                            parsed_index.append(pd.to_datetime(idx_str))
                        except:
                            parsed_index.append(idx_str)
                    
                    # Create DataFrame from dictionary with index orientation
                    df = pd.DataFrame.from_dict(df_data, orient='index', columns=columns)
                    df.index = parsed_index
                    return df
                except Exception as e:
                    logger.warning(f"Error reconstructing DataFrame: {e}")
                    return data
            else:
                return {k: self._deserialize_data(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._deserialize_data(item) for item in data]
        else:
            return data
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> bool:
        """Store data in cache with optional TTL"""
        try:
            cache_path = self._get_cache_path(key)
            
            # Serialize data
            serialized_data = self._serialize_data(data)
            
            cache_entry = {
                'data': serialized_data,
                'timestamp': datetime.now().isoformat(),
                'ttl': ttl or self.default_ttl
            }
            
            with open(cache_path, 'w') as f:
                json.dump(cache_entry, f, indent=2)
            
            logger.debug(f"Cache set: {key}")
            return True
            
        except Exception as e:
            logger.warning(f"Error setting cache {key}: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve data from cache"""
        try:
            cache_path = self._get_cache_path(key)
            
            if not os.path.exists(cache_path):
                return None
            
            with open(cache_path, 'r') as f:
                cache_entry = json.load(f)
            
            # Check if cache has expired
            timestamp = datetime.fromisoformat(cache_entry['timestamp'])
            ttl = cache_entry.get('ttl', self.default_ttl)
            
            if datetime.now() - timestamp > timedelta(seconds=ttl):
                # Cache expired, remove file
                os.remove(cache_path)
                return None
            
            # Deserialize and return data
            data = self._deserialize_data(cache_entry['data'])
            logger.debug(f"Cache hit: {key}")
            return data
            
        except Exception as e:
            logger.warning(f"Error reading cache {key}: {e}")
            # Remove corrupted cache file
            try:
                cache_path = self._get_cache_path(key)
                if os.path.exists(cache_path):
                    os.remove(cache_path)
            except:
                pass
            return None
    
    def clear_all(self) -> bool:
        """Clear all cache files"""
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.cache_dir, filename)
                    os.remove(file_path)
            
            logger.info("All cache cleared")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
    
    def cleanup_expired(self) -> int:
        """Remove expired cache files and return count of removed files"""
        removed_count = 0
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.cache_dir, filename)
                    try:
                        with open(file_path, 'r') as f:
                            cache_entry = json.load(f)
                        
                        timestamp = datetime.fromisoformat(cache_entry['timestamp'])
                        ttl = cache_entry.get('ttl', self.default_ttl)
                        
                        if datetime.now() - timestamp > timedelta(seconds=ttl):
                            os.remove(file_path)
                            removed_count += 1
                            
                    except Exception as e:
                        logger.warning(f"Error processing cache file {filename}: {e}")
                        # Remove corrupted file
                        try:
                            os.remove(file_path)
                            removed_count += 1
                        except:
                            pass
            
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} expired cache files")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error cleaning up cache: {e}")
            return 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            total_files = 0
            total_size = 0
            expired_files = 0
            
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.cache_dir, filename)
                    total_files += 1
                    total_size += os.path.getsize(file_path)
                    
                    try:
                        with open(file_path, 'r') as f:
                            cache_entry = json.load(f)
                        
                        timestamp = datetime.fromisoformat(cache_entry['timestamp'])
                        ttl = cache_entry.get('ttl', self.default_ttl)
                        
                        if datetime.now() - timestamp > timedelta(seconds=ttl):
                            expired_files += 1
                            
                    except:
                        expired_files += 1
            
            return {
                'total_files': total_files,
                'total_size': total_size,
                'expired_files': expired_files,
                'active_files': total_files - expired_files,
                'cache_dir': self.cache_dir
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'error': str(e)}

# Global cache manager instance
cache_manager = CacheManager()