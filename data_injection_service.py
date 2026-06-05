"""
Data Injection Service
Allows admin to inject real API data from various sources
"""

import threading
import time
import logging
import requests
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sqlite3
import json
import os

logger = logging.getLogger(__name__)

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

class DataInjectionService:
    """Service for injecting real-time data from external APIs"""
    
    def __init__(self):
        self.running = False
        self.data_sources = {}
        self.update_threads = {}
        self.last_updates = {}
        self.data_quality_metrics = {}
        
    def start_data_injection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start data injection from specified source"""
        try:
            source = config.get('data_source')
            symbols = config.get('symbols', [])
            
            if not symbols:
                return {'status': 'error', 'error': 'No symbols specified'}
            
            if source == 'angel_one':
                return self._start_angel_one_injection(config)
            elif source == 'yfinance':
                return self._start_yfinance_injection(config)
            elif source == 'alpha_vantage':
                return self._start_alpha_vantage_injection(config)
            elif source == 'custom':
                return self._start_custom_injection(config)
            else:
                return {'status': 'error', 'error': f'Unknown data source: {source}'}
                
        except Exception as e:
            logger.error(f"Error starting data injection: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def stop_data_injection(self, source: str = None) -> Dict[str, Any]:
        """Stop data injection from specified source or all sources"""
        try:
            if source:
                if source in self.update_threads:
                    self.update_threads[source].stop()
                    del self.update_threads[source]
                    logger.info(f"Stopped data injection from {source}")
                return {'status': 'success', 'message': f'Stopped {source} data injection'}
            else:
                # Stop all sources
                for src in list(self.update_threads.keys()):
                    self.update_threads[src].stop()
                    del self.update_threads[src]
                self.running = False
                logger.info("Stopped all data injection services")
                return {'status': 'success', 'message': 'Stopped all data injection services'}
                
        except Exception as e:
            logger.error(f"Error stopping data injection: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _start_angel_one_injection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start Angel One data injection"""
        try:
            symbols = config.get('symbols', [])
            frequency = config.get('update_frequency', 30)
            
            # Create update thread
            thread = DataUpdateThread(
                source='angel_one',
                symbols=symbols,
                frequency=frequency,
                update_function=self._fetch_angel_one_data
            )
            
            self.update_threads['angel_one'] = thread
            thread.start()
            
            logger.info(f"Started Angel One data injection for {len(symbols)} symbols")
            return {'status': 'success', 'message': 'Angel One data injection started'}
            
        except Exception as e:
            logger.error(f"Error starting Angel One injection: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _start_yfinance_injection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start Yahoo Finance data injection"""
        try:
            symbols = config.get('symbols', [])
            frequency = config.get('update_frequency', 30)
            
            # Create update thread
            thread = DataUpdateThread(
                source='yfinance',
                symbols=symbols,
                frequency=frequency,
                update_function=self._fetch_yfinance_data
            )
            
            self.update_threads['yfinance'] = thread
            thread.start()
            
            logger.info(f"Started Yahoo Finance data injection for {len(symbols)} symbols")
            return {'status': 'success', 'message': 'Yahoo Finance data injection started'}
            
        except Exception as e:
            logger.error(f"Error starting Yahoo Finance injection: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _start_alpha_vantage_injection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start Alpha Vantage data injection"""
        try:
            symbols = config.get('symbols', [])
            frequency = config.get('update_frequency', 30)
            api_key = config.get('api_key')
            
            if not api_key:
                return {'status': 'error', 'error': 'Alpha Vantage API key required'}
            
            # Create update thread
            thread = DataUpdateThread(
                source='alpha_vantage',
                symbols=symbols,
                frequency=frequency,
                update_function=self._fetch_alpha_vantage_data,
                extra_params={'api_key': api_key}
            )
            
            self.update_threads['alpha_vantage'] = thread
            thread.start()
            
            logger.info(f"Started Alpha Vantage data injection for {len(symbols)} symbols")
            return {'status': 'success', 'message': 'Alpha Vantage data injection started'}
            
        except Exception as e:
            logger.error(f"Error starting Alpha Vantage injection: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _start_custom_injection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start custom API data injection"""
        try:
            symbols = config.get('symbols', [])
            frequency = config.get('update_frequency', 30)
            endpoint = config.get('api_endpoint')
            api_key = config.get('api_key')
            
            if not endpoint or not api_key:
                return {'status': 'error', 'error': 'Custom API requires endpoint and key'}
            
            # Create update thread
            thread = DataUpdateThread(
                source='custom',
                symbols=symbols,
                frequency=frequency,
                update_function=self._fetch_custom_api_data,
                extra_params={'endpoint': endpoint, 'api_key': api_key}
            )
            
            self.update_threads['custom'] = thread
            thread.start()
            
            logger.info(f"Started custom API data injection for {len(symbols)} symbols")
            return {'status': 'success', 'message': 'Custom API data injection started'}
            
        except Exception as e:
            logger.error(f"Error starting custom API injection: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _fetch_angel_one_data(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetch data from Angel One API"""
        try:
            # This would integrate with your existing Angel One client
            # For now, return mock data
            data = {}
            for symbol in symbols:
                data[symbol] = {
                    'price': 100.0 + (hash(symbol) % 1000) / 100,  # Mock price
                    'volume': 1000000 + (hash(symbol) % 1000000),
                    'timestamp': datetime.now().isoformat(),
                    'source': 'angel_one'
                }
            return data
        except Exception as e:
            logger.error(f"Error fetching Angel One data: {e}")
            return {}
    
    def _fetch_yfinance_data(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetch data from Yahoo Finance"""
        try:
            data = {}
            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    current_price = info.get('regularMarketPrice', 0)
                    
                    data[symbol] = {
                        'price': current_price,
                        'volume': info.get('volume', 0),
                        'timestamp': datetime.now().isoformat(),
                        'source': 'yfinance',
                        'market_cap': info.get('marketCap', 0),
                        'pe_ratio': info.get('trailingPE', 0)
                    }
                except Exception as e:
                    logger.warning(f"Error fetching data for {symbol}: {e}")
                    continue
            
            return data
        except Exception as e:
            logger.error(f"Error fetching Yahoo Finance data: {e}")
            return {}
    
    def _fetch_alpha_vantage_data(self, symbols: List[str], extra_params: Dict) -> Dict[str, Any]:
        """Fetch data from Alpha Vantage API"""
        try:
            api_key = extra_params.get('api_key')
            data = {}
            
            for symbol in symbols:
                try:
                    # Alpha Vantage Global Quote endpoint
                    url = f"https://www.alphavantage.co/query"
                    params = {
                        'function': 'GLOBAL_QUOTE',
                        'symbol': symbol,
                        'apikey': api_key
                    }
                    
                    response = requests.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    
                    quote_data = response.json().get('Global Quote', {})
                    if quote_data:
                        data[symbol] = {
                            'price': float(quote_data.get('05. price', 0)),
                            'volume': int(quote_data.get('06. volume', 0)),
                            'timestamp': datetime.now().isoformat(),
                            'source': 'alpha_vantage',
                            'change': float(quote_data.get('09. change', 0)),
                            'change_percent': quote_data.get('10. change percent', '0%')
                        }
                    
                    # Rate limiting for Alpha Vantage (5 requests per minute for free tier)
                    time.sleep(12)
                    
                except Exception as e:
                    logger.warning(f"Error fetching Alpha Vantage data for {symbol}: {e}")
                    continue
            
            return data
        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage data: {e}")
            return {}
    
    def _fetch_custom_api_data(self, symbols: List[str], extra_params: Dict) -> Dict[str, Any]:
        """Fetch data from custom API"""
        try:
            endpoint = extra_params.get('endpoint')
            api_key = extra_params.get('api_key')
            data = {}
            
            headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
            
            for symbol in symbols:
                try:
                    # Make request to custom endpoint
                    url = f"{endpoint}/quote/{symbol}"
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    
                    quote_data = response.json()
                    data[symbol] = {
                        'price': quote_data.get('price', 0),
                        'volume': quote_data.get('volume', 0),
                        'timestamp': datetime.now().isoformat(),
                        'source': 'custom_api',
                        'data': quote_data  # Include all custom data
                    }
                    
                except Exception as e:
                    logger.warning(f"Error fetching custom API data for {symbol}: {e}")
                    continue
            
            return data
        except Exception as e:
            logger.error(f"Error fetching custom API data: {e}")
            return {}
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of data injection service"""
        try:
            status = {
                'running': self.running,
                'active_sources': list(self.update_threads.keys()),
                'last_updates': self.last_updates.copy(),
                'data_quality': self.data_quality_metrics.copy()
            }
            return status
        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return {'error': str(e)}
    
    def inject_data_to_system(self, data: Dict[str, Any]) -> bool:
        """Inject fetched data into the trading system"""
        try:
            # Update database with new data
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            
            for symbol, quote_data in data.items():
                # Update current prices table
                cursor.execute('''
                    INSERT OR REPLACE INTO current_prices (symbol, price, volume, timestamp, source)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    quote_data.get('price', 0),
                    quote_data.get('volume', 0),
                    quote_data.get('timestamp', datetime.now().isoformat()),
                    quote_data.get('source', 'unknown')
                ))
                
                # Log data injection
                logger.info(f"Injected data for {symbol}: {quote_data.get('price')} @ {quote_data.get('timestamp')}")
            
            conn.commit()
            conn.close()
            
            # Update last update timestamp
            self.last_updates[datetime.now().isoformat()] = len(data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error injecting data to system: {e}")
            return False


class DataUpdateThread(threading.Thread):
    """Thread for updating data at specified frequency"""
    
    def __init__(self, source: str, symbols: List[str], frequency: int, 
                 update_function, extra_params: Dict = None):
        super().__init__()
        self.source = source
        self.symbols = symbols
        self.frequency = frequency
        self.update_function = update_function
        self.extra_params = extra_params or {}
        self.running = True
        self.daemon = True
    
    def run(self):
        """Main update loop"""
        logger.info(f"Started {self.source} update thread for {len(self.symbols)} symbols")
        
        while self.running:
            try:
                # Fetch data
                if self.extra_params:
                    data = self.update_function(self.symbols, self.extra_params)
                else:
                    data = self.update_function(self.symbols)
                
                # Inject data into system
                if data:
                    # This would call the main data injection service
                    logger.info(f"Fetched {len(data)} symbols from {self.source}")
                
                # Wait for next update
                time.sleep(self.frequency)
                
            except Exception as e:
                logger.error(f"Error in {self.source} update thread: {e}")
                time.sleep(self.frequency)
    
    def stop(self):
        """Stop the update thread"""
        self.running = False
        logger.info(f"Stopping {self.source} update thread")


# Global instance
data_injection_service = DataInjectionService()

def get_data_injection_service():
    """Get the global data injection service instance"""
    return data_injection_service
