try:
    from alpha_vantage.timeseries import TimeSeries
    from alpha_vantage.foreignexchange import ForeignExchange
except ImportError:
    print("Warning: alpha_vantage module not found. Some features may be limited.")
    TimeSeries = None
    ForeignExchange = None

import pandas as pd
try:
    import pandas_ta as ta
except ImportError:
    ta = None
from datetime import datetime, timedelta
import time
from typing import Dict, Optional, Tuple, Union
import os
import requests
import logging
import random
import numpy as np
from config import (
    ALPHA_VANTAGE_API_KEY,
    ALPHA_VANTAGE_BACKUP_KEY,
    OPENEXCHANGERATES_API_KEY,
    CURRENCYLAYER_API_KEY,
    API_TIMEOUT,
    CACHE_DURATION,
    PREMIUM_API_ENABLED,
    ALPHA_VANTAGE_RATE_LIMIT,
    ALPHA_VANTAGE_DAILY_LIMIT,
    EXCHANGERATE_API_RATE_LIMIT,
    MAX_RETRIES,
    ERROR_RETRY_DELAY
)
import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OTCDataHandler:
    def __init__(self, api_key=None):
        self.api_key = api_key or ALPHA_VANTAGE_API_KEY
        self.backup_api_key = ALPHA_VANTAGE_BACKUP_KEY
        self.price_cache = {}
        self.cache_duration = CACHE_DURATION
        self.last_api_call = {}
        self.rate_limit_window = 60  # 1 minute
        self.max_calls_per_window = ALPHA_VANTAGE_RATE_LIMIT
        self.daily_calls = 0
        self.daily_limit = ALPHA_VANTAGE_DAILY_LIMIT
        self.last_daily_reset = datetime.now()
        self.api_key_valid = None
        self.max_retries = MAX_RETRIES
        self.retry_delay = ERROR_RETRY_DELAY
        
        # Initialize rate limiting attributes
        self.source_limits = {
            'Alpha Vantage': {
                'call_count': 0,
                'last_call': 0,
                'error_count': 0,
                'backoff_until': 0,
                'daily_calls': 0,
                'last_daily_reset': datetime.now()
            },
            'ExchangeRate-API': {
                'call_count': 0,
                'last_call': 0,
                'error_count': 0,
                'backoff_until': 0
            }
        }
        
        self.data_sources = [
            {
                'name': 'Alpha Vantage',
                'rate_limit': ALPHA_VANTAGE_RATE_LIMIT,
                'daily_limit': ALPHA_VANTAGE_DAILY_LIMIT,
                'retry_after': self.retry_delay
            },
            {
                'name': 'ExchangeRate-API',
                'rate_limit': EXCHANGERATE_API_RATE_LIMIT,
                'retry_after': self.retry_delay
            }
        ]
        
        # Initialize TimeSeries if alpha_vantage is available
        if TimeSeries is not None:
            try:
                self.ts = TimeSeries(key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize TimeSeries: {str(e)}")
                self.ts = None
        else:
            self.ts = None
            
        # Validate API key on initialization
        self._validate_api_key()

    def get_realtime_price(self, symbol: str, return_source: bool = False, force_refresh: bool = False) -> Union[float, Tuple[float, str]]:
        """
        Get real-time price for OTC symbol with improved error handling and caching
        
        Args:
            symbol: The OTC symbol to get price for (e.g. 'EURUSD_OTC')
            return_source: Whether to return the data source along with the price
            force_refresh: Whether to force a refresh from API instead of using cache
            
        Returns:
            If return_source is True: Tuple of (price, source)
            If return_source is False: Just the price
        """
        try:
            now = datetime.now()
            
            # Remove _OTC suffix for API call
            base_symbol = symbol.replace('_OTC', '')
            from_currency = base_symbol[:3]
            to_currency = base_symbol[3:]
            
            logger.info(f"Getting realtime price for {symbol} ({from_currency}/{to_currency})")
            
            # Check cache first if not forcing refresh
            if not force_refresh and symbol in self.price_cache:
                cache_time, price = self.price_cache[symbol]
                if (now - cache_time).total_seconds() < self.cache_duration:
                    logger.info(f"Returning cached price for {symbol}: {price}")
                    if return_source:
                        return price, 'Cache'
                    return price
            
            # Rate limiting check
            if symbol in self.last_api_call:
                calls_in_window = [t for t in self.last_api_call[symbol] 
                                 if (now - t).total_seconds() < self.rate_limit_window]
                if len(calls_in_window) >= self.max_calls_per_window:
                    logger.warning(f"Rate limit reached for {symbol}, using cached data if available")
                    if symbol in self.price_cache:
                        cache_time, price = self.price_cache[symbol]
                        if return_source:
                            return price, 'Rate Limited Cache'
                        return price
                    return None if not return_source else (None, 'Rate Limited')
            
            # Try Alpha Vantage first
            logger.info(f"Trying Alpha Vantage for {symbol}")
            price = self._get_alpha_vantage_price(from_currency, to_currency)
            if price:
                # Normalize price based on currency pair
                price = self._normalize_price(price, from_currency, to_currency)
                logger.info(f"Got normalized price from Alpha Vantage: {price}")
                self._update_cache_and_rate_limit(symbol, price, now)
                if return_source:
                    return price, 'Alpha Vantage'
                return price
            
            # Try ExchangeRate-API as fallback
            logger.info(f"Trying ExchangeRate-API for {symbol}")
            price = self._get_exchangerate_api_price(from_currency, to_currency)
            if price:
                # Normalize price based on currency pair
                price = self._normalize_price(price, from_currency, to_currency)
                logger.info(f"Got normalized price from ExchangeRate-API: {price}")
                self._update_cache_and_rate_limit(symbol, price, now)
                if return_source:
                    return price, 'ExchangeRate-API'
                return price
            
            # Try Fixer.io as second fallback
            logger.info(f"Trying Fixer.io for {symbol}")
            price = self._get_fixer_price(from_currency, to_currency)
            if price:
                # Normalize price based on currency pair
                price = self._normalize_price(price, from_currency, to_currency)
                logger.info(f"Got normalized price from Fixer.io: {price}")
                self._update_cache_and_rate_limit(symbol, price, now)
                if return_source:
                    return price, 'Fixer.io'
                return price
            
            # If all APIs fail but we have cached data, use it
            if symbol in self.price_cache:
                logger.warning(f"All APIs failed for {symbol}, using expired cache")
                cache_time, price = self.price_cache[symbol]
                if return_source:
                    return price, 'Expired Cache'
                return price
            
            logger.error(f"No data available for {symbol} from any source")
            return None if not return_source else (None, 'No Data Available')
            
        except Exception as e:
            logger.error(f"Error fetching OTC price for {symbol}: {str(e)}")
            # Try to return cached data if available
            if symbol in self.price_cache:
                cache_time, price = self.price_cache[symbol]
                if return_source:
                    return price, 'Error Fallback Cache'
                return price
            return None if not return_source else (None, 'Error')
    
    def _update_cache_and_rate_limit(self, symbol: str, price: float, timestamp: datetime):
        """Update cache and rate limit tracking for a symbol"""
        self.price_cache[symbol] = (timestamp, price)
        if symbol not in self.last_api_call:
            self.last_api_call[symbol] = []
        self.last_api_call[symbol].append(timestamp)
        # Clean up old rate limit entries
        self.last_api_call[symbol] = [t for t in self.last_api_call[symbol] 
                                    if (timestamp - t).total_seconds() < self.rate_limit_window]
    
    def _get_alpha_vantage_price(self, from_currency: str, to_currency: str) -> Optional[float]:
        """Get price from Alpha Vantage API"""
        if not self.api_key:
            return None
            
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}&to_currency={to_currency}&apikey={self.api_key}"
        
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if "Realtime Currency Exchange Rate" in data:
                return float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        except Exception as e:
            logger.error(f"Alpha Vantage API error: {str(e)}")
        return None
    
    def _get_exchangerate_api_price(self, from_currency: str, to_currency: str) -> Optional[float]:
        """Get price from ExchangeRate-API"""
        url = f"https://open.er-api.com/v6/latest/{from_currency}"
        
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if "rates" in data and to_currency in data["rates"]:
                return float(data["rates"][to_currency])
        except Exception as e:
            logger.error(f"ExchangeRate-API error: {str(e)}")
        return None
    
    def _get_fixer_price(self, from_currency: str, to_currency: str) -> Optional[float]:
        """Get price from Fixer.io API"""
        url = f"http://data.fixer.io/api/latest?access_key=YOUR_FIXER_API_KEY&base={from_currency}&symbols={to_currency}"
        
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if data.get("success") and "rates" in data and to_currency in data["rates"]:
                return float(data["rates"][to_currency])
        except Exception as e:
            logger.error(f"Fixer.io API error: {str(e)}")
        return None

    def _validate_api_key(self):
        """Validate the API key by making a test request."""
        try:
            logger.info("Validating Alpha Vantage API key")
            url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=EUR&to_currency=USD&apikey={self.api_key}"
            response = requests.get(url, timeout=API_TIMEOUT)
            data = response.json()
            
            if "Error Message" in data:
                logger.error(f"Invalid API key: {data['Error Message']}")
                raise ValueError(f"Invalid API key: {data['Error Message']}")
                
            if "Note" in data:
                if "premium" in data["Note"].lower():
                    if not PREMIUM_API_ENABLED:
                        logger.warning("Premium API features required. Set PREMIUM_API_ENABLED=True in config.py")
                elif "API call frequency" in data["Note"]:
                    logger.warning(f"API rate limit reached: {data['Note']}")
                    
            logger.info("API key validation successful")
                    
        except requests.exceptions.Timeout:
            logger.warning("Timeout while validating API key. OTC features may be limited.")
            self.api_key_valid = False
            return
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error while validating API key: {str(e)}")
            raise ValueError(f"Request error while validating API key: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to validate API key: {str(e)}")
            raise ValueError(f"Failed to validate API key: {str(e)}")

    def _check_rate_limit(self, source_name: str) -> bool:
        """Check if we've exceeded rate limits for a data source"""
        now = datetime.now()
        source = self.source_limits[source_name]
        
        # Reset daily counts if it's a new day
        if source_name == 'Alpha Vantage':
            if (now - source['last_daily_reset']).days > 0:
                source['daily_calls'] = 0
                source['last_daily_reset'] = now
            
            # Check daily limit
            if source['daily_calls'] >= self.daily_limit:
                logger.warning(f"{source_name} daily limit reached")
                return False
        
        # Check if we're in backoff period
        if now.timestamp() < source['backoff_until']:
            return False
            
        # Reset call count if we're in a new window
        if (now.timestamp() - source['last_call']) >= self.rate_limit_window:
            source['call_count'] = 0
            
        # Check rate limit
        source_config = next((s for s in self.data_sources if s['name'] == source_name), None)
        if source_config and source['call_count'] >= source_config['rate_limit']:
            return False
            
        return True

    def _validate_price(self, price: float) -> bool:
        """Validate if the price is reasonable."""
        if price is None or not isinstance(price, (int, float)):
            return False
        if price <= 0:
            return False
        if price > 1000000:  # Unrealistic exchange rate
            return False
        return True

    def _get_alpha_vantage_rate(self, pair: str) -> Optional[float]:
        """Get rate from Alpha Vantage with rate limit handling."""
        if not self.api_key:
            logger.warning("No Alpha Vantage API key provided")
            return None
            
        from_symbol = pair[:3]
        to_symbol = pair[3:]
        
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_symbol}&to_currency={to_symbol}&apikey={self.api_key}"
        
        try:
            response = requests.get(url, timeout=API_TIMEOUT)
            data = response.json()
            
            if "Error Message" in data:
                logger.error(f"Alpha Vantage API Error: {data['Error Message']}")
                return None
                
            if "Note" in data:
                if "premium" in data["Note"].lower():
                    logger.warning("Premium API features required")
                    return None
                elif "API call frequency" in data["Note"]:
                    logger.warning(f"API rate limit reached: {data['Note']}")
                    return None
                
            if "Realtime Currency Exchange Rate" in data:
                rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
                logger.info(f"Successfully fetched rate from Alpha Vantage: {rate}")
                return rate
                
        except Exception as e:
            logger.error(f"Error fetching from Alpha Vantage: {str(e)}")
            return None
        
        return None

    def _get_exchangerate_api_rate(self, pair: str) -> Optional[float]:
        """Get rate from ExchangeRate-API."""
        from_symbol = pair[:3]
        to_symbol = pair[3:]
        url = f"https://open.er-api.com/v6/latest/{from_symbol}"
        
        try:
            response = requests.get(url, timeout=API_TIMEOUT)
            data = response.json()
            
            if data.get("result") == "error":
                logger.error(f"ExchangeRate-API Error: {data.get('error-type', 'Unknown error')}")
                return None
                
            if data.get("rates") and to_symbol in data["rates"]:
                rate = float(data["rates"][to_symbol])
                logger.info(f"Successfully fetched rate from ExchangeRate-API: {rate}")
                return rate
                
        except Exception as e:
            logger.error(f"Error fetching from ExchangeRate-API: {str(e)}")
            return None
        
        return None

    def _get_fixer_rate(self, from_currency, to_currency):
        """Get rate from Fixer.io API."""
        try:
            url = f"https://api.exchangerate.host/latest?base={from_currency}&symbols={to_currency}"
            response = requests.get(url, timeout=API_TIMEOUT)
            data = response.json()
            
            if data.get("success", False) and to_currency in data.get("rates", {}):
                return float(data["rates"][to_currency])
                
        except Exception as e:
            logger.error(f"Fixer API error: {str(e)}")
            
        return None

    def _get_openexchangerates_rate(self, from_currency, to_currency):
        """Get rate from Open Exchange Rates API."""
        try:
            url = f"https://openexchangerates.org/api/latest.json?app_id={OPENEXCHANGERATES_API_KEY}&base={from_currency}&symbols={to_currency}"
            response = requests.get(url, timeout=API_TIMEOUT)
            data = response.json()
            
            if data.get("rates") and to_currency in data["rates"]:
                return float(data["rates"][to_currency])
                
        except Exception as e:
            logger.error(f"Open Exchange Rates API error: {str(e)}")
            
        return None

    def _get_currencylayer_rate(self, from_currency, to_currency):
        """Get rate from Currency Layer API."""
        try:
            url = f"http://apilayer.net/api/live?access_key={CURRENCYLAYER_API_KEY}&currencies={to_currency}&source={from_currency}"
            response = requests.get(url, timeout=API_TIMEOUT)
            data = response.json()
            
            if data.get("success") and "quotes" in data:
                quote_key = f"{from_currency}{to_currency}"
                if quote_key in data["quotes"]:
                    return float(data["quotes"][quote_key])
                
        except Exception as e:
            logger.error(f"Currency Layer API error: {str(e)}")
            
        return None

    def _get_alpha_vantage_historical(self, from_currency: str, to_currency: str, interval: str = '1min') -> Optional[pd.DataFrame]:
        """Get historical data from Alpha Vantage."""
        try:
            if self.ts is None:
                logger.error("Alpha Vantage module not available")
                return None
                
            # Get intraday data
            data, _ = self.ts.get_intraday(
                symbol=f"{from_currency}{to_currency}",
                interval=interval,
                outputsize='compact'
            )
            
            if data is not None and not data.empty:
                # Rename columns to match our format
                data.columns = ['open', 'high', 'low', 'close', 'volume']
                return data
                
        except Exception as e:
            logger.error(f"Error fetching historical data from Alpha Vantage: {str(e)}")
            
        return None

    def get_historical_data(self, symbol: str, interval: str = '1min', 
                          output_size: str = 'compact') -> Optional[pd.DataFrame]:
        """Get historical data with improved error handling and fallback options."""
        try:
            # Get historical data
            data = self._get_alpha_vantage_historical(symbol[:3], symbol[3:], interval)
            if data is None or data.empty:
                return None

            # Calculate technical indicators
            indicators = {}
            
            # RSI
            if len(data) >= 14:
                delta = data['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                indicators['rsi'] = (100 - (100 / (1 + rs))).iloc[-1]
            
            # MACD
            if len(data) >= 26:
                exp1 = data['close'].ewm(span=12, adjust=False).mean()
                exp2 = data['close'].ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9, adjust=False).mean()
                indicators['macd'] = macd.iloc[-1]
                indicators['macd_signal'] = signal.iloc[-1]
                indicators['macd_hist'] = (macd - signal).iloc[-1]
            
            # Bollinger Bands
            if len(data) >= 20:
                sma = data['close'].rolling(window=20).mean()
                std = data['close'].rolling(window=20).std()
                indicators['bb_upper'] = (sma + (std * 2)).iloc[-1]
                indicators['bb_middle'] = sma.iloc[-1]
                indicators['bb_lower'] = (sma - (std * 2)).iloc[-1]
            
            # Stochastic RSI
            if len(data) >= 14:
                # Calculate RSI
                delta = data['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                
                # Calculate Stochastic RSI
                stoch_rsi = (rsi - rsi.rolling(window=14).min()) / (rsi.rolling(window=14).max() - rsi.rolling(window=14).min())
                indicators['stoch_rsi_k'] = stoch_rsi.iloc[-1]
                indicators['stoch_rsi_d'] = stoch_rsi.rolling(window=3).mean().iloc[-1]
            
            return {
                'historical': {
                    'dates': data.index.strftime('%Y-%m-%d %H:%M').tolist(),
                    'prices': {
                        'open': data['open'].tolist(),
                        'high': data['high'].tolist(),
                        'low': data['low'].tolist(),
                        'close': data['close'].tolist(),
                        'volume': data['volume'].tolist()
                    },
                    'indicators': indicators
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting historical data: {str(e)}")
            return None

    def calculate_technical_indicators(self, data: pd.DataFrame) -> Dict:
        """
        Calculate technical indicators for the given data using pandas_ta
        
        Args:
            data (pd.DataFrame): Price data
            
        Returns:
            Dict: Dictionary of technical indicators
        """
        try:
            # Ensure we have the required columns
            if '4. close' in data.columns:
                data = data.rename(columns={
                    '4. close': 'close',
                    '1. open': 'open',
                    '2. high': 'high',
                    '3. low': 'low',
                    '5. volume': 'volume'
                })

            # Calculate indicators manually since we have limited data points
            indicators = {}
            
            # Simple Moving Average (SMA)
            if len(data) >= 20:
                indicators['sma_20'] = data['close'].rolling(window=20).mean().iloc[-1]
            
            # Exponential Moving Average (EMA)
            if len(data) >= 20:
                indicators['ema_20'] = data['close'].ewm(span=20, adjust=False).mean().iloc[-1]
            
            # RSI
            if len(data) >= 14:
                delta = data['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                indicators['rsi'] = (100 - (100 / (1 + rs))).iloc[-1]
            
            # MACD
            if len(data) >= 26:
                exp1 = data['close'].ewm(span=12, adjust=False).mean()
                exp2 = data['close'].ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9, adjust=False).mean()
                indicators['macd'] = macd.iloc[-1]
                indicators['macd_signal'] = signal.iloc[-1]
                indicators['macd_hist'] = (macd - signal).iloc[-1]
            
            # Bollinger Bands
            if len(data) >= 20:
                sma = data['close'].rolling(window=20).mean()
                std = data['close'].rolling(window=20).std()
                indicators['bb_upper'] = (sma + (std * 2)).iloc[-1]
                indicators['bb_middle'] = sma.iloc[-1]
                indicators['bb_lower'] = (sma - (std * 2)).iloc[-1]
            
            # Additional indicators
            if len(data) >= 14:
                # CCI - Fixed calculation without using mad()
                tp = (data['high'] + data['low'] + data['close']) / 3
                sma_tp = tp.rolling(window=20).mean()
                # Calculate mean deviation manually
                md = tp.rolling(window=20).apply(lambda x: np.mean(np.abs(x - np.mean(x))))
                indicators['cci'] = ((tp - sma_tp) / (0.015 * md)).iloc[-1]
                
                # ADX
                tr = pd.DataFrame()
                tr['h-l'] = abs(data['high'] - data['low'])
                tr['h-pc'] = abs(data['high'] - data['close'].shift(1))
                tr['l-pc'] = abs(data['low'] - data['close'].shift(1))
                tr['tr'] = tr[['h-l', 'h-pc', 'l-pc']].max(axis=1)
                atr = tr['tr'].rolling(window=14).mean()
                indicators['atr'] = atr.iloc[-1]
            
            return indicators

        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return {}

    async def get_realtime_price_async(self, pair: str) -> Optional[Tuple[float, float]]:
        """Get real-time price data for a pair asynchronously"""
        try:
            # Remove _OTC suffix if present
            base_pair = pair.replace('_OTC', '')
            
            # Get the base currencies
            base_currency = base_pair[:3]  # First 3 characters
            quote_currency = base_pair[3:]  # Remaining characters
            
            # Get rates for both currencies
            base_rate = await self.get_currency_rate_async(base_currency)
            quote_rate = await self.get_currency_rate_async(quote_currency)
            
            if base_rate is None or quote_rate is None:
                print(f"Failed to get rates for {base_currency} or {quote_currency}")
                return None
                
            # Calculate the cross rate
            rate = base_rate / quote_rate
            
            # Add spread for OTC pairs
            spread = 0.0002  # 2 pips spread
            bid = rate * (1 - spread)
            ask = rate * (1 + spread)
            
            return (bid, ask)
            
        except Exception as e:
            print(f"Error in get_realtime_price_async: {str(e)}")
            return None 

    def _update_rate_limit(self, source_name: str):
        """Update rate limit tracking after an API call"""
        now = datetime.now()
        source = self.source_limits[source_name]
        
        # Update call counts
        source['call_count'] += 1
        source['last_call'] = now.timestamp()
        
        if source_name == 'Alpha Vantage':
            source['daily_calls'] += 1
            
        # Reset error count on successful call
        source['error_count'] = 0
        source['backoff_until'] = 0

    async def get_currency_rate_async(self, currency: str) -> Optional[float]:
        """Get currency rate asynchronously."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://www.alphavantage.co/query"
                params = {
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": currency,
                    "to_currency": "USD",  # Using USD as base
                    "apikey": self.api_key
                }
                
                async with session.get(url, params=params, timeout=API_TIMEOUT) as response:
                    data = await response.json()
                    
                    if "Realtime Currency Exchange Rate" in data:
                        return float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
                        
        except Exception as e:
            logger.error(f"Error getting async currency rate for {currency}: {str(e)}")
            
        return None 

    def _normalize_price(self, price: float, from_currency: str, to_currency: str) -> float:
        """
        Normalize the price based on currency pair to match broker format
        """
        try:
            # Special handling for BRL pairs to match Quotex format
            if 'BRL' in (from_currency, to_currency):
                if from_currency == 'USD' and to_currency == 'BRL':
                    return 1 / price  # Invert the rate to match Quotex format
                elif from_currency == 'BRL' and to_currency == 'USD':
                    return price  # Already in correct format
            
            # Add other special cases here as needed
            # For example, if we find other currency pairs that need normalization
            
            return price
            
        except Exception as e:
            logger.error(f"Error normalizing price: {str(e)}")
            return price  # Return original price if normalization fails 