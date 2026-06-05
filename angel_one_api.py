#!/usr/bin/env python3
"""
Angel One SmartAPI Integration using Official Library
Provides real-time market data, historical data, and order execution
Based on: https://github.com/angel-one/smartapi-python
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import requests

# Official SmartAPI imports
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from SmartApi.smartWebSocketOrderUpdate import SmartWebSocketOrderUpdate
import pyotp
from logzero import logger
from rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

class AngelOneAPI:
    """Angel One SmartAPI client using official library"""
    
    def __init__(self, api_key: str, client_id: str, password: str, totp_secret: str):
        self.api_key = api_key
        self.client_id = client_id
        self.password = password  # This will be used as MPIN
        self.totp_secret = totp_secret
        self.smart_api = SmartConnect(api_key)
        self.access_token = None
        self.refresh_token = None
        self.feed_token = None
        self.is_connected = False
        self.demo_mode = False  # When True, funds/holdings/positions return mock data
        self._last_session_time = 0.0
        self._session_ttl = 10 * 3600  # Renew after 10 hours (Angel One sessions typically last 24h)
        self._renewal_thread = None
        # Instrument cache: {SYMBOL: (exchange, tradingsymbol, token)}
        self._instrument_map: Dict[str, Tuple[str, str, str]] = {}
    
    def set_demo_mode(self, enabled: bool):
        """Switch between demo (mock funds) and live (real broker) mode.
        Market data still flows from the real API regardless of mode."""
        self.demo_mode = enabled
        logger.info(f"AngelOneAPI demo_mode set to: {enabled}")
        
    def generate_session(self) -> bool:
        """Generate session and get access token using official SmartAPI"""
        try:
            # Generate TOTP
            totp = pyotp.TOTP(self.totp_secret).now()
            
            # Try MPIN login first (new method)
            try:
                data = self.smart_api.generateSessionByMPIN(self.client_id, self.password, totp)
            except AttributeError:
                # Fallback to regular session generation
                data = self.smart_api.generateSession(self.client_id, self.password, totp)
            
            if data['status'] == False:
                logger.error(f"Session generation failed: {data}")
                self.is_connected = False
                return False
            else:
                # Extract tokens
                self.refresh_token = data['data']['refreshToken']
                self.feed_token = self.smart_api.getfeedToken()
                self.access_token = self.smart_api.access_token
                
                # Get user profile to verify connection
                user_profile = self.smart_api.getProfile(self.refresh_token)
                
                logger.info("Angel One session generated successfully")
                logger.info(f"User Profile: {user_profile}")
                self.is_connected = True
                self._last_session_time = time.time()
                # Load instruments for symbol resolution
                try:
                    self._load_instruments()
                except Exception as ie:
                    logger.warning(f"Unable to load instruments: {ie}")
                # Start background session renewal if not already running
                self._start_session_renewal()
                return True
                
        except Exception as e:
            logger.error(f"Error generating session: {str(e)}")
            self.is_connected = False
            return False
    
    def _start_session_renewal(self):
        """Start background thread to renew session before expiry (like Dhan API does)"""
        if self._renewal_thread and self._renewal_thread.is_alive():
            return
        def renewal_loop():
            while self.is_connected:
                elapsed = time.time() - self._last_session_time
                remaining = max(0, self._session_ttl - elapsed)
                if remaining > 300:
                    sleep_for = remaining - 300  # Renew 5 minutes before expiry
                    logger.info(f"Angel One session renewal sleeping for {sleep_for/3600:.1f}h")
                    time.sleep(min(sleep_for, 3600))
                    continue
                logger.info("Angel One session expiring soon — renewing...")
                self.generate_session()
        self._renewal_thread = threading.Thread(target=renewal_loop, daemon=True, name="angel-session-renewal")
        self._renewal_thread.start()
        logger.info("Angel One session renewal background thread started")

    def get_profile(self) -> Dict:
        """Get user profile information"""
        try:
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            res = self.smart_api.getProfile(self.refresh_token)
            return res
        except Exception as e:
            logger.error(f"Error getting profile: {str(e)}")
            return {}
    
    def get_funds(self) -> Dict:
        """Get available funds — returns mock virtual funds in demo mode"""
        try:
            if self.demo_mode:
                logger.info("Returning mock funds (demo mode)")
                return {
                    "status": True,
                    "message": "DEMO MODE - Virtual funds (not real)",
                    "data": {
                        "net": "100000.00",
                        "availablecash": "100000.00",
                        "availableintradaypayin": "0",
                        "availablelimitmargin": "0",
                        "collateral": "0",
                        "m2munrealized": "0",
                        "m2mrealized": "0",
                        "utiliseddebits": "0",
                        "utilisedspan": "0",
                        "utilisedoptionpremium": "0",
                        "utiliseddelivery": "0",
                        "utilisedholdingssales": "0",
                        "utilisedexposure": "0",
                        "utilisedturnover": "0",
                        "utilisedpnl": "0",
                        "utilisedbrokerage": "0"
                    }
                }
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            res = self.smart_api.rmsLimit()
            return res
        except Exception as e:
            logger.error(f"Error getting funds: {str(e)}")
            return {}
    
    def get_holdings(self) -> Dict:
        """Get current holdings — returns empty list in demo mode"""
        try:
            if self.demo_mode:
                return {"status": True, "message": "DEMO MODE", "data": []}
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            res = self.smart_api.holding()
            return res
        except Exception as e:
            logger.error(f"Error getting holdings: {str(e)}")
            return {}
    
    def get_positions(self) -> Dict:
        """Get current positions — returns empty list in demo mode"""
        try:
            if self.demo_mode:
                return {"status": True, "message": "DEMO MODE", "data": []}
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            res = self.smart_api.position()
            return res
        except Exception as e:
            logger.error(f"Error getting positions: {str(e)}")
            return {}
    
    def get_historical_data(self, symbol: str, interval: str = "ONE_MINUTE", 
                          from_date: str = None, to_date: str = None) -> pd.DataFrame:
        """Get historical data for a symbol using official SmartAPI (matching your format)"""
        try:
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return pd.DataFrame()
                
            # Widen date window for indices like NIFTY50 to improve non-empty responses
            is_index = symbol and symbol.upper() in { 'NIFTY50', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX' }
            if not from_date:
                lookback_days = 30
                from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M")
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Resolve exchange, tradingsymbol and token
            exchange, tradingsymbol, symbol_token = self._resolve_symbol(symbol)
            logger.info(f"Getting historical data for {symbol} => exch={exchange}, ts={tradingsymbol}, token={symbol_token}")
            
            # Historic API call (matching your format exactly)
            historic_param = {
                "exchange": exchange,
                "symboltoken": symbol_token,
                "interval": interval,
                "fromdate": from_date, 
                "todate": to_date
            }
            
            logger.info(f"API call parameters: {historic_param}")
            
            max_retries = 3
            result = None
            for attempt in range(max_retries):
                rate_limiter.wait_if_needed('angel_one')
                try:
                    result = self.smart_api.getCandleData(historic_param)
                    rate_limiter.record_call('angel_one')
                    
                    # Check if API returned a rate limit error cleanly within the JSON
                    if result and not result.get("status"):
                        msg = result.get("message", "").lower()
                        if "exceed" in msg or "limit" in msg or "rate" in msg:
                            raise Exception(f"API Rate limit: {msg}")
                    
                    break  # Success
                except Exception as e:
                    msg = str(e).lower()
                    if 'access denied because of exceeding access rate' in msg or 'limit' in msg or "couldn't parse" in msg:
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2.0
                            logger.warning(f"Rate limit hit for {symbol}. Retrying in {wait_time}s (Attempt {attempt+1}/{max_retries}).")
                            time.sleep(wait_time)
                            continue
                    raise e
            
            logger.info(f"API response: {result}")
            
            if not result or not result.get("status"):
                logger.warning(f"No historical data for {symbol} - API response: {result}")
                return pd.DataFrame()
            
            raw_data = result.get("data")
            if not raw_data:
                logger.warning(f"No historical data for {symbol}")
                return pd.DataFrame()
            
            # SmartAPI returns list of rows: [timestamp, open, high, low, close, volume]
            if isinstance(raw_data, list) and len(raw_data) > 0 and isinstance(raw_data[0], list):
                df = pd.DataFrame(raw_data, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                return df
            
            # Some variants return nested under 'data' key as dict
            if isinstance(raw_data, dict) and 'data' in raw_data and isinstance(raw_data['data'], list):
                rows = raw_data['data']
                df = pd.DataFrame(rows, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                return df
            
            logger.warning(f"Unexpected historical data format for {symbol}: {type(raw_data)}")
            return pd.DataFrame()
                
        except Exception as e:
            # Handle known empty/ratelimit responses
            msg = str(e)
            if 'Access denied because of exceeding access rate' in msg or "couldn't parse" in msg.lower() or "Couldn't parse" in msg:
                logger.warning(f"Rate/parse issue for {symbol}: {msg}")
                return pd.DataFrame()
            logger.error(f"Error getting historical data: {str(e)}")
            return pd.DataFrame()
    
    def get_quote(self, symbols: List[str]) -> Dict:
        """Get real-time quotes for symbols using official SmartAPI"""
        try:
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            # Get quotes for each symbol individually
            result = {"data": {}}
            for symbol in symbols:
                clean_symbol = symbol.replace('.NS', '').upper()
                exchange, tradingsymbol, symbol_token = self._resolve_symbol(symbol)
                
                max_retries = 3
                for attempt in range(max_retries):
                    rate_limiter.wait_if_needed('angel_one')
                    try:
                        # SmartAPI ltpData(exchange, tradingsymbol, symboltoken)
                        quote_result = self.smart_api.ltpData(exchange, tradingsymbol, symbol_token)
                        rate_limiter.record_call('angel_one')
                        
                        if quote_result and quote_result.get("status"):
                            result["data"][clean_symbol] = quote_result.get("data", {})
                            break  # Success
                        else:
                            msg = quote_result.get("message", "").lower() if quote_result else ""
                            if "exceed" in msg or "limit" in msg or "rate" in msg:
                                raise Exception(f"API Rate limit: {msg}")
                            logger.warning(f"No quote data for {clean_symbol}")
                            break  # Stop retrying if it's a non-rate-limit error
                    except Exception as e:
                        msg = str(e).lower()
                        if 'access denied because of exceeding access rate' in msg or 'limit' in msg or "couldn't parse" in msg:
                            if attempt < max_retries - 1:
                                wait_time = (attempt + 1) * 1.0
                                logger.warning(f"Rate limit hit for {clean_symbol}. Retrying in {wait_time}s...")
                                time.sleep(wait_time)
                                continue
                        logger.warning(f"Error getting quote for {clean_symbol}: {str(e)}")
                        break
            
            return result
                
        except Exception as e:
            logger.error(f"Error getting quotes: {str(e)}")
            return {}
    
    def place_order(self, symbol: str, quantity: int, order_type: str, 
                   product_type: str, price: float = None, trigger_price: float = None) -> Dict:
        """Place an order using official SmartAPI — simulates in demo mode"""
        try:
            if self.demo_mode:
                logger.info(f"SIMULATED order in demo mode: {order_type} {quantity} {symbol} @ {price}")
                return {
                    "status": True,
                    "data": {
                        "orderid": f"DEMO_{int(time.time())}",
                        "message": "Simulated order (demo mode)"
                    }
                }
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            # Get resolved symbol info using dynamic lookup or static fallback
            exchange, tradingsymbol, symbol_token = self._resolve_symbol(symbol)
            
            # Clean symbol (remove .NS if present)
            clean_symbol = symbol.replace('.NS', '').upper()
            
            # Indices use NSE for order placement; otherwise keep the resolved exchange
            # (e.g., BSE, NFO, MCX, CDS) to support stocks, commodities, derivatives, etc.
            if exchange == "NSE_INDICES":
                order_exchange = "NSE"
            else:
                order_exchange = exchange
            
            # For indices like NIFTY50, use the proper tradingsymbol and token from _resolve_symbol
            # For stocks, Angel One SmartAPI v2 expects the exact tradingsymbol as per exchange
            # Do NOT add -EQ suffix; SmartAPI handles this internally when exchange=NSE
            final_tradingsymbol = tradingsymbol
            
            # If we get a symbol from _get_symbol_token that returned "1", try better lookup
            if symbol_token == "1" and clean_symbol not in ['SENSEX']:
                # Try to fetch actual token from instrument list if loaded
                inst = self._instrument_map.get(clean_symbol)
                if inst:
                    _, final_tradingsymbol, symbol_token = inst
                    logger.info(f"Dynamic lookup resolved {clean_symbol} -> {final_tradingsymbol}, token={symbol_token}")
                else:
                    logger.error(f"CRITICAL: Unable to resolve token for {clean_symbol}. Order will fail.")
                    return {
                        "status": False,
                        "error": f"Symbol token not found for {clean_symbol}. Please refresh instruments."
                    }
                
            # Order parameters (matching your format exactly)
            orderparams = {
                "variety": "NORMAL",
                "tradingsymbol": final_tradingsymbol,
                "symboltoken": symbol_token,
                "transactiontype": order_type,
                "exchange": order_exchange,
                "ordertype": "LIMIT" if price else "MARKET",
                "producttype": product_type,
                "duration": "DAY",
                "price": str(price) if price else "0",
                "squareoff": "0",
                "stoploss": str(trigger_price) if trigger_price else "0",
                "quantity": str(quantity)
            }
            
            logger.info(f"Placing order: {orderparams}")
            
            # Place order using official method (matching your format)
            rate_limiter.wait_if_needed('angel_one')
            orderid = self.smart_api.placeOrder(orderparams)
            rate_limiter.record_call('angel_one')
            
            if orderid:
                return {
                    "status": True,
                    "data": {
                        "orderid": orderid,
                        "message": "Order placed successfully"
                    }
                }
            else:
                return {
                    "status": False,
                    "error": "Failed to place order"
                }
                
        except Exception as e:
            logger.error(f"Error placing order: {str(e)}")
            return {
                "status": False,
                "error": str(e)
            }
    
    def modify_order(self, order_id: str, quantity: int = None, 
                    price: float = None, order_type: str = None) -> Dict:
        """Modify an existing order using official SmartAPI — simulates in demo mode"""
        try:
            if self.demo_mode:
                return {"status": True, "data": {"orderid": order_id, "message": "Simulated modify (demo mode)"}}
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            modifyparams = {
                "variety": "NORMAL",
                "orderid": order_id,
                "ordertype": order_type or "LIMIT",
                "producttype": "INTRADAY",
                "duration": "DAY",
                "price": str(price) if price else "0",
                "quantity": str(quantity) if quantity else "0"
            }
            
            result = self.smart_api.modifyOrder(modifyparams)
            return result
                
        except Exception as e:
            logger.error(f"Error modifying order: {str(e)}")
            return {}
    
    def cancel_order(self, order_id: str) -> Dict:
        """Cancel an order using official SmartAPI — simulates in demo mode"""
        try:
            if self.demo_mode:
                return {"status": True, "message": "Simulated cancel (demo mode)"}
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            cancelparams = {
                "variety": "NORMAL",
                "orderid": order_id
            }
            
            result = self.smart_api.cancelOrder(cancelparams)
            return result
                
        except Exception as e:
            logger.error(f"Error cancelling order: {str(e)}")
            return {}
    
    def get_order_book(self) -> Dict:
        """Get order book using official SmartAPI"""
        try:
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            result = self.smart_api.orderBook()
            return result
        except Exception as e:
            logger.error(f"Error getting order book: {str(e)}")
            return {}
    
    def get_trade_book(self) -> Dict:
        """Get trade book using official SmartAPI"""
        try:
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            result = self.smart_api.tradeBook()
            return result
        except Exception as e:
            logger.error(f"Error getting trade book: {str(e)}")
            return {}
    
    def _get_symbol_token(self, symbol: str) -> str:
        """Get symbol token for Angel One - UPDATED with correct tokens"""
        symbol_tokens = {
            "NIFTY50": "26000",
            "BANKNIFTY": "26009", 
            "SENSEX": "1",
            "RELIANCE": "2885",
            "TCS": "11536",
            "HDFCBANK": "3416",
            "INFY": "1594",
            "ICICIBANK": "4963",
            "SBIN": "3045",
            "BHARTIARTL": "10604",
            "KOTAKBANK": "1922",
            "BAJFINANCE": "317",
            "HINDUNILVR": "1394",
            "WIPRO": "4226",
            "ITC": "16669",
            "ASIANPAINT": "1605",
            "MARUTI": "3252",
            "TITAN": "3506",
            "NESTLEIND": "21862",
            "POWERGRID": "2278"
        }
        
        clean_symbol = symbol.replace('.NS', '')
        return symbol_tokens.get(clean_symbol, "1")
    
    def get_market_status(self) -> Dict:
        """Get market status using official SmartAPI"""
        try:
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            # Use getMarketData with required parameters
            mode = "FULL"
            exchange_tokens = {"NSE": ["26000"]}  # NIFTY50 token
            result = self.smart_api.getMarketData(mode, exchange_tokens)
            return result
        except AttributeError:
            # Fallback if method doesn't exist
            logger.warning("getMarketData method not available, returning mock data")
            return {"data": {"market": True}}
        except Exception as e:
            logger.error(f"Error getting market status: {str(e)}")
            return {"data": {"market": True}}
    
    def get_indices(self) -> Dict:
        """Get market indices using official SmartAPI"""
        try:
            if not self.is_connected:
                logger.error("Not connected to Angel One API")
                return {}
                
            result = self.smart_api.getIndices()
            return result
        except Exception as e:
            logger.error(f"Error getting indices: {str(e)}")
            return {}
    
    def terminate_session(self) -> bool:
        """Terminate session using official SmartAPI (matching your format)"""
        try:
            if not self.is_connected:
                return True
                
            # Logout (matching your format exactly)
            logout = self.smart_api.terminateSession(self.client_id)
            self.is_connected = False
            logger.info("Logout Successful")
            return True
        except Exception as e:
            logger.error(f"Logout failed: {str(e)}")
            return False

    def _load_instruments(self) -> None:
        """Load Angel One instrument list from master JSON to resolve symbols."""
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        temp_map: Dict[str, Tuple[str, str, str]] = {}
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            instruments = resp.json()
            for ins in instruments or []:
                exch = ins.get('exch_seg', '').upper()
                if exch not in ("NSE", "BSE", "NFO", "NSE_INDICES"):
                    continue
                symbol_key = (ins.get('symbol') or ins.get('name') or ins.get('tradingsymbol') or "").upper()
                tradingsymbol = ins.get('tradingsymbol') or symbol_key
                token = str(ins.get('token') or ins.get('symboltoken') or "").strip()
                if symbol_key and token:
                    temp_map[symbol_key] = (exch, tradingsymbol, token)
        except Exception as e:
            logger.warning(f"Instrument master download failed: {e}")
        if temp_map:
            self._instrument_map = temp_map
            logger.info(f"Instrument map loaded: {len(self._instrument_map)} symbols")

    def _resolve_symbol(self, symbol: str) -> Tuple[str, str, str]:
        """Resolve (exchange, tradingsymbol, token) for a display symbol."""
        clean_symbol = symbol.replace('.NS', '').upper()
        
        static_map: Dict[str, Tuple[str, str, str]] = {
            'NIFTY50': ("NSE_INDICES", "NIFTY 50", "26000"),
            'BANKNIFTY': ("NSE_INDICES", "NIFTY BANK", "26009"),
            'FINNIFTY': ("NSE_INDICES", "NIFTY FIN SERVICE", "26037"),
            'MIDCPNIFTY': ("NSE_INDICES", "NIFTY MIDCAP 50", "26017"),
            'SENSEX': ("BSE", "SENSEX", "1"),
            'RELIANCE': ("NSE", "RELIANCE-EQ", "2885"),
            'TCS': ("NSE", "TCS-EQ", "11536"),
            'HDFCBANK': ("NSE", "HDFCBANK-EQ", "3416"),
            'INFY': ("NSE", "INFY-EQ", "1594"),
            'ICICIBANK': ("NSE", "ICICIBANK-EQ", "4963"),
            'HINDUNILVR': ("NSE", "HINDUNILVR-EQ", "1394"),
            'SBIN': ("NSE", "SBIN-EQ", "3045"),
            'BHARTIARTL': ("NSE", "BHARTIARTL-EQ", "10604"),
            'KOTAKBANK': ("NSE", "KOTAKBANK-EQ", "1922"),
            'BAJFINANCE': ("NSE", "BAJFINANCE-EQ", "317"),
        }
        if clean_symbol in static_map:
            return static_map[clean_symbol]
        # Fall back to loaded instrument map for unknown symbols
        if clean_symbol in self._instrument_map:
            return self._instrument_map[clean_symbol]
        # Fallback
        return ("NSE", clean_symbol, self._get_symbol_token(clean_symbol))

class AngelOneWebSocket:
    """WebSocket handler for real-time data using official SmartAPI (matching your format)"""
    
    def __init__(self, api_client: AngelOneAPI):
        self.api_client = api_client
        self.sws = None
        self.order_ws = None
        self.subscribed_symbols = set()
        self.on_price_update = None
        
    def start_streaming(self, on_price_update_callback):
        """Start WebSocket streaming in the background"""
        self.on_price_update = on_price_update_callback
        
        def on_data(ws, message):
            try:
                # Angel One SmartWebSocketV2 returns ticks as list of dicts
                # Handle both list-of-dicts and single-dict formats
                ticks = message if isinstance(message, list) else [message] if isinstance(message, dict) else []
                for tick in ticks:
                    if not isinstance(tick, dict):
                        continue
                    token = tick.get('token')
                    # Angel One SmartWebSocketV2 returns last_traded_price as:
                    #   int (paise × 100) — e.g. 173545 for ₹1,735.45
                    #   float (already decimal) — e.g. 1735.45
                    # Check using isinstance to avoid 100x drops.
                    raw_raw = tick.get('last_traded_price')
                    if raw_raw is None:
                        raw_raw = tick.get('ltp', 0)
                    if not token or not raw_raw:
                        continue
                    if isinstance(raw_raw, int):
                        price = float(raw_raw) / 100.0
                    else:
                        price = float(raw_raw)

                    # Map token back to symbol
                    symbol = self._get_symbol_by_token(token)
                    if symbol and self.on_price_update:
                        self.on_price_update(symbol, price)
            except Exception as e:
                logger.error(f"WebSocket tick processing error: {e}", exc_info=True)
                
        def on_open(ws):
            logger.info("Angel One WebSocket Connected")
            self._resubscribe_all()
            
        def on_error(ws, error):
            logger.error(f"Angel One WebSocket Error: {error}")
            
        def on_close(ws, code, reason):
            logger.warning(f"Angel One WebSocket Closed: {reason}")
            self.api_client.is_connected = False
            # Auto-reconnect after 10 seconds
            import threading as _th
            def _reconnect():
                _th.Thread(target=self._auto_reconnect, daemon=True).start()
            _th.Thread(target=_reconnect, daemon=True).start()
            
        def run_ws():
            self.connect_websocket(on_data, on_open, on_error, on_close)
        
        import threading
        threading.Thread(target=run_ws, daemon=True).start()
        return True

    def subscribe(self, symbol: str):
        """Add a symbol to WS subscriptions dynamically"""
        if symbol in self.subscribed_symbols:
            return
        self.subscribed_symbols.add(symbol)
        if self.sws:
            exchange, _, token = self.api_client._resolve_symbol(symbol)
            exchange_type = 3 if exchange == "BSE" else (2 if exchange == "NFO" else 1)
            self.subscribe_to_tokens("streaming_ltp", 1, [{"exchangeType": exchange_type, "tokens": [token]}])

    def unsubscribe(self, symbol: str):
        """Remove a symbol from WS subscriptions"""
        if symbol in self.subscribed_symbols:
            self.subscribed_symbols.remove(symbol)
        if self.sws:
            exchange, _, token = self.api_client._resolve_symbol(symbol)
            exchange_type = 3 if exchange == "BSE" else (2 if exchange == "NFO" else 1)
            self.unsubscribe_from_tokens("streaming_ltp", 1, [{"exchangeType": exchange_type, "tokens": [token]}])

    def _resubscribe_all(self):
        if not self.sws or not self.subscribed_symbols:
            return
        token_map = {}
        for symbol in self.subscribed_symbols:
            exchange, _, token = self.api_client._resolve_symbol(symbol)
            exchange_type = 3 if exchange == "BSE" else (2 if exchange == "NFO" else 1)
            if exchange_type not in token_map:
                token_map[exchange_type] = []
            token_map[exchange_type].append(token)
        token_list = [{"exchangeType": k, "tokens": v} for k, v in token_map.items()]
        self.subscribe_to_tokens("streaming_ltp", 1, token_list)

    def _get_symbol_by_token(self, token: str) -> str:
        # Verified map takes priority over instrument map for correct display symbols
        static_map = {"26000": "NIFTY50", "26009": "BANKNIFTY", "26037": "FINNIFTY", "1": "SENSEX"}
        if token in static_map: return static_map[token]
        symbol_tokens = {"RELIANCE": "2885", "TCS": "11536", "HDFCBANK": "3416", "INFY": "1594", "ICICIBANK": "4963", "SBIN": "3045", "BHARTIARTL": "10604", "KOTAKBANK": "1922", "BAJFINANCE": "317", "HINDUNILVR": "1394", "WIPRO": "4226", "ITC": "16669", "ASIANPAINT": "1605", "MARUTI": "3252", "TITAN": "3506", "NESTLEIND": "21862", "POWERGRID": "2278"}
        for k, v in symbol_tokens.items():
            if v == token: return k
        # Fall back to instrument map, stripping suffixes like -EQ, -BE, etc
        suffixes = ("-EQ", "-BE", "-BL", "-IQ", "-RL", "-AF", "-U3", "-U4", "-BB")
        for sym, (exch, ts, tok) in self.api_client._instrument_map.items():
            if tok == token:
                for sfx in suffixes:
                    if sym.upper().endswith(sfx):
                        return sym[:-len(sfx)]
                return sym
        return None
        
    def connect_websocket(self, on_data_callback, on_open_callback=None, on_error_callback=None, on_close_callback=None):
        """Connect to WebSocket for real-time data (matching your format)"""
        try:
            if not self.api_client.is_connected:
                logger.error("API client not connected")
                return False
                
            # WebSocket connection (matching your format)
            self.sws = SmartWebSocketV2(
                self.api_client.access_token,   # auth_token: JWT from SmartConnect session
                self.api_client.api_key,         # api_key: SmartAPI key
                self.api_client.client_id,       # client_code: Angel One client ID
                self.api_client.feed_token,       # feed_token: from SmartConnect session
                max_retry_attempt=5,             # Allow retries
                retry_strategy=1,                # Exponential backoff
                retry_delay=5,                   # Start at 5s
                retry_multiplier=2,              # Double each time: 5,10,20,40,80
                retry_duration=60                # Max retry duration in minutes
            )
            
            # Monkey-patch _on_close to accept *args from websocket-client 1.x
            def _patched_on_close(wsapp, *args):
                if args:
                    logger.info(f"Angel One WS closing: code={args[0]}")
                if self.sws and self.sws.on_close:
                    self.sws.on_close(wsapp, *args)
            self.sws._on_close = _patched_on_close
            
            # IMPORTANT: Use correct callback attribute names expected by the library
            # Library calls self.on_data() and self.on_open(), NOT on_ticks/on_connect
            self.sws.on_data = on_data_callback
            self.sws.on_open = on_open_callback or self._on_open
            self.sws.on_error = on_error_callback or self._on_error
            self.sws.on_close = on_close_callback or self._on_close
            
            self.sws.connect()
            return True
            
        except Exception as e:
            logger.error(f"Error connecting WebSocket: {str(e)}")
            return False
    
    def subscribe_to_tokens(self, correlation_id: str, mode: int, token_list: List[Dict]):
        """Subscribe to specific tokens"""
        try:
            if self.sws:
                self.sws.subscribe(correlation_id, mode, token_list)
                return True
            return False
        except Exception as e:
            logger.error(f"Error subscribing to tokens: {str(e)}")
            return False
    
    def send_request(self, token: str, task: str):
        """Send request to WebSocket (matching your format)"""
        try:
            if self.sws:
                self.sws.send_request(token, task)
                return True
            return False
        except Exception as e:
            logger.error(f"Error sending request: {str(e)}")
            return False
    
    def unsubscribe_from_tokens(self, correlation_id: str, mode: int, token_list: List[Dict]):
        """Unsubscribe from specific tokens"""
        try:
            if self.sws:
                self.sws.unsubscribe(correlation_id, mode, token_list)
                return True
            return False
        except Exception as e:
            logger.error(f"Error unsubscribing from tokens: {str(e)}")
            return False
    
    def connect_order_websocket(self):
        """Connect to order update WebSocket"""
        try:
            if not self.api_client.is_connected:
                logger.error("API client not connected")
                return False
                
            self.order_ws = SmartWebSocketOrderUpdate(
                self.api_client.access_token,
                self.api_client.api_key,
                self.api_client.client_id,
                self.api_client.feed_token
            )
            
            self.order_ws.connect()
            return True
            
        except Exception as e:
            logger.error(f"Error connecting order WebSocket: {str(e)}")
            return False
    
    def close_connection(self):
        """Close WebSocket connection"""
        try:
            if self.sws:
                self.sws.close_connection()
            if self.order_ws:
                self.order_ws.close_connection()
        except Exception as e:
            logger.error(f"Error closing WebSocket: {str(e)}")
    
    def _auto_reconnect(self):
        """Auto-reconnect WebSocket after disconnect with exponential backoff"""
        import time as _time
        for attempt in range(1, 6):
            _time.sleep(10 * attempt)
            if self.api_client.is_connected:
                logger.info("Auto-reconnect skipped — already connected")
                return
            try:
                logger.info(f"Auto-reconnect attempt {attempt}/5...")
                ok = self.api_client.generate_session()
                if not ok:
                    logger.warning(f"Session re-auth failed on attempt {attempt}")
                    continue
                # Reconnect WebSocket with fresh tokens
                on_data = getattr(self.sws, 'on_data', None) if self.sws else None
                on_open = getattr(self.sws, 'on_open', None) if self.sws else None
                on_error = getattr(self.sws, 'on_error', None) if self.sws else None
                on_close = getattr(self.sws, 'on_close', None) if self.sws else None
                self.connect_websocket(on_data, on_open, on_error, on_close)
                if self.api_client.is_connected:
                    logger.info("Auto-reconnect successful")
                    return
            except Exception as e:
                logger.warning(f"Auto-reconnect attempt {attempt} failed: {e}")
        logger.warning("Auto-reconnect exhausted after 5 attempts")

    def _on_connect(self, ws, response):
        """WebSocket connection opened (matching your format)"""
        logger.info("WebSocket connection opened")
        ws.websocket_connection()  # Websocket connection
        
    def _on_error(self, wsapp, error):
        logger.error(f"WebSocket error: {error}")
    
    def _on_close(self, ws, *args):
        """WebSocket connection closed"""
        logger.info(f"Angel One WS closed (code={args[0] if args else '?'})")

class AngelOneDataProvider:
    """Data provider for Angel One API integration using official library"""
    
    def __init__(self, api_client: AngelOneAPI):
        self.api_client = api_client
        self.cache = {}
        self.cache_duration = 60  # 1 minute cache
        self.history_cache = {}
        self.history_ttl = 120  # seconds
        
    def get_real_time_price(self, symbol: str) -> Dict:
        """Get real-time price for a symbol"""
        try:
            # Check cache first
            cache_key = f"price_{symbol}"
            if cache_key in self.cache:
                cached_data, timestamp = self.cache[cache_key]
                if time.time() - timestamp < self.cache_duration:
                    return cached_data
            
            # Fetch from API
            quotes = self.api_client.get_quote([symbol])
            if quotes and quotes.get("data"):
                # Extract price data from official API response
                price_data = quotes["data"]
                
                # Find the symbol in the response
                symbol_key = symbol.replace('.NS', '')
                if symbol_key in price_data:
                    data = price_data[symbol_key]
                    result = {
                        'price': float(data.get('ltp', 0)),
                        'open': float(data.get('open', 0)),
                        'high': float(data.get('high', 0)),
                        'low': float(data.get('low', 0)),
                        'close': float(data.get('close', 0)),
                        'volume': int(data.get('volume', 0)),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # Cache the result
                    self.cache[cache_key] = (result, time.time())
                    return result
                else:
                    logger.warning(f"No real-time data for {symbol}")
                    return {}
            else:
                logger.warning(f"No real-time data for {symbol}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting real-time price: {str(e)}")
            return {}
    
    def get_historical_data(self, symbol: str, interval: str = "1d", 
                          period: str = "1mo") -> pd.DataFrame:
        """Get historical data for a symbol"""
        try:
            # Map friendly intervals to SmartAPI intervals
            interval_map = {
                '1m': 'ONE_MINUTE',
                '5m': 'FIVE_MINUTE',
                '15m': 'FIFTEEN_MINUTE',
                '30m': 'THIRTY_MINUTE',
                '60m': 'ONE_HOUR',
                '1d': 'ONE_DAY',
                'ONE_MINUTE': 'ONE_MINUTE',
                'FIVE_MINUTE': 'FIVE_MINUTE',
                'FIFTEEN_MINUTE': 'FIFTEEN_MINUTE',
                'THIRTY_MINUTE': 'THIRTY_MINUTE',
                'ONE_HOUR': 'ONE_HOUR',
                'ONE_DAY': 'ONE_DAY'
            }
            smart_interval = interval_map.get(interval, 'ONE_DAY')
            
            # Cache key
            now_ts = int(time.time())
            cache_key = (symbol.upper(), smart_interval)
            cached = self.history_cache.get(cache_key)
            if cached and now_ts - cached['ts'] < self.history_ttl:
                return cached['df']
            
            # Primary fetch
            df = self.api_client.get_historical_data(symbol, smart_interval)
            
            # If empty and symbol looks like index, retry on NSE_INDICES
            if (df is None or df.empty):
                index_like = symbol.upper() in { 'NIFTY50', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'NIFTYREALTY', 'NIFTYPVTBANK', 'NIFTYPSUBANK', 'NIFTYMEDIA' }
                if index_like:
                    try:
                        exch, ts, token = self.api_client._resolve_symbol(symbol)
                        # Force exchange to NSE_INDICES
                        if exch != 'NSE_INDICES':
                            logger.info(f"Retrying {symbol} on NSE_INDICES fallback")
                            # Temporarily override resolution for retry
                            original_resolve = self.api_client._resolve_symbol
                            def resolve_indices(sym):
                                e, t, tok = original_resolve(sym)
                                return ('NSE_INDICES', t, tok)
                            self.api_client._resolve_symbol = resolve_indices
                            try:
                                df = self.api_client.get_historical_data(symbol, smart_interval)
                            finally:
                                self.api_client._resolve_symbol = original_resolve
                    except Exception as e:
                        logger.warning(f"Index fallback failed for {symbol}: {e}")
            
            if df is None:
                df = pd.DataFrame()
            
            # Store cache
            self.history_cache[cache_key] = { 'ts': now_ts, 'df': df }
            return df
        except Exception as e:
            logger.error(f"Error getting historical data: {str(e)}")
            return pd.DataFrame()
    
    def is_market_open(self) -> bool:
        """Check if market is open"""
        try:
            market_status = self.api_client.get_market_status()
            if market_status and market_status.get("data"):
                return market_status["data"].get("market", False)
            return False
        except Exception as e:
            logger.error(f"Error checking market status: {str(e)}")
            return False