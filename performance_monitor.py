import time
import psutil
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from collections import deque

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """Monitor system performance metrics"""
    
    def __init__(self, history_size: int = 100):
        self.history_size = history_size
        self.metrics_history = {
            'cpu_percent': deque(maxlen=history_size),
            'memory_percent': deque(maxlen=history_size),
            'memory_used_mb': deque(maxlen=history_size),
            'disk_usage_percent': deque(maxlen=history_size),
            'network_io': deque(maxlen=history_size),
            'timestamp': deque(maxlen=history_size)
        }
        self.start_time = time.time()
        self.monitoring = False
        self.monitor_thread = None
        self.lock = threading.Lock()
        
        # Performance thresholds
        self.thresholds = {
            'cpu_warning': 80.0,
            'cpu_critical': 95.0,
            'memory_warning': 80.0,
            'memory_critical': 95.0,
            'disk_warning': 85.0,
            'disk_critical': 95.0
        }
    
    def start_monitoring(self, interval: int = 30):
        """Start performance monitoring in a separate thread"""
        if self.monitoring:
            logger.warning("Performance monitoring is already running")
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self.monitor_thread.start()
        logger.info(f"Performance monitoring started with {interval}s interval")
    
    def stop_monitoring(self):
        """Stop performance monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Performance monitoring stopped")
    
    def _monitor_loop(self, interval: int):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                self._collect_metrics()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Error in performance monitoring: {e}")
                time.sleep(interval)
    
    def _collect_metrics(self):
        """Collect current system metrics"""
        try:
            with self.lock:
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=1)
                
                # Memory usage
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                memory_used_mb = memory.used / (1024 * 1024)
                
                # Disk usage
                disk = psutil.disk_usage('/')
                disk_usage_percent = (disk.used / disk.total) * 100
                
                # Network I/O
                network = psutil.net_io_counters()
                network_io = {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                }
                
                # Store metrics
                timestamp = datetime.now()
                self.metrics_history['cpu_percent'].append(cpu_percent)
                self.metrics_history['memory_percent'].append(memory_percent)
                self.metrics_history['memory_used_mb'].append(memory_used_mb)
                self.metrics_history['disk_usage_percent'].append(disk_usage_percent)
                self.metrics_history['network_io'].append(network_io)
                self.metrics_history['timestamp'].append(timestamp)
                
                # Check for warnings
                self._check_thresholds(cpu_percent, memory_percent, disk_usage_percent)
                
        except Exception as e:
            logger.error(f"Error collecting performance metrics: {e}")
    
    def _check_thresholds(self, cpu_percent: float, memory_percent: float, disk_percent: float):
        """Check if metrics exceed warning/critical thresholds"""
        warnings = []
        
        if cpu_percent >= self.thresholds['cpu_critical']:
            warnings.append(f"CRITICAL: CPU usage at {cpu_percent:.1f}%")
        elif cpu_percent >= self.thresholds['cpu_warning']:
            warnings.append(f"WARNING: CPU usage at {cpu_percent:.1f}%")
        
        if memory_percent >= self.thresholds['memory_critical']:
            warnings.append(f"CRITICAL: Memory usage at {memory_percent:.1f}%")
        elif memory_percent >= self.thresholds['memory_warning']:
            warnings.append(f"WARNING: Memory usage at {memory_percent:.1f}%")
        
        if disk_percent >= self.thresholds['disk_critical']:
            warnings.append(f"CRITICAL: Disk usage at {disk_percent:.1f}%")
        elif disk_percent >= self.thresholds['disk_warning']:
            warnings.append(f"WARNING: Disk usage at {disk_percent:.1f}%")
        
        for warning in warnings:
            logger.warning(warning)
    
    def get_current_metrics(self) -> Dict:
        """Get current system metrics"""
        try:
            with self.lock:
                if not self.metrics_history['timestamp']:
                    return {'error': 'No metrics collected yet'}
                
                latest_idx = -1
                return {
                    'timestamp': self.metrics_history['timestamp'][latest_idx].isoformat(),
                    'cpu_percent': self.metrics_history['cpu_percent'][latest_idx],
                    'memory_percent': self.metrics_history['memory_percent'][latest_idx],
                    'memory_used_mb': self.metrics_history['memory_used_mb'][latest_idx],
                    'disk_usage_percent': self.metrics_history['disk_usage_percent'][latest_idx],
                    'network_io': self.metrics_history['network_io'][latest_idx],
                    'uptime_seconds': time.time() - self.start_time
                }
        except Exception as e:
            logger.error(f"Error getting current metrics: {e}")
            return {'error': str(e)}
    
    def get_metrics_history(self, hours: int = 24) -> Dict:
        """Get metrics history for the specified time period"""
        try:
            with self.lock:
                cutoff_time = datetime.now() - timedelta(hours=hours)
                
                # Filter metrics within the time period
                filtered_metrics = {
                    'cpu_percent': [],
                    'memory_percent': [],
                    'memory_used_mb': [],
                    'disk_usage_percent': [],
                    'network_io': [],
                    'timestamp': []
                }
                
                for i, timestamp in enumerate(self.metrics_history['timestamp']):
                    if timestamp >= cutoff_time:
                        for key in filtered_metrics:
                            if key == 'timestamp':
                                filtered_metrics[key].append(timestamp.isoformat())
                            else:
                                filtered_metrics[key].append(self.metrics_history[key][i])
                
                return filtered_metrics
                
        except Exception as e:
            logger.error(f"Error getting metrics history: {e}")
            return {'error': str(e)}
    
    def get_performance_summary(self) -> Dict:
        """Get performance summary with averages and peaks"""
        try:
            with self.lock:
                if not self.metrics_history['timestamp']:
                    return {'error': 'No metrics collected yet'}
                
                # Calculate averages
                cpu_avg = sum(self.metrics_history['cpu_percent']) / len(self.metrics_history['cpu_percent'])
                memory_avg = sum(self.metrics_history['memory_percent']) / len(self.metrics_history['memory_percent'])
                disk_avg = sum(self.metrics_history['disk_usage_percent']) / len(self.metrics_history['disk_usage_percent'])
                
                # Calculate peaks
                cpu_peak = max(self.metrics_history['cpu_percent'])
                memory_peak = max(self.metrics_history['memory_percent'])
                disk_peak = max(self.metrics_history['disk_usage_percent'])
                
                # Calculate uptime
                uptime_seconds = time.time() - self.start_time
                uptime_hours = uptime_seconds / 3600
                
                return {
                    'uptime_hours': round(uptime_hours, 2),
                    'metrics_collected': len(self.metrics_history['timestamp']),
                    'averages': {
                        'cpu_percent': round(cpu_avg, 2),
                        'memory_percent': round(memory_avg, 2),
                        'disk_usage_percent': round(disk_avg, 2)
                    },
                    'peaks': {
                        'cpu_percent': round(cpu_peak, 2),
                        'memory_percent': round(memory_peak, 2),
                        'disk_usage_percent': round(disk_peak, 2)
                    },
                    'thresholds': self.thresholds,
                    'monitoring_active': self.monitoring
                }
                
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {'error': str(e)}
    
    def set_thresholds(self, thresholds: Dict[str, float]) -> bool:
        """Update performance thresholds"""
        try:
            for key, value in thresholds.items():
                if key in self.thresholds and isinstance(value, (int, float)):
                    self.thresholds[key] = float(value)
            logger.info(f"Updated performance thresholds: {thresholds}")
            return True
        except Exception as e:
            logger.error(f"Error setting thresholds: {e}")
            return False

# Global performance monitor instance
performance_monitor = PerformanceMonitor()
