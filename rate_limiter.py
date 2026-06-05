import time
import threading
from collections import defaultdict, deque
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Rate limiter to control API call frequency"""
    
    def __init__(self):
        import os
        self.limits = {
            'yfinance': {'calls': int(os.getenv('YFINANCE_RATE_LIMIT', '10')), 'window': 60},
            'angel_one': {'calls': int(os.getenv('ANGEL_ONE_RATE_LIMIT', '50')), 'window': 60},
            'alpha_vantage': {'calls': int(os.getenv('ALPHA_VANTAGE_RATE_LIMIT', '5')), 'window': 60},
            'general': {'calls': int(os.getenv('GENERAL_RATE_LIMIT', '20')), 'window': 60}
        }
        self.call_history = defaultdict(deque)
        self.lock = threading.Lock()
    
    def can_make_call(self, service: str = 'general') -> bool:
        """Check if a call can be made without exceeding rate limits"""
        with self.lock:
            now = time.time()
            limit_config = self.limits.get(service, self.limits['general'])
            max_calls = limit_config['calls']
            window = limit_config['window']
            
            # Clean old calls outside the window
            call_history = self.call_history[service]
            while call_history and call_history[0] < now - window:
                call_history.popleft()
            
            # Check if we can make another call
            return len(call_history) < max_calls
    
    def record_call(self, service: str = 'general') -> None:
        """Record a successful API call"""
        with self.lock:
            now = time.time()
            self.call_history[service].append(now)
            logger.debug(f"Recorded call for {service}, total calls in window: {len(self.call_history[service])}")
    
    def wait_if_needed(self, service: str = 'general') -> None:
        """Wait if necessary to respect rate limits"""
        wait_time = 0.0
        with self.lock:
            now = time.time()
            limit_config = self.limits.get(service, self.limits['general'])
            window = limit_config['window']

            call_history = self.call_history[service]
            while call_history and call_history[0] < now - window:
                call_history.popleft()

            if len(call_history) >= limit_config['calls']:
                oldest_call = call_history[0]
                wait_time = window - (time.time() - oldest_call)
                if wait_time < 0:
                    wait_time = 0.0

        if wait_time > 0:
            logger.info(f"Rate limit reached for {service}, waiting {wait_time:.2f} seconds")
            time.sleep(wait_time)
    
    def get_stats(self) -> Dict[str, Dict]:
        """Get current rate limiting statistics"""
        with self.lock:
            stats = {}
            now = time.time()
            
            for service, limit_config in self.limits.items():
                call_history = self.call_history[service]
                window = limit_config['window']
                
                # Clean old calls
                while call_history and call_history[0] < now - window:
                    call_history.popleft()
                
                stats[service] = {
                    'calls_in_window': len(call_history),
                    'max_calls': limit_config['calls'],
                    'window_seconds': window,
                    'remaining_calls': max(0, limit_config['calls'] - len(call_history)),
                    'reset_time': call_history[0] + window if call_history else None
                }
            
            return stats
    
    def reset(self, service: Optional[str] = None) -> None:
        """Reset rate limiting for a service or all services"""
        with self.lock:
            if service:
                self.call_history[service].clear()
                logger.info(f"Reset rate limiting for {service}")
            else:
                self.call_history.clear()
                logger.info("Reset rate limiting for all services")

# Global rate limiter instance
rate_limiter = RateLimiter()
