"""
Forex data handling module with caching support.
"""

import requests
import logging
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, Union
from config import (
    ALPHA_VANTAGE_API_KEY,
    ALPHA_VANTAGE_BACKUP_KEY,
    OPENEXCHANGERATES_API_KEY,
    CURRENCYLAYER_API_KEY,
    API_TIMEOUT,
    CACHE_DURATION,
    FIXER_API_KEY
)

# Configure logging
logger = logging.getLogger(__name__)

# Cache for forex rates
_forex_cache: Dict[str, Dict[str, Any]] = {}

def get_cached_realtime_forex(pair: str, return_source: bool = False) -> Optional[Union[float, Tuple[float, str]]]:
    """
    Get real-time forex rate with caching support.
    
    Args:
        pair (str): Currency pair (e.g., "EURUSD")
        return_source (bool): Whether to return the data source along with the rate
        
    Returns:
        Optional[Union[float, Tuple[float, str]]]: Rate or (rate, source) if return_source is True
    """
    try:
        # Remove '/' from pair name if present
        pair = pair.replace('/', '')
        
        # Check cache first
        cache_key = f"forex_rate_{pair}"
        now = datetime.now()
        
        if cache_key in _forex_cache:
            cache_entry = _forex_cache[cache_key]
            cache_age = (now - datetime.fromisoformat(cache_entry['timestamp'])).total_seconds()
            
            # If cache is still valid, return cached data
            if cache_age < CACHE_DURATION:
                logger.debug(f"Cache hit for {pair}")
                if return_source:
                    return cache_entry['rate'], f"Cache ({cache_entry['source']})"
                return cache_entry['rate']
        
        # Try ExchangeRate-API first as it's more reliable
        result = _get_exchange_rate_api_rate(pair)
        if result is not None:
            rate, source = result if isinstance(result, tuple) else (result, 'ExchangeRate-API')
            # Update cache
            _forex_cache[cache_key] = {
                'rate': rate,
                'source': source,
                'timestamp': now.isoformat()
            }
            if return_source:
                return rate, source
            return rate
        
        # Track Alpha Vantage API calls
        av_calls_key = 'alpha_vantage_calls'
        if av_calls_key not in _forex_cache:
            _forex_cache[av_calls_key] = {'count': 0, 'reset_time': now}
        
        # Reset Alpha Vantage call counter if a day has passed
        av_calls = _forex_cache[av_calls_key]
        if (now - datetime.fromisoformat(av_calls['reset_time'])).total_seconds() > 86400:  # 24 hours
            av_calls['count'] = 0
            av_calls['reset_time'] = now.isoformat()
        
        # Try Alpha Vantage if we haven't exceeded daily limit
        if av_calls['count'] < 25:  # Free tier limit is 25 calls per day
            result = _get_alpha_vantage_rate(pair)
            if result is not None:
                rate, source = result if isinstance(result, tuple) else (result, 'Alpha Vantage')
                # Update cache
                _forex_cache[cache_key] = {
                    'rate': rate,
                    'source': source,
                    'timestamp': now.isoformat()
                }
                # Increment Alpha Vantage call counter
                av_calls['count'] += 1
                _forex_cache[av_calls_key] = av_calls
                
                if return_source:
                    return rate, source
                return rate
        
        # Try Fixer.io as last fallback
        result = _get_fixer_io_rate(pair)
        if result is not None:
            rate, source = result if isinstance(result, tuple) else (result, 'Fixer.io')
            # Update cache
            _forex_cache[cache_key] = {
                'rate': rate,
                'source': source,
                'timestamp': now.isoformat()
            }
            if return_source:
                return rate, source
            return rate
        
        # If all APIs fail but we have cached data, use it with a warning
        if cache_key in _forex_cache:
            logger.warning(f"All APIs failed for {pair}, using expired cache")
            cache_entry = _forex_cache[cache_key]
            if return_source:
                return cache_entry['rate'], f"Expired Cache ({cache_entry['source']})"
            return cache_entry['rate']
        
        logger.error(f"No data available for {pair} from any source")
        return None if not return_source else (None, "No Data")
        
    except Exception as e:
        logger.error(f"Error in get_cached_realtime_forex for {pair}: {str(e)}")
        return None if not return_source else (None, "Error")

def _get_alpha_vantage_rate(pair: str) -> Optional[Tuple[float, str]]:
    """Get rate from Alpha Vantage."""
    if not ALPHA_VANTAGE_API_KEY and not ALPHA_VANTAGE_BACKUP_KEY:
        logger.warning("No Alpha Vantage API keys configured")
        return None
        
    from_symbol = pair[:3]
    to_symbol = pair[3:]
    
    # Try primary key first
    if ALPHA_VANTAGE_API_KEY:
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_symbol}&to_currency={to_symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
        result = _try_alpha_vantage_request(url, pair)
        if result is not None:
            return result
            
    # Try backup key if primary fails
    if ALPHA_VANTAGE_BACKUP_KEY:
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_symbol}&to_currency={to_symbol}&apikey={ALPHA_VANTAGE_BACKUP_KEY}"
        result = _try_alpha_vantage_request(url, pair)
        if result is not None:
            return result
            
    return None

def _try_alpha_vantage_request(url: str, pair: str) -> Optional[Tuple[float, str]]:
    """Helper function to make Alpha Vantage API request."""
    try:
        logger.info(f"Fetching rate for {pair} from Alpha Vantage")
        response = requests.get(url, timeout=API_TIMEOUT)
        data = response.json()
        
        if "Error Message" in data:
            logger.error(f"Alpha Vantage API Error: {data['Error Message']}")
            return None
            
        if "Note" in data:
            note = data["Note"].lower()
            if "premium" in note:
                logger.warning("Alpha Vantage: Premium API features required")
                return None
            elif "api call frequency" in note:
                logger.warning(f"Alpha Vantage: Rate limit reached - {data['Note']}")
                return None
            
        if "Realtime Currency Exchange Rate" in data:
            try:
                rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
                if rate <= 0:
                    logger.error(f"Alpha Vantage: Invalid rate {rate} for {pair}")
                    return None
                logger.info(f"Successfully fetched rate for {pair} from Alpha Vantage: {rate}")
                return rate, "Alpha Vantage"
            except (KeyError, ValueError) as e:
                logger.error(f"Alpha Vantage: Error parsing rate for {pair}: {str(e)}")
                return None
            
    except Exception as e:
        logger.error(f"Error fetching from Alpha Vantage for {pair}: {str(e)}")
        
    return None

def _get_exchange_rate_api_rate(pair: str) -> Optional[Tuple[float, str]]:
    """Get rate from ExchangeRate-API."""
    from_symbol = pair[:3]
    to_symbol = pair[3:]
    url = f"https://open.er-api.com/v6/latest/{from_symbol}"
    
    try:
        logger.info(f"Fetching rate for {pair} from ExchangeRate-API")
        response = requests.get(url, timeout=API_TIMEOUT)
        data = response.json()
        
        if not data.get("result") == "success":
            error_type = data.get("error-type", "Unknown error")
            logger.error(f"ExchangeRate-API Error: {error_type}")
            return None
            
        rates = data.get("rates", {})
        if not rates or to_symbol not in rates:
            logger.error(f"ExchangeRate-API: No rate found for {to_symbol}")
            return None
            
        rate = float(rates[to_symbol])
        if rate <= 0:
            logger.error(f"ExchangeRate-API: Invalid rate {rate} for {pair}")
            return None
            
        logger.info(f"Successfully fetched rate for {pair} from ExchangeRate-API: {rate}")
        return rate, "ExchangeRate-API"
            
    except Exception as e:
        logger.error(f"Error fetching from ExchangeRate-API for {pair}: {str(e)}")
        
    return None

def _get_fixer_io_rate(pair: str) -> Optional[Tuple[float, str]]:
    """Get rate from Fixer.io."""
    from_symbol = pair[:3]
    to_symbol = pair[3:]
    
    # Use the configured API key from config
    url = f"https://api.exchangerate.host/latest?access_key={FIXER_API_KEY}&base={from_symbol}&symbols={to_symbol}"
    
    try:
        logger.info(f"Fetching rate for {pair} from Fixer.io")
        response = requests.get(url, timeout=API_TIMEOUT)
        data = response.json()
        
        if not data.get("success", False):
            error_info = data.get("error", {})
            logger.error(f"Fixer.io API Error: {error_info}")
            return None
            
        if data.get("rates") and to_symbol in data.get("rates", {}):
            rate = float(data["rates"][to_symbol])
            logger.info(f"Successfully fetched rate for {pair} from Fixer.io: {rate}")
            return rate, "Fixer.io"
            
    except Exception as e:
        logger.error(f"Error fetching from Fixer.io for {pair}: {str(e)}")
        
    return None