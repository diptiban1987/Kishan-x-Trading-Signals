from flask_socketio import SocketIO, emit
from flask import session, request
from datetime import datetime, timedelta, time
import json
import logging
from typing import Dict, Optional, Union, Tuple
import yfinance as yf
import pandas as pd
import numpy as np
import time
import random
import asyncio
import pytz
from forex_data import get_cached_realtime_forex as get_forex_rate
try:
    import pandas_ta as ta
except ImportError:
    ta = None
from scipy.stats import norm
import math

logger = logging.getLogger(__name__)

REAL_FOREX_SYMBOLS = {'AUDUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY'}
REAL_INDIAN_SYMBOLS = {
    # Major Indices
    'NIFTY50', 'BANKNIFTY', 'SENSEX', 'FINNIFTY', 'MIDCPNIFTY',
    # Sector Indices
    'NIFTYREALTY', 'NIFTYPVTBANK', 'NIFTYPSUBANK', 'NIFTYFIN', 'NIFTYMEDIA',
    # Popular Stocks
    'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'HINDUNILVR', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'BAJFINANCE'
}

class WebSocketHandler:
    def __init__(self, socketio):
        self.socketio = socketio
        self.connected_users = {}
        self.subscribed_symbols = {}
        self.price_cache = {}
        self.last_update = {}
        self.last_request_time = {}
        self.min_request_interval = 1  # Reduced from 2 seconds to 1 second
        self.rate_limit_backoff = {}
        self.max_backoff = 30
        self.forex_symbols = {
            'AUDUSD': 'AUDUSD=X',
            'EURUSD': 'EURUSD=X',
            'GBPUSD': 'GBPUSD=X',
            'USDJPY': 'USDJPY=X',
            'USDCAD': 'USDCAD=X',
            'USDCHF': 'USDCHF=X',
            'NZDUSD': 'NZDUSD=X',
            'EURGBP': 'EURGBP=X',
            'EURJPY': 'EURJPY=X',
            'GBPJPY': 'GBPJPY=X'
        }
        # Indian index symbols mapping
        self.indian_symbols = {
            'NIFTY50': '^NSEI',  # NSE NIFTY 50
            'BANKNIFTY': '^NSEBANK',  # NSE BANK NIFTY
            'SENSEX': '^BSESN',  # BSE SENSEX
            'FINNIFTY': '^CNXFIN',  # NSE FINANCIAL SERVICES
            'MIDCPNIFTY': '^NSEMDCP50',  # NSE MIDCAP 50
            # Sector Indices
            'NIFTYREALTY': '^CNXREALTY',
            'NIFTYPVTBANK': '^NIFTYBANK',
            'NIFTYPSUBANK': '^CNXPSUBANK',
            'NIFTYFIN': '^CNXFIN',
            'NIFTYMEDIA': '^CNXMEDIA',
            # Popular Stocks
            'RELIANCE': 'RELIANCE.NS',
            'TCS': 'TCS.NS',
            'HDFCBANK': 'HDFCBANK.NS',
            'INFY': 'INFY.NS',
            'ICICIBANK': 'ICICIBANK.NS',
            'HINDUNILVR': 'HINDUNILVR.NS',
            'SBIN': 'SBIN.NS',
            'BHARTIARTL': 'BHARTIARTL.NS',
            'KOTAKBANK': 'KOTAKBANK.NS',
            'BAJFINANCE': 'BAJFINANCE.NS'
        }
        # Initialize OTC data handler
        from otc_data import OTCDataHandler
        from config import ALPHA_VANTAGE_API_KEY
        self.otc_handler = OTCDataHandler(api_key=ALPHA_VANTAGE_API_KEY)
        self.setup_handlers()
        
    def setup_handlers(self):
        """Setup WebSocket event handlers"""
        @self.socketio.on('connect')
        def handle_connect():
            if 'user_id' not in session:
                logger.warning("Unauthenticated WebSocket connection attempt")
                return False
            return self.handle_connect(session['user_id'])
            
        @self.socketio.on('disconnect')
        def handle_disconnect():
            if 'user_id' in session:
                self.handle_disconnect(session['user_id'])
            
        @self.socketio.on('subscribe')
        def handle_subscribe(data):
            try:
                if 'user_id' not in session:
                    logger.warning("Unauthenticated subscription attempt")
                    return False
                    
                symbol = data.get('symbol')
                if not symbol:
                    logger.warning("No symbol provided for subscription")
                    return False
                    
                # Clean up the symbol
                symbol = symbol.replace('/', '')
                return self.subscribe_symbol(session['user_id'], symbol)
            except Exception as e:
                logger.error(f'Error handling subscription: {str(e)}')
                return False
                
        @self.socketio.on('unsubscribe')
        def handle_unsubscribe(data):
            try:
                if 'user_id' not in session:
                    logger.warning("Unauthenticated unsubscribe attempt")
                    return False
                    
                symbol = data.get('symbol')
                if not symbol:
                    logger.warning("No symbol provided for unsubscribe")
                    return False
                    
                # Clean up the symbol
                symbol = symbol.replace('/', '')
                return self.unsubscribe_symbol(session['user_id'], symbol)
            except Exception as e:
                logger.error(f'Error handling unsubscription: {str(e)}')
                return False

    def handle_connect(self, user_id):
        """Handle new WebSocket connection with improved error handling."""
        try:
            self.connected_users[user_id] = {
                'sid': request.sid,
                'subscriptions': set(),
                'last_update': {},
                'error_count': 0
            }
            logger.info(f"User {user_id} connected via WebSocket")
            return True
        except Exception as e:
            logger.error(f"Error handling WebSocket connection: {str(e)}")
            return False

    def handle_disconnect(self, user_id):
        """Handle WebSocket disconnection with cleanup."""
        try:
            if user_id in self.connected_users:
                # Clean up subscriptions
                for symbol in self.connected_users[user_id]['subscriptions']:
                    self.unsubscribe_symbol(user_id, symbol)
                del self.connected_users[user_id]
                logger.info(f"User {user_id} disconnected from WebSocket")
        except Exception as e:
            logger.error(f"Error handling WebSocket disconnection: {str(e)}")

    async def subscribe_symbol(self, user_id, symbol):
        """Subscribe user to symbol updates"""
        try:
            if user_id not in self.connected_users:
                logger.warning(f"User {user_id} not connected")
                return False

            # Extract symbol string if it's a SQLite Row object
            if hasattr(symbol, 'symbol'):
                symbol = symbol.symbol
            elif isinstance(symbol, dict) and 'symbol' in symbol:
                symbol = symbol['symbol']

            # Add to user's subscriptions
            self.connected_users[user_id]['subscriptions'].add(symbol)

            # Send initial data
            data = await self.get_latest_price_data(symbol)
            if data:
                self.socketio.emit('price_update', data, room=request.sid)
                logger.info(f"User {user_id} subscribed to {symbol} with initial data")
                
                # Start periodic updates
                await self.start_periodic_updates(user_id, symbol)
                return True
            return False
        except Exception as e:
            logger.error(f"Error subscribing to symbol {symbol}: {str(e)}")
            return False

    async def start_periodic_updates(self, user_id, symbol):
        """Start periodic updates for a symbol"""
        try:
            async def update():
                while True:  # Keep running until unsubscribed
                    if user_id in self.connected_users and symbol in self.connected_users[user_id]['subscriptions']:
                        data = await self.get_latest_price_data(symbol)
                        if data:
                            self.socketio.emit('price_update', data, room=self.connected_users[user_id]['sid'])
                            logger.debug(f"Sent periodic update for {symbol} to user {user_id}")
                        await asyncio.sleep(1)  # Update every second
                    else:
                        break  # Stop if user is no longer subscribed
            
            # Start the update loop as a background task
            self.socketio.start_background_task(update)
            logger.info(f"Started periodic updates for {symbol} for user {user_id}")
        except Exception as e:
            logger.error(f"Error starting periodic updates for {symbol}: {str(e)}")

    def unsubscribe_symbol(self, user_id, symbol):
        """Unsubscribe user from symbol updates"""
        try:
            if user_id in self.connected_users and symbol in self.connected_users[user_id]['subscriptions']:
                self.connected_users[user_id]['subscriptions'].remove(symbol)
                logger.info(f"User {user_id} unsubscribed from {symbol}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error unsubscribing from symbol {symbol}: {str(e)}")
            return False

    def is_indian_market_open(self):
        """Check if Indian market is currently open"""
        try:
            # Get current time in IST
            import pytz
            now = datetime.now(pytz.timezone('Asia/Kolkata'))
            
            # Indian markets are open Monday-Friday, 9:15 AM to 3:30 PM IST
            if now.weekday() >= 5:  # Saturday or Sunday
                return False
                
            market_open = datetime.time(9, 15, 0)
            market_close = datetime.time(15, 30, 0)
            current_time = now.time()
            
            return market_open <= current_time <= market_close
        except Exception as e:
            logger.error(f"Error checking market hours: {str(e)}")
            return False  # Default to closed on error to avoid off-hours trading
            
    async def get_latest_price_data(self, symbol: str) -> Dict:
        """Get latest price data for a symbol with improved OTC handling"""
        try:
            now = datetime.now()
            
            # Check rate limiting
            if symbol in self.last_request_time:
                time_since_last = (now - self.last_request_time[symbol]).total_seconds()
                if time_since_last < self.min_request_interval:
                    return None

            # Update last request time
            self.last_request_time[symbol] = now
            
            price_data = {
                'symbol': symbol,
                'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
                'source': None
            }

            # Handle OTC symbols
            if symbol.endswith('_OTC'):
                if not self.otc_handler:
                    logger.error("OTC handler not initialized")
                    return None
                    
                price, source = self.otc_handler.get_realtime_price(symbol, return_source=True)
                if price is not None:
                    price_data.update({
                        'rate': float(price),
                        'source': source,
                        'type': 'otc_update'
                    })
                    return price_data
                return None

            # Handle regular forex symbols
            elif symbol in self.forex_symbols:
                yf_symbol = self.forex_symbols[symbol]
                try:
                    ticker = yf.Ticker(yf_symbol)
                    data = ticker.history(period='1d', interval='1m')
                    if not data.empty:
                        last_price = float(data['Close'].iloc[-1])
                        price_data.update({
                            'rate': last_price,
                            'source': 'Yahoo Finance',
                            'type': 'forex_update'
                        })
                        return price_data
                except Exception as e:
                    logger.error(f"Error fetching forex data for {symbol}: {str(e)}")
                    return None

            # Handle Indian market symbols
            elif symbol in self.indian_symbols:
                yf_symbol = self.indian_symbols[symbol]
                try:
                    ticker = yf.Ticker(yf_symbol)
                    data = ticker.history(period='1d', interval='1m')
                    if not data.empty:
                        last_price = float(data['Close'].iloc[-1])
                        market_open = self.is_indian_market_open()
                        price_data.update({
                            'rate': last_price,
                            'source': 'Yahoo Finance',
                            'type': 'indian_update',
                            'market_open': market_open,
                            'pair': symbol  # Add the pair field to match expected format
                        })
                        return price_data
                except Exception as e:
                    logger.error(f"Error fetching Indian market data for {symbol}: {str(e)}")
                    return None

            logger.warning(f"Unsupported symbol type: {symbol}")
            return None

        except Exception as e:
            logger.error(f"Error getting latest price data for {symbol}: {str(e)}")
            return None

    def calculate_price_change(self, data):
        """Calculate price change percentage"""
        try:
            if len(data) < 2:
                return 0.0
            return ((data['Close'].iloc[-1] - data['Close'].iloc[0]) / data['Close'].iloc[0]) * 100
        except Exception as e:
            logger.error(f"Error calculating price change: {str(e)}")
            return 0.0

    def calculate_indicators(self, data):
        """Calculate technical indicators"""
        try:
            # RSI
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # MACD
            exp1 = data['Close'].ewm(span=12, adjust=False).mean()
            exp2 = data['Close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()

            return {
                'rsi': rsi.iloc[-1],
                'macd': macd.iloc[-1],
                'macd_signal': signal.iloc[-1]
            }
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return {
                'rsi': 50.0,
                'macd': 0.0,
                'macd_signal': 0.0
            }

    async def broadcast_updates(self):
        """Broadcast price updates to all connected clients using socketio.emit"""
        while True:
            try:
                if not self.connected_users:
                    await asyncio.sleep(0.5)
                    continue

                for symbol in self.subscribed_symbols:
                    try:
                        await asyncio.sleep(0.2)

                        price_data = await self.get_latest_price_data(symbol)
                        if price_data:
                            message = {
                                'type': 'price_update',
                                'data': price_data,
                                'timestamp': datetime.now().isoformat(),
                                'status': price_data.get('status', 'success')
                            }
                            if 'pair' not in price_data and symbol:
                                message['data']['pair'] = symbol
                            if price_data.get('type') == 'indian_update' and 'market_open' in price_data:
                                message['data']['market_open'] = price_data['market_open']
                            self.socketio.emit('price_update', message)
                        else:
                            logger.warning(f"No price data available for {symbol}")
                    except Exception as e:
                        logger.error(f"Error processing updates for {symbol}: {str(e)}")
                        continue

                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error in broadcast loop: {str(e)}")
                await asyncio.sleep(0.5)

    def update_price(self, symbol: str, price_data: Dict):
        """Update price data and broadcast to subscribed clients"""
        try:
            # Update cache
            self.price_cache[symbol] = {
                'symbol': symbol,
                'price': price_data.get('price'),
                'change': price_data.get('change'),
                'volume': price_data.get('volume'),
                'timestamp': datetime.now().isoformat()
            }
            
            # Broadcast to all subscribed clients
            self.socketio.emit('price_update', self.price_cache[symbol])
            
        except Exception as e:
            logger.error(f'Error updating price: {str(e)}')
            
    def broadcast_trade(self, trade_data: Dict):
        """Broadcast trade information to all clients"""
        try:
            self.socketio.emit('trade_update', trade_data)
        except Exception as e:
            logger.error(f'Error broadcasting trade: {str(e)}')
            
    def broadcast_signal(self, signal_data: Dict):
        """Broadcast trading signal to all clients"""
        try:
            self.socketio.emit('signal_update', signal_data)
        except Exception as e:
            logger.error(f'Error broadcasting signal: {str(e)}')
            
    def broadcast_alert(self, alert_data: Dict):
        """Broadcast alert to all clients"""
        try:
            self.socketio.emit('alert', alert_data)
        except Exception as e:
            logger.error(f'Error broadcasting alert: {str(e)}')
            
    def get_cached_price(self, symbol: str) -> Optional[Dict]:
        """Get cached price data for a symbol"""
        return self.price_cache.get(symbol)
        
    def clear_cache(self, symbol: Optional[str] = None):
        """Clear price cache for a symbol or all symbols"""
        try:
            if symbol:
                self.price_cache.pop(symbol, None)
            else:
                self.price_cache.clear()
        except Exception as e:
            logger.error(f'Error clearing cache: {str(e)}')

def black_scholes_call_put(S, K, T, r, sigma, option_type):
    """Calculate Black-Scholes option price"""
    try:
        if not all(isinstance(x, (int, float)) for x in [S, K, T, r, sigma]):
            return None
            
        if any(math.isnan(x) for x in [S, K, T, r, sigma]):
            return None
            
        if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
            return None
            
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if option_type.lower() == "call":
            price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        elif option_type.lower() == "put":
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        else:
            return None
            
        return float(price) if not math.isnan(price) else None
        
    except Exception as e:
        logger.error(f"Error in Black-Scholes calculation: {str(e)}")
        return None