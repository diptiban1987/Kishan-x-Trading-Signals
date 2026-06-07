#!/usr/bin/env python3
"""
Enhanced Indian Trading System with Auto-Trading Capabilities
Focuses on NIFTY, BANKNIFTY, and major Indian stocks for maximum profitability
"""

import pandas as pd
import numpy as np
import requests
import json
import logging
import os
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import sqlite3
import time
import threading
from dataclasses import dataclass
from angel_one_api import AngelOneAPI, AngelOneDataProvider
from ai_models.signal_predictor import AISignalPredictor
from dhan_api import dhan_client

logger = logging.getLogger(__name__)

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

@dataclass
class IndianTradeSignal:
    """Indian market trade signal with enhanced analysis"""
    symbol: str
    signal_type: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float  # 0.0 to 1.0
    entry_price: float
    target_price: float
    stop_loss: float
    strategy: str
    timeframe: str
    risk_reward_ratio: float
    market_sentiment: str
    volume_analysis: str
    volatility: float
    timestamp: datetime
    expiry_date: Optional[str] = None
    option_type: Optional[str] = None  # 'CE', 'PE' for options

# Symbols that MUST NOT be traded (indices — cannot be traded in cash market)
# NIFTY50 and BANKNIFTY are allowed — traded via NFO futures with ₹5L+ capital
BLOCKED_SYMBOLS = {'SENSEX', 'FINNIFTY', 'MIDCPNIFTY',
                   'NIFTYREALTY', 'NIFTYPVTBANK', 'NIFTYPSUBANK', 'NIFTYFIN', 'NIFTYMEDIA'}

# ──────────────────────────────────────────────────────────────────────────────
# BACKTEST-DRIVEN CONFIGURATION (2026-06-07)
# ──────────────────────────────────────────────────────────────────────────────
# AI predictor: PF=0.75, WinRate=32.7%, Sharpe=-0.75  → LOSING MONEY
# Technical-only (all 7 symbols): PF=1.33, WinRate=51.7%, Sharpe=+0.31
# Technical-only (SBIN+RELIANCE+TCS): PF=2.60, WinRate=62.8%, Sharpe=+1.15
#
# Decision: Disable AI signals, use technical-only, focus on proven symbols.
# Set USE_AI_SIGNALS=True to re-enable AI (not recommended until model improves).
# ──────────────────────────────────────────────────────────────────────────────
USE_AI_SIGNALS = False   # AI predictor disabled — destroys edge (PF 0.75)

# Only these symbols have backtested edge with technical strategies.
# Other symbols still appear in the UI for charting but won't generate trade signals.
PROVEN_SYMBOLS = {'SBIN', 'RELIANCE', 'TCS'}

# Set to True to allow signals on ALL symbols (not just proven ones).
# Not recommended — HDFCBANK/INFY/NIFTY50 drag PF down from 2.60 to 1.33.
ALLOW_ALL_SYMBOLS = False

class IndianTradingSystem:
    """Advanced Indian Trading System with Auto-Trading"""
    
    def __init__(self, db_path: str = None, angel_one_client=None):
        self.db_path = db_path if db_path is not None else _get_db_path()
        self.indian_symbols = {
            # Major Stocks
            'RELIANCE': 'RELIANCE.NS',
            'TCS': 'TCS.NS',
            'HDFCBANK': 'HDFCBANK.NS',
            'INFY': 'INFY.NS',
            'ICICIBANK': 'ICICIBANK.NS',
            'HINDUNILVR': 'HINDUNILVR.NS',
            'SBIN': 'SBIN.NS',
            'BHARTIARTL': 'BHARTIARTL.NS',
            'KOTAKBANK': 'KOTAKBANK.NS',
            'BAJFINANCE': 'BAJFINANCE.NS',
            # Indices — for chart display only (trading blocked by BLOCKED_SYMBOLS)
            'NIFTY50': '^NSEI',
            'BANKNIFTY': '^NSEBANK',
            'SENSEX': '^BSESN',
            'FINNIFTY': 'NIFTY_FIN_SERVICE.NS',
            'MIDCPNIFTY': '^NSEMDCP50',
            'NIFTYREALTY': '^CNXREALTY',
            'NIFTYPVTBANK': '^NIFTYBANK',
            'NIFTYPSUBANK': '^CNXPSUBANK',
            'NIFTYFIN': '^CNXFIN',
            'NIFTYMEDIA': '^CNXMEDIA'
        }
        
        # Initialize Angel One integration
        if angel_one_client:
            self.angel_one = angel_one_client
            self.data_provider = AngelOneDataProvider(angel_one_client)
        else:
            # Disable mock; require Angel One configuration first
            self.angel_one = None
            self.data_provider = None
            logger.error("Angel One client not configured. Please set credentials and restart.")
        
        # Trading strategies for Indian markets
        self.strategies = {
            'nifty_momentum': self.nifty_momentum_strategy,
            'banknifty_volatility': self.banknifty_volatility_strategy,
            'stock_breakout': self.stock_breakout_strategy
        }
        
        # Market timing for Indian markets (IST)
        self.market_hours = {
            'pre_market': '09:00',
            'market_open': '09:15',
            'market_close': '15:30',
            'post_market': '15:45'
        }
        
        self.active_trades = {}
        self.trade_history = []
        self.performance_metrics = {}
        self._live_mode = True  # Set externally by set_live_mode()
        self.today_file = None
        self._init_activity_log()
        
        # Dynamic price validation: instead of hardcoded ranges that go stale,
        # use percentage-based sanity checks against the last known price.
        # Cache of last-known-good prices per symbol (updated on each valid fetch)
        self._last_known_prices = {}
        # Maximum allowed single-day deviation from last known price (50%)
        self._max_price_deviation_pct = 0.50
        # Absolute floor/ceiling for any Indian instrument
        self._absolute_price_floor = 0.50   # No legit stock below ₹0.50
        self._absolute_price_ceiling = 500000  # No legit stock above ₹5,00,000

        self._api_error_cooldowns = {}
        self._api_cooldown_seconds = 30

    def validate_price(self, symbol: str, price: float) -> bool:
        """Validate price using dynamic percentage-based sanity checks.
        
        Instead of hardcoded ranges that go stale over time, this checks:
        1. Price is within absolute floor/ceiling bounds
        2. Price is within ±50% of the last known good price for this symbol
        3. If no prior price is known, accepts any price within absolute bounds
        """
        if price <= 0:
            return False
        
        # Absolute bounds check
        if price < self._absolute_price_floor or price > self._absolute_price_ceiling:
            logger.warning(f"⚠️ PRICE ANOMALY: {symbol} price {price:.2f} outside absolute bounds "
                          f"[{self._absolute_price_floor}-{self._absolute_price_ceiling}]")
            return False
        
        clean_symbol = symbol.replace('.NS', '').replace('.BO', '').upper()
        
        # Check against last known good price (dynamic, not hardcoded)
        last_price = self._last_known_prices.get(clean_symbol)
        if last_price is not None and last_price > 0:
            deviation = abs(price - last_price) / last_price
            if deviation > self._max_price_deviation_pct:
                logger.warning(f"⚠️ PRICE ANOMALY: {symbol} price {price:.2f} deviates "
                              f"{deviation:.1%} from last known {last_price:.2f} "
                              f"(max allowed: {self._max_price_deviation_pct:.0%})")
                return False
        
        # Price is valid — update last known price
        self._last_known_prices[clean_symbol] = price
        return True

    def set_live_mode(self, live: bool):
        """Set whether this system should place real broker orders"""
        self._live_mode = live
        logger.info(f"IndianTradingSystem live mode: {live}")

    def is_live(self) -> bool:
        """Check if system is in live (real money) mode"""
        return self._live_mode

    def _init_activity_log(self):
        try:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            today = datetime.now().strftime('%Y-%m-%d')
            self.activity_log_path = os.path.join(log_dir, f'trading_session_{today}.md')
            with open(self.activity_log_path, 'a', encoding='utf-8') as f:
                f.write(f"# Trading Session Activity Log — {today}\n\n")
                f.write(f"**System:** Indian Auto Trader (DEMO Mode)\n")
                f.write(f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"**Mode:** DEMO (Mock Funds ₹1,00,000)\n\n")
                f.write("| Time | Symbol | Action | Entry | Exit | Qty | P&L | Balance | Strategy |\n")
                f.write("|------|--------|--------|-------|------|-----|-----|---------|----------|\n")
        except Exception as e:
            logger.error(f"Failed to init activity log: {e}")

    def log_activity(self, action: str, symbol: str, entry: float, exit: float, qty: int, pnl: float, balance: float, strat: str = ''):
        try:
            ts = datetime.now().strftime('%H:%M:%S')
            line = f"| {ts} | {symbol} | {action} | {entry:.2f} | {exit:.2f} | {qty} | {pnl:+.2f} | {balance:.2f} | {strat} |\n"
            with open(self.activity_log_path, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
        
    @staticmethod
    def get_nse_holidays(year: int) -> set:
        """Get NSE trading holidays for a given year using holidays package + supplement."""
        import holidays as py_holidays
        h = py_holidays.India(subdiv='MH', years=year)
        nse_holidays = set(h)

        # Supplementary NSE-specific holidays the package may miss
        # These are fixed-date or known NSE holidays
        supplementary = {
            # Format: (month, day) — checked for any year
            (1, 26),    # Republic Day
            (8, 15),    # Independence Day
            (10, 2),    # Gandhi Jayanti
            (12, 25),   # Christmas
        }
        import calendar
        for month, day in supplementary:
            try:
                d = datetime(year, month, day).date()
                nse_holidays.add(d)
            except ValueError:
                pass

        # Add Sundays (NSE never trades on Sunday)
        for month in range(1, 13):
            for day in range(1, calendar.monthrange(year, month)[1] + 1):
                d = datetime(year, month, day).date()
                if d.weekday() == 6:
                    nse_holidays.add(d)

        return nse_holidays

    def is_market_open(self) -> bool:
        """Check if Indian market is currently open (IST), including holiday check."""
        try:
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist)

            # Weekend check
            if now.weekday() >= 5:
                return False

            # Holiday check
            holidays = self.get_nse_holidays(now.year)
            today = now.date()
            if today in holidays:
                logger.info(f"Market closed — {today} is an NSE holiday")
                return False

            # Time check: 9:15 AM to 3:30 PM IST
            market_open = datetime.strptime('09:15', '%H:%M').time()
            market_close = datetime.strptime('15:30', '%H:%M').time()
            current_time = now.time()

            return market_open <= current_time <= market_close

        except Exception as e:
            logger.error(f"Error checking market hours: {str(e)}")
            return False

    def is_trading_day(self, dt: Optional[datetime] = None) -> bool:
        """Check if a given day is a valid NSE trading day (ignoring time)."""
        try:
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            if dt is None:
                dt = datetime.now(ist)
            elif dt.tzinfo is None:
                dt = ist.localize(dt)

            if dt.weekday() >= 5:
                return False
            holidays = self.get_nse_holidays(dt.year)
            return dt.date() not in holidays
        except Exception:
            return False
    
    def _is_api_on_cooldown(self, provider: str) -> bool:
        last_err = self._api_error_cooldowns.get(provider, 0)
        return time.time() - last_err < self._api_cooldown_seconds

    def get_indian_market_data(self, symbol: str, period: str = '1d', interval: str = '1d') -> Optional[pd.DataFrame]:
        """Get Indian market data using Dhan API, with Angel One and yfinance as fallbacks."""
        try:
            if symbol not in self.indian_symbols:
                logger.error(f"Symbol {symbol} not found in Indian symbols")
                return None
            
            # 1. Dhan API SKIPPED — permanently disabled (DH-902: not subscribed to Data APIs)
            # Saves ~20s per cycle wasted on failed API calls per symbol

            # 2. Try Angel One API (Fallback 1)
            if self.data_provider and not self._is_api_on_cooldown('angel_one'):
                try:
                    logger.info(f"Attempting fallback data fetch from Angel One API for {symbol}")
                    data = self.data_provider.get_historical_data(symbol, interval, period)
                    if not data.empty:
                        # Divisor correction: Angel One sometimes returns divided prices (e.g. 4.3 instead of 745)
                        close_col = 'Close' if 'Close' in data.columns else 'close' if 'close' in data.columns else None
                        if close_col:
                            last_close = data[close_col].iloc[-1]
                            clean_sym = symbol.upper().replace('.NS', '').replace('.BO', '')
                            # Use last known good price to detect abnormally low values
                            known_price = self._last_known_prices.get(clean_sym)
                            if known_price and known_price > 0:
                                if last_close < known_price * 0.1:
                                    price_cols = [c for c in ['Open', 'High', 'Low', 'Close', 'open', 'high', 'low', 'close'] if c in data.columns]
                                    # Try candidate multipliers to find one that brings price close to known price
                                    magnitude = None
                                    for mul in [10, 20, 50, 100, 200, 500, 1000]:
                                        if known_price * 0.5 <= last_close * mul <= known_price * 1.5:
                                            magnitude = mul
                                            break
                                    if magnitude is None:
                                        magnitude = max(1, int(known_price / last_close))
                                    for col in price_cols:
                                        data[col] = data[col] * magnitude
                                    logger.warning(f"🔄 Divisor correction: {symbol} prices ×{magnitude} (was {last_close:.2f}, now {data[close_col].iloc[-1]:.2f})")
                        return data
                    logger.warning(f"Angel One returned no data for {symbol}, falling back to yfinance...")
                except Exception as e:
                    logger.warning(f"Angel One API failed for {symbol}: {str(e)}, falling back to yfinance...")
                    self._api_error_cooldowns['angel_one'] = time.time()
            
            # 3. Fallback to yfinance if both brokers fail (e.g. internet loss / timeouts)
            import yfinance as yf
            
            # Map symbol to Yahoo Finance ticker (usually .NS for NSE)
            yf_symbol = symbol
            if symbol in ['NIFTY', 'NIFTY50']:
                yf_symbol = '^NSEI'
            elif symbol == 'BANKNIFTY':
                yf_symbol = '^NSEBANK'
            elif symbol == 'FINNIFTY':
                yf_symbol = 'NIFTY_FIN_SERVICE.NS'
            elif symbol == 'MIDCPNIFTY':
                yf_symbol = '^NSEMDCP50'
            elif symbol == 'SENSEX':
                yf_symbol = '^BSESN'
            elif not symbol.startswith('^'):
                yf_symbol = f"{symbol}.NS"
                
            logger.info(f"Using yfinance fallback for {symbol} as {yf_symbol}")
            
            # Convert intervals for yfinance
            yf_interval = interval
            if interval == 'ONE_DAY' or interval == '1d':
                yf_interval = '1d'
            elif interval == 'ONE_MINUTE':
                yf_interval = '1m'
            elif interval == 'FIVE_MINUTE':
                yf_interval = '5m'
                
            # Convert periods for yfinance
            yf_period = period
            if period in ('1d', 'ONE_DAY'):
                yf_period = '1d'
            elif period in ('5d', 'FIVE_DAY'):
                yf_period = '5d'
            elif period in ('10d', 'TEN_DAY'):
                yf_period = '10d'
            elif period in ('1mo', 'ONE_MONTH'):
                yf_period = '1mo'
                
            try:
                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(period=yf_period, interval=yf_interval)
                
                if not df.empty:
                    logger.info(f"Successfully retrieved {len(df)} rows from yfinance for {symbol}")
                    return df
            except Exception as yf_e:
                logger.error(f"yfinance download failed for {symbol} (possibly offline): {yf_e}")
                
            logger.error(f"No fallback data available for {symbol}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {str(e)}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
    
    # Mock generation disabled
    
    def analyze_indian_market(self, symbol: str) -> IndianTradeSignal:
        """Comprehensive Indian market analysis.
        
        Signal priority (based on backtest 2026-06-07):
          1. Technical strategies are PRIMARY (PF=2.60 on proven symbols)
          2. AI predictor is DISABLED by default (PF=0.75 — loses money)
          3. Only PROVEN_SYMBOLS get trade signals unless ALLOW_ALL_SYMBOLS=True
        """
        try:
            # Block index symbols that cannot be traded in cash market
            clean_sym = symbol.replace('.NS', '').replace('.BO', '').upper()
            if clean_sym in BLOCKED_SYMBOLS:
                return self._create_neutral_signal(symbol)

            # Only generate trading signals for proven symbols
            if not ALLOW_ALL_SYMBOLS and clean_sym not in PROVEN_SYMBOLS:
                logger.debug(f"Skipping signal for {symbol}: not in PROVEN_SYMBOLS (charting only)")
                return self._create_neutral_signal(symbol)

            # Get INTRADAY data (5-minute candles) for signal generation
            data = self.get_indian_market_data(symbol, period='5d', interval='5m')
            if data is None or data.empty or len(data) < 20:
                # Fallback to daily if 5m unavailable
                data = self.get_indian_market_data(symbol, period='10d', interval='1d')
            if data is None or data.empty:
                return self._create_neutral_signal(symbol)
            
            # Normalize column names to capitalized format
            col_map = {c: c.capitalize() for c in data.columns if c.islower()}
            if col_map:
                data = data.rename(columns=col_map)
            
            # AI Predictor — DISABLED by default (backtest: PF=0.75, loses money).
            # Set USE_AI_SIGNALS=True at module level to re-enable.
            if USE_AI_SIGNALS:
                try:
                    if not hasattr(self, '_predictor'):
                        self._predictor = AISignalPredictor()
                    predictor = self._predictor
                    ai_signal = predictor.predict_with_data(symbol, data)
                    
                    raw_conf = ai_signal.get('confidence', 0)
                    if ai_signal and ai_signal.get('signal') != 'HOLD' and raw_conf >= 0.55:
                        logger.info(f"Using AI signal for {symbol}: {ai_signal['signal']} with {raw_conf*100:.1f}% raw confidence")
                        
                        direction = 'BUY' if ai_signal['signal'] in ('BUY', 'CALL') else 'SELL' if ai_signal['signal'] in ('SELL', 'PUT') else 'HOLD'
                        
                        if raw_conf < 0.65:
                            logger.info(f"Skipping AI signal for {symbol}: raw confidence {raw_conf:.3f} below 0.65 threshold")
                            return None
                        confidence = min(max(0.60 + (raw_conf - 0.55) * 0.78, 0.50), 0.95)
                        current_price = data['Close'].iloc[-1]
                        
                        atr = self._calculate_atr(data, 14)
                        atr_pct = atr / current_price if current_price > 0 else 0.02
                        target_mult = max(atr_pct * 2, 0.008)
                        stop_mult = max(atr_pct * 1.5, 0.005)
                        if direction == 'BUY':
                            target = current_price * (1 + target_mult)
                            stop_loss = current_price * (1 - stop_mult)
                        else:
                            target = current_price * (1 - target_mult)
                            stop_loss = current_price * (1 + stop_mult)
                            
                        signal = IndianTradeSignal(
                            symbol=symbol,
                            signal_type=direction,
                            confidence=confidence,
                            entry_price=current_price,
                            target_price=target,
                            stop_loss=stop_loss,
                            strategy='AI XGBoost Predictor',
                            timeframe='1D',
                            risk_reward_ratio=0.0,
                            market_sentiment=self._analyze_market_sentiment(symbol, data),
                            volume_analysis=self._analyze_volume(data),
                            volatility=self._calculate_volatility(data),
                            timestamp=datetime.now()
                        )
                        
                        risk_reward = self._calculate_risk_reward(signal, data)
                        signal.risk_reward_ratio = risk_reward
                        return signal
                except Exception as ai_e:
                    logger.error(f"AI Predictor failed for {symbol}, falling back to technical strategies: {ai_e}")
            else:
                logger.debug(f"AI signals disabled for {symbol} — using technical strategies only (USE_AI_SIGNALS=False)")
            
            # Fallback to calculate technical indicators and static strategies
            indicators = self._calculate_indian_indicators(data)
            
            # Apply trading strategies
            signal = self._apply_indian_strategies(symbol, data, indicators)
            
            # Blend ATR levels with strategy targets: use the better of the two
            if signal.signal_type != 'HOLD' and signal.confidence > 0:
                current_price = data['Close'].iloc[-1]
                atr = indicators.get('atr', self._calculate_atr(data, 14))
                atr_pct = atr / current_price if current_price > 0 else 0.02
                target_mult = max(atr_pct * 2, 0.008)
                stop_mult = max(atr_pct * 1.5, 0.005)
                if signal.signal_type == 'BUY':
                    signal.target_price = max(signal.target_price, current_price * (1 + target_mult))
                    signal.stop_loss = max(signal.stop_loss, current_price * (1 - stop_mult))
                else:
                    signal.target_price = min(signal.target_price, current_price * (1 - target_mult))
                    signal.stop_loss = min(signal.stop_loss, current_price * (1 + stop_mult))
            
            # Calculate risk-reward
            risk_reward = self._calculate_risk_reward(signal, data)
            signal.risk_reward_ratio = risk_reward
            
            # Add market sentiment
            signal.market_sentiment = self._analyze_market_sentiment(symbol, data)
            
            # Add volume analysis
            signal.volume_analysis = self._analyze_volume(data)
            
            # Add volatility
            signal.volatility = self._calculate_volatility(data)
            
            return signal
            
        except Exception as e:
            logger.error(f"Error analyzing Indian market for {symbol}: {str(e)}")
            return self._create_neutral_signal(symbol)
    
    def _calculate_indian_indicators(self, data: pd.DataFrame) -> Dict:
        """Calculate technical indicators optimized for Indian markets"""
        try:
            close_prices = data['Close']
            
            # RSI with Indian market optimization
            rsi = self._calculate_rsi(close_prices, period=14)
            
            # MACD optimized for Indian markets
            ema12 = close_prices.ewm(span=12).mean()
            ema26 = close_prices.ewm(span=26).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9).mean()
            
            # Bollinger Bands with Indian volatility
            sma20 = close_prices.rolling(window=20).mean()
            std20 = close_prices.rolling(window=20).std()
            bb_upper = sma20 + (std20 * 2.2)  # Wider bands for Indian markets
            bb_lower = sma20 - (std20 * 2.2)
            
            # Moving averages
            sma50 = close_prices.rolling(window=50).mean()
            sma200 = close_prices.rolling(window=200).mean()
            
            # Volume indicators
            volume_sma = data['Volume'].rolling(window=20).mean()
            volume_ratio = data['Volume'] / volume_sma
            
            # Support and resistance levels
            support_levels = self._find_support_levels(close_prices)
            resistance_levels = self._find_resistance_levels(close_prices)
            
            # Average True Range for adaptive stop/target
            atr = self._calculate_atr(data, 14)
            
            bb_middle = sma20.iloc[-1] if not sma20.empty else close_prices.iloc[-1]
            bb_width = ((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / sma20.iloc[-1]) if not sma20.empty else 0.04

            # Stochastic and Williams %R
            stoch_k = 50
            williams_r = -50
            if len(close_prices) > 14:
                lowest_14 = close_prices.rolling(window=14).min()
                highest_14 = close_prices.rolling(window=14).max()
                stoch_k = ((close_prices.iloc[-1] - lowest_14.iloc[-1]) / (highest_14.iloc[-1] - lowest_14.iloc[-1] + 1e-10)) * 100
                williams_r = ((highest_14.iloc[-1] - close_prices.iloc[-1]) / (highest_14.iloc[-1] - lowest_14.iloc[-1] + 1e-10)) * -100

            return {
                'rsi': rsi.iloc[-1] if not rsi.empty else 50,
                'macd': macd.iloc[-1] if not macd.empty else 0,
                'macd_signal': signal.iloc[-1] if not signal.empty else 0,
                'bb_upper': bb_upper.iloc[-1] if not bb_upper.empty else close_prices.iloc[-1],
                'bb_lower': bb_lower.iloc[-1] if not bb_lower.empty else close_prices.iloc[-1],
                'sma50': sma50.iloc[-1] if not sma50.empty else close_prices.iloc[-1],
                'sma200': sma200.iloc[-1] if not sma200.empty else close_prices.iloc[-1],
                'volume_ratio': volume_ratio.iloc[-1] if not volume_ratio.empty else 1.0,
                'support_levels': support_levels,
                'resistance_levels': resistance_levels,
                'atr': atr,
                # Aliases for strategy compatibility
                'sma_20': sma20.iloc[-1] if not sma20.empty else close_prices.iloc[-1],
                'sma_50': sma50.iloc[-1] if not sma50.empty else close_prices.iloc[-1],
                'sma_200': sma200.iloc[-1] if not sma200.empty else close_prices.iloc[-1],
                'ema_12': ema12.iloc[-1] if not ema12.empty else close_prices.iloc[-1],
                'ema_26': ema26.iloc[-1] if not ema26.empty else close_prices.iloc[-1],
                'bb_middle': bb_middle,
                'bb_width': bb_width,
                'stochastic_k': stoch_k,
                'williams_r': williams_r,
            }
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return {}
    
    def _apply_indian_strategies(self, symbol: str, data: pd.DataFrame, indicators: Dict) -> IndianTradeSignal:
        """Apply enhanced Indian market specific trading strategies"""
        try:
            current_price = data['Close'].iloc[-1]
            
            # Single primary strategy only (no Multi-Strategy noise)
            primary_signal = None
            
            # Strategy 1: NIFTY Momentum Strategy (single, primary)
            if 'NIFTY' in symbol:
                primary_signal = self.nifty_momentum_strategy(data, indicators)
                
            # Strategy 2: BANKNIFTY Volatility Strategy (single, primary)
            elif 'BANKNIFTY' in symbol:
                primary_signal = self.banknifty_volatility_strategy(data, indicators)
                
            # Strategy 3: Stock specific - use only the best single strategy
            else:
                if symbol in ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY']:
                    primary_signal = self.large_cap_strategy(data, indicators)
                else:
                    primary_signal = self.stock_breakout_strategy(data, indicators)
            
            if primary_signal is None:
                return self._create_neutral_signal(symbol)
            
            # Create trade signal directly from single strategy
            return IndianTradeSignal(
                symbol=symbol,
                signal_type=primary_signal['type'],
                confidence=primary_signal['confidence'],
                entry_price=current_price,
                target_price=primary_signal['target'],
                stop_loss=primary_signal['stop_loss'],
                strategy=primary_signal['strategy_name'],
                timeframe='1D',
                risk_reward_ratio=0.0,
                market_sentiment='',
                volume_analysis='',
                volatility=0.0,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error applying strategies: {str(e)}")
            return self._create_neutral_signal(symbol)
    
    def nifty_momentum_strategy(self, data: pd.DataFrame, indicators: Dict) -> Dict:
        """NIFTY specific momentum strategy — multi-confirmation for higher accuracy"""
        try:
            current_price = data['Close'].iloc[-1]
            rsi = indicators.get('rsi', 50)
            macd = indicators.get('macd', 0)
            macd_signal = indicators.get('macd_signal', 0)
            sma50 = indicators.get('sma50', current_price)
            sma200 = indicators.get('sma200', current_price)
            volume_ratio = indicators.get('volume_ratio', 1.0)
            
            macd_hist = macd - macd_signal
            
            # Multi-confirmation BUY conditions (need 3+ of 5)
            buy_checks = [
                current_price > sma50,             # 1. Price above 50 SMA
                rsi > 40 and rsi < 75,             # 2. RSI not oversold, not overbought
                macd_hist > 0,                      # 3. MACD histogram positive
                current_price > sma200,            # 4. Above 200 SMA (long-term uptrend)
                volume_ratio > 0.8,                # 5. Volume not too low
            ]
            
            sell_checks = [
                current_price < sma50,             # 1. Price below 50 SMA
                rsi < 60 and rsi > 25,             # 2. RSI not oversold, not overbought
                macd_hist < 0,                      # 3. MACD histogram negative
                current_price < sma200,            # 4. Below 200 SMA (long-term downtrend)
                volume_ratio > 0.8,                # 5. Volume not too low
            ]
            
            buy_score = sum(buy_checks)
            sell_score = sum(sell_checks)
            
            # Require at least 3/5 confirmations
            if buy_score >= 3:
                confidence = 0.6 + (buy_score / 5.0) * 0.3
                target = current_price * 1.015  # 1.5% target (more realistic)
                stop_loss = current_price * 0.99  # 1% stop loss
                
                return {
                    'type': 'BUY',
                    'confidence': min(confidence, 0.95),
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'NIFTY Momentum'
                }
            elif sell_score >= 3:
                confidence = 0.6 + (sell_score / 5.0) * 0.3
                target = current_price * 0.985  # 1.5% target
                stop_loss = current_price * 1.01  # 1% stop loss
                
                return {
                    'type': 'SELL',
                    'confidence': min(confidence, 0.95),
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'NIFTY Momentum'
                }
            else:
                return {
                    'type': 'HOLD',
                    'confidence': 0.2,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'NIFTY Momentum'
                }
                
        except Exception as e:
            logger.error(f"Error in NIFTY momentum strategy: {str(e)}")
            return {'type': 'HOLD', 'confidence': 0.0, 'target': 0, 'stop_loss': 0, 'strategy_name': 'Error'}
    
    def banknifty_volatility_strategy(self, data: pd.DataFrame, indicators: Dict) -> Dict:
        """BANKNIFTY specific volatility strategy"""
        try:
            current_price = data['Close'].iloc[-1]
            bb_upper = indicators.get('bb_upper', current_price)
            bb_lower = indicators.get('bb_lower', current_price)
            rsi = indicators.get('rsi', 50)
            volume_ratio = indicators.get('volume_ratio', 1.0)
            
            # BANKNIFTY volatility conditions
            volatility_buy = (
                current_price <= bb_lower and  # Price at lower Bollinger Band
                rsi < 35 and  # Oversold
                volume_ratio > 1.2  # High volume
            )
            
            volatility_sell = (
                current_price >= bb_upper and  # Price at upper Bollinger Band
                rsi > 75 and  # Overbought
                volume_ratio > 1.2  # High volume
            )
            
            if volatility_buy:
                target = current_price * 1.015  # 1.5% target (shorter for volatility)
                stop_loss = current_price * 0.985  # 1.5% stop loss
                confidence = min((35 - rsi) / 35, 1.0)
                
                return {
                    'type': 'BUY',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'BANKNIFTY Volatility'
                }
            elif volatility_sell:
                target = current_price * 0.985  # 1.5% target
                stop_loss = current_price * 1.015  # 1.5% stop loss
                confidence = min((rsi - 75) / 25, 1.0)
                
                return {
                    'type': 'SELL',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'BANKNIFTY Volatility'
                }
            else:
                return {
                    'type': 'HOLD',
                    'confidence': 0.5,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'BANKNIFTY Volatility'
                }
                
        except Exception as e:
            logger.error(f"Error in BANKNIFTY volatility strategy: {str(e)}")
            return {'type': 'HOLD', 'confidence': 0.0, 'target': 0, 'stop_loss': 0, 'strategy_name': 'Error'}
    
    def stock_breakout_strategy(self, data: pd.DataFrame, indicators: Dict) -> Dict:
        """Stock specific breakout strategy"""
        try:
            current_price = data['Close'].iloc[-1]
            resistance_levels = indicators.get('resistance_levels', [])
            support_levels = indicators.get('support_levels', [])
            volume_ratio = indicators.get('volume_ratio', 1.0)
            rsi = indicators.get('rsi', 50)
            
            # Check for breakout above resistance
            breakout_buy = False
            breakout_target = current_price * 1.03
            
            for resistance in resistance_levels:
                if current_price > resistance and volume_ratio > 1.5:
                    breakout_buy = True
                    breakout_target = max(resistance * 1.02, current_price * 1.015)
                    break
            
            # Check for breakdown below support
            breakdown_sell = False
            breakdown_target = current_price * 0.97
            
            for support in support_levels:
                if current_price < support and volume_ratio > 1.5:
                    breakdown_sell = True
                    breakdown_target = min(support * 0.98, current_price * 0.985)
                    break
            
            if breakout_buy:
                return {
                    'type': 'BUY',
                    'confidence': 0.8,
                    'target': breakout_target,
                    'stop_loss': current_price * 0.98,
                    'strategy_name': 'Stock Breakout'
                }
            elif breakdown_sell:
                return {
                    'type': 'SELL',
                    'confidence': 0.8,
                    'target': breakdown_target,
                    'stop_loss': current_price * 1.02,
                    'strategy_name': 'Stock Breakdown'
                }
            else:
                return {
                    'type': 'HOLD',
                    'confidence': 0.5,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'Stock Breakout'
                }
                
        except Exception as e:
            logger.error(f"Error in stock breakout strategy: {str(e)}")
            return {'type': 'HOLD', 'confidence': 0.0, 'target': 0, 'stop_loss': 0, 'strategy_name': 'Error'}
    
    def _create_neutral_signal(self, symbol: str) -> IndianTradeSignal:
        """Create a neutral signal when analysis fails"""
        return IndianTradeSignal(
            symbol=symbol,
            signal_type='HOLD',
            confidence=0.0,
            entry_price=0.0,
            target_price=0.0,
            stop_loss=0.0,
            strategy='Neutral',
            timeframe='1D',
            risk_reward_ratio=0.0,
            market_sentiment='Neutral',
            volume_analysis='Unknown',
            volatility=0.0,
            timestamp=datetime.now()
        )
    
    def _calculate_risk_reward(self, signal: IndianTradeSignal, data: pd.DataFrame) -> float:
        """Calculate risk-reward ratio"""
        try:
            if signal.signal_type == 'HOLD':
                return 0.0
                
            current_price = data['Close'].iloc[-1]
            
            if signal.signal_type == 'BUY':
                reward = signal.target_price - current_price
                risk = current_price - signal.stop_loss
            else:  # SELL
                reward = current_price - signal.target_price
                risk = signal.stop_loss - current_price
                
            if risk > 0:
                return reward / risk
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating risk-reward: {str(e)}")
            return 0.0
    
    def _analyze_market_sentiment(self, symbol: str, data: pd.DataFrame) -> str:
        """Analyze market sentiment for Indian markets"""
        try:
            # Simple sentiment based on price movement
            if len(data) < 5:
                return 'Neutral'
                
            recent_prices = data['Close'].tail(5)
            price_change = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]
            
            if price_change > 0.02:  # 2% gain
                return 'Bullish'
            elif price_change < -0.02:  # 2% loss
                return 'Bearish'
            else:
                return 'Neutral'
                
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {str(e)}")
            return 'Neutral'
    
    def _analyze_volume(self, data: pd.DataFrame) -> str:
        """Analyze volume patterns"""
        try:
            if len(data) < 20:
                return 'Normal'
                
            recent_volume = data['Volume'].tail(5).mean()
            avg_volume = data['Volume'].tail(20).mean()
            
            if recent_volume > avg_volume * 1.5:
                return 'High'
            elif recent_volume < avg_volume * 0.5:
                return 'Low'
            else:
                return 'Normal'
                
        except Exception as e:
            logger.error(f"Error analyzing volume: {str(e)}")
            return 'Normal'
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range for volatility-based stop/target"""
        try:
            high, low, close = data['High'], data['Low'], data['Close']
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs()
            ], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean().iloc[-1]
            return float(atr) if not pd.isna(atr) else float(close.iloc[-1] * 0.02)
        except Exception as e:
            logger.error(f"Error calculating ATR: {str(e)}")
            return float(data['Close'].iloc[-1] * 0.02) if not data.empty else 0.0

    def _calculate_volatility(self, data: pd.DataFrame) -> float:
        """Calculate price volatility"""
        try:
            if len(data) < 20:
                return 0.0
                
            returns = data['Close'].pct_change().dropna()
            return returns.std()
            
        except Exception as e:
            logger.error(f"Error calculating volatility: {str(e)}")
            return 0.0
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, min_periods=period).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, min_periods=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi
        except Exception as e:
            logger.error(f"Error calculating RSI: {str(e)}")
            return pd.Series()
    
    def _find_support_levels(self, prices: pd.Series) -> List[float]:
        """Find support levels using pivot points — only recent 60 candles"""
        try:
            if len(prices) < 20:
                return []
                
            recent_prices = prices.iloc[-60:]
            # Simple support levels using recent lows
            support_levels = []
            for i in range(10, len(recent_prices)):
                if recent_prices.iloc[i] == recent_prices.iloc[i-10:i+1].min():
                    support_levels.append(recent_prices.iloc[i])
                    
            return support_levels[:3]  # Return top 3 support levels
            
        except Exception as e:
            logger.error(f"Error finding support levels: {str(e)}")
            return []
    
    def _find_resistance_levels(self, prices: pd.Series) -> List[float]:
        """Find resistance levels using pivot points — only recent 60 candles"""
        try:
            if len(prices) < 20:
                return []
                
            recent_prices = prices.iloc[-60:]
            # Simple resistance levels using recent highs
            resistance_levels = []
            for i in range(10, len(recent_prices)):
                if recent_prices.iloc[i] == recent_prices.iloc[i-10:i+1].max():
                    resistance_levels.append(recent_prices.iloc[i])
                    
            return resistance_levels[:3]  # Return top 3 resistance levels
            
        except Exception as e:
            logger.error(f"Error finding resistance levels: {str(e)}")
            return []

    def mean_reversion_strategy(self, data: pd.DataFrame, indicators: Dict) -> Dict:
        """Mean reversion strategy for Indian markets"""
        try:
            current_price = data['Close'].iloc[-1]
            rsi = indicators.get('rsi', 50)
            bb_upper = indicators.get('bb_upper', current_price)
            bb_lower = indicators.get('bb_lower', current_price)
            bb_middle = indicators.get('bb_middle', current_price)
            
            # Mean reversion conditions
            oversold = rsi < 30 and current_price <= bb_lower
            overbought = rsi > 70 and current_price >= bb_upper
            
            if oversold:
                target = bb_middle  # Target middle of Bollinger Bands
                stop_loss = current_price * 0.98  # 2% stop loss
                confidence = min((30 - rsi) / 30, 1.0)
                
                return {
                    'type': 'BUY',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'Mean Reversion'
                }
            elif overbought:
                target = bb_middle
                stop_loss = current_price * 1.02
                confidence = min((rsi - 70) / 30, 1.0)
                
                return {
                    'type': 'SELL',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'Mean Reversion'
                }
            else:
                return {
                    'type': 'HOLD',
                    'confidence': 0.3,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'Mean Reversion'
                }
                
        except Exception as e:
            logger.error(f"Error in mean reversion strategy: {str(e)}")
            return {'type': 'HOLD', 'confidence': 0.0, 'target': 0, 'stop_loss': 0, 'strategy_name': 'Error'}

    def trend_following_strategy(self, data: pd.DataFrame, indicators: Dict) -> Dict:
        """Trend following strategy"""
        try:
            current_price = data['Close'].iloc[-1]
            sma_20 = indicators.get('sma_20', current_price)
            sma_50 = indicators.get('sma_50', current_price)
            ema_12 = indicators.get('ema_12', current_price)
            ema_26 = indicators.get('ema_26', current_price)
            macd = indicators.get('macd', 0)
            macd_signal = indicators.get('macd_signal', 0)
            
            # Trend following conditions
            bullish_trend = (
                current_price > sma_20 > sma_50 and  # Price above moving averages
                ema_12 > ema_26 and  # EMA crossover
                macd > macd_signal  # MACD bullish
            )
            
            bearish_trend = (
                current_price < sma_20 < sma_50 and  # Price below moving averages
                ema_12 < ema_26 and  # EMA crossover
                macd < macd_signal  # MACD bearish
            )
            
            if bullish_trend:
                target = current_price * 1.025  # 2.5% target
                stop_loss = sma_20 * 0.995  # Stop below 20 SMA
                confidence = 0.7
                
                return {
                    'type': 'BUY',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'Trend Following'
                }
            elif bearish_trend:
                target = current_price * 0.975  # 2.5% target
                stop_loss = sma_20 * 1.005  # Stop above 20 SMA
                confidence = 0.7
                
                return {
                    'type': 'SELL',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'Trend Following'
                }
            else:
                return {
                    'type': 'HOLD',
                    'confidence': 0.3,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'Trend Following'
                }
                
        except Exception as e:
            logger.error(f"Error in trend following strategy: {str(e)}")
            return {'type': 'HOLD', 'confidence': 0.0, 'target': 0, 'stop_loss': 0, 'strategy_name': 'Error'}

    def enhanced_breakout_strategy(self, data: pd.DataFrame, indicators: Dict) -> Dict:
        """Enhanced breakout strategy with volume confirmation"""
        try:
            current_price = data['Close'].iloc[-1]
            resistance_levels = indicators.get('resistance_levels', [])
            support_levels = indicators.get('support_levels', [])
            volume_ratio = indicators.get('volume_ratio', 1.0)
            atr = indicators.get('atr', current_price * 0.02)
            
            # Check for breakout above resistance with volume
            breakout_buy = False
            breakout_target = current_price * 1.03
            
            for resistance in resistance_levels:
                if current_price > resistance and volume_ratio > 1.5:
                    breakout_buy = True
                    breakout_target = max(resistance * 1.02, current_price * 1.015)
                    break
            
            # Check for breakdown below support with volume
            breakdown_sell = False
            breakdown_target = current_price * 0.97
            
            for support in support_levels:
                if current_price < support and volume_ratio > 1.5:
                    breakdown_sell = True
                    breakdown_target = min(support * 0.98, current_price * 0.985)
                    break
            
            if breakout_buy:
                return {
                    'type': 'BUY',
                    'confidence': min(0.8, 0.5 + volume_ratio * 0.1),
                    'target': breakout_target,
                    'stop_loss': current_price - atr,
                    'strategy_name': 'Enhanced Breakout'
                }
            elif breakdown_sell:
                return {
                    'type': 'SELL',
                    'confidence': min(0.8, 0.5 + volume_ratio * 0.1),
                    'target': breakdown_target,
                    'stop_loss': current_price + atr,
                    'strategy_name': 'Enhanced Breakdown'
                }
            else:
                return {
                    'type': 'HOLD',
                    'confidence': 0.3,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'Enhanced Breakout'
                }
                
        except Exception as e:
            logger.error(f"Error in enhanced breakout strategy: {str(e)}")
            return {'type': 'HOLD', 'confidence': 0.0, 'target': 0, 'stop_loss': 0, 'strategy_name': 'Error'}

    def large_cap_strategy(self, data: pd.DataFrame, indicators: Dict) -> Dict:
        """Strategy optimized for large cap stocks"""
        try:
            current_price = data['Close'].iloc[-1]
            rsi = indicators.get('rsi', 50)
            sma_50 = indicators.get('sma_50', current_price)
            sma_200 = indicators.get('sma_200', current_price)
            volume_ratio = indicators.get('volume_ratio', 1.0)
            macd = indicators.get('macd', 0)
            macd_signal = indicators.get('macd_signal', 0)
            
            # Large cap conditions (more conservative)
            bullish = (
                rsi > 45 and rsi < 65 and  # RSI in neutral zone
                current_price > sma_50 > sma_200 and  # Above key MAs
                macd > macd_signal and  # MACD bullish
                volume_ratio > 1.2  # Above average volume
            )
            
            bearish = (
                rsi < 55 and rsi > 35 and  # RSI in neutral zone
                current_price < sma_50 and  # Below 50 SMA
                macd < macd_signal and  # MACD bearish
                volume_ratio > 1.2  # Above average volume
            )
            
            if bullish:
                target = current_price * 1.02  # Conservative 2% target
                stop_loss = current_price * 0.98  # 2% stop loss
                confidence = 0.6
                
                return {
                    'type': 'BUY',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'Large Cap'
                }
            elif bearish:
                target = current_price * 0.98
                stop_loss = current_price * 1.02
                confidence = 0.6
                
                return {
                    'type': 'SELL',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'Large Cap'
                }
            else:
                return {
                    'type': 'HOLD',
                    'confidence': 0.4,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'Large Cap'
                }
                
        except Exception as e:
            logger.error(f"Error in large cap strategy: {str(e)}")
            return {'type': 'HOLD', 'confidence': 0.0, 'target': 0, 'stop_loss': 0, 'strategy_name': 'Error'}

    def stock_momentum_strategy(self, data: pd.DataFrame, indicators: Dict) -> Dict:
        """Momentum strategy for individual stocks"""
        try:
            current_price = data['Close'].iloc[-1]
            rsi = indicators.get('rsi', 50)
            stochastic_k = indicators.get('stochastic_k', 50)
            williams_r = indicators.get('williams_r', -50)
            volume_ratio = indicators.get('volume_ratio', 1.0)
            
            # Momentum conditions
            strong_momentum_buy = (
                rsi > 50 and rsi < 70 and  # RSI bullish but not overbought
                stochastic_k > 50 and  # Stochastic bullish
                williams_r > -50 and  # Williams %R bullish
                volume_ratio > 1.3  # Strong volume
            )
            
            strong_momentum_sell = (
                rsi < 50 and rsi > 30 and  # RSI bearish but not oversold
                stochastic_k < 50 and  # Stochastic bearish
                williams_r < -50 and  # Williams %R bearish
                volume_ratio > 1.3  # Strong volume
            )
            
            if strong_momentum_buy:
                target = current_price * 1.03  # 3% target
                stop_loss = current_price * 0.97  # 3% stop loss
                confidence = 0.7
                
                return {
                    'type': 'BUY',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'Stock Momentum'
                }
            elif strong_momentum_sell:
                target = current_price * 0.97
                stop_loss = current_price * 1.03
                confidence = 0.7
                
                return {
                    'type': 'SELL',
                    'confidence': confidence,
                    'target': target,
                    'stop_loss': stop_loss,
                    'strategy_name': 'Stock Momentum'
                }
            else:
                return {
                    'type': 'HOLD',
                    'confidence': 0.3,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'Stock Momentum'
                }
                
        except Exception as e:
            logger.error(f"Error in stock momentum strategy: {str(e)}")
            return {'type': 'HOLD', 'confidence': 0.0, 'target': 0, 'stop_loss': 0, 'strategy_name': 'Error'}

    def stock_volatility_strategy(self, data: pd.DataFrame, indicators: Dict) -> Dict:
        """Volatility-based strategy for stocks"""
        try:
            current_price = data['Close'].iloc[-1]
            bb_upper = indicators.get('bb_upper', current_price)
            bb_lower = indicators.get('bb_lower', current_price)
            bb_width = indicators.get('bb_width', 0.02)
            atr = indicators.get('atr', current_price * 0.02)
            volume_ratio = indicators.get('volume_ratio', 1.0)
            
            # High volatility conditions
            high_volatility = bb_width > 0.03  # Bollinger Band width > 3%
            
            if high_volatility:
                # Volatility expansion strategy
                if current_price <= bb_lower and volume_ratio > 1.2:
                    target = current_price + atr * 2  # Target 2 ATR
                    stop_loss = current_price - atr
                    confidence = 0.6
                    
                    return {
                        'type': 'BUY',
                        'confidence': confidence,
                        'target': target,
                        'stop_loss': stop_loss,
                        'strategy_name': 'Volatility Expansion'
                    }
                elif current_price >= bb_upper and volume_ratio > 1.2:
                    target = current_price - atr * 2
                    stop_loss = current_price + atr
                    confidence = 0.6
                    
                    return {
                        'type': 'SELL',
                        'confidence': confidence,
                        'target': target,
                        'stop_loss': stop_loss,
                        'strategy_name': 'Volatility Expansion'
                    }
            
            return {
                'type': 'HOLD',
                'confidence': 0.3,
                'target': current_price,
                'stop_loss': current_price,
                'strategy_name': 'Volatility'
            }
                
        except Exception as e:
            logger.error(f"Error in stock volatility strategy: {str(e)}")
            return {'type': 'HOLD', 'confidence': 0.0, 'target': 0, 'stop_loss': 0, 'strategy_name': 'Error'}

    def _combine_weighted_signals(self, strategies_results: List[Tuple[Dict, float]], current_price: float) -> Dict:
        """Combine multiple strategy signals with weighted average"""
        try:
            if not strategies_results:
                return {
                    'type': 'HOLD',
                    'confidence': 0.0,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'Combined'
                }
            
            # Calculate weighted averages with confidence
            total_weight_unscaled = sum(weight for _, weight in strategies_results)
            if total_weight_unscaled == 0:
                return {
                    'type': 'HOLD',
                    'confidence': 0.0,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'Combined'
                }
            
            # Weighted signal types (use confidence * weight for accurate weighting)
            buy_weight = sum(signal['confidence'] * weight for signal, weight in strategies_results if signal['type'] == 'BUY')
            sell_weight = sum(signal['confidence'] * weight for signal, weight in strategies_results if signal['type'] == 'SELL')
            hold_weight = sum(signal['confidence'] * weight for signal, weight in strategies_results if signal['type'] == 'HOLD')
            
            effective_total = buy_weight + sell_weight + hold_weight
            if effective_total == 0:
                return {
                    'type': 'HOLD',
                    'confidence': 0.0,
                    'target': current_price,
                    'stop_loss': current_price,
                    'strategy_name': 'Combined'
                }
            
            # Determine final signal type (pick the strongest signal)
            if buy_weight > sell_weight and buy_weight > hold_weight:
                final_type = 'BUY'
                confidence = buy_weight / effective_total
            elif sell_weight > buy_weight and sell_weight > hold_weight:
                final_type = 'SELL'
                confidence = sell_weight / effective_total
            else:
                final_type = 'HOLD'
                confidence = hold_weight / effective_total
            
            # Calculate weighted targets and stop losses (using confidence * weight)
            if final_type == 'BUY':
                relevant = [(signal, weight) for signal, weight in strategies_results if signal['type'] == 'BUY']
                if relevant:
                    total_cw = sum(signal['confidence'] * weight for signal, weight in relevant)
                    target = sum(signal['target'] * signal['confidence'] * weight for signal, weight in relevant) / total_cw
                    stop_loss = sum(signal['stop_loss'] * signal['confidence'] * weight for signal, weight in relevant) / total_cw
                else:
                    target = current_price * 1.02
                    stop_loss = current_price * 0.98
            elif final_type == 'SELL':
                relevant = [(signal, weight) for signal, weight in strategies_results if signal['type'] == 'SELL']
                if relevant:
                    total_cw = sum(signal['confidence'] * weight for signal, weight in relevant)
                    target = sum(signal['target'] * signal['confidence'] * weight for signal, weight in relevant) / total_cw
                    stop_loss = sum(signal['stop_loss'] * signal['confidence'] * weight for signal, weight in relevant) / total_cw
                else:
                    target = current_price * 0.98
                    stop_loss = current_price * 1.02
            else:
                target = current_price
                stop_loss = current_price
            
            return {
                'type': final_type,
                'confidence': confidence,
                'target': target,
                'stop_loss': stop_loss,
                'strategy_name': 'Multi-Strategy'
            }
            
        except Exception as e:
            logger.error(f"Error combining weighted signals: {str(e)}")
            return {
                'type': 'HOLD',
                'confidence': 0.0,
                'target': current_price,
                'stop_loss': current_price,
                'strategy_name': 'Error'
            }
    
    def get_all_signals(self) -> List[IndianTradeSignal]:
        """Get trading signals for all Indian symbols (parallel execution for speed)"""
        import concurrent.futures
        signals = []
        # Filter out blocked symbols before analysis
        symbol_list = [s for s in self.indian_symbols.keys()
                       if s.upper() not in BLOCKED_SYMBOLS]
        logger.info(f"Getting signals for {len(symbol_list)} tradeable symbols (parallel)")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_symbol = {executor.submit(self.analyze_indian_market, symbol): symbol for symbol in symbol_list}
            for future in concurrent.futures.as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    signal = future.result()
                    # RAISED threshold from 0.72 → 0.82 for higher quality signals
                    if signal.signal_type != 'HOLD' and signal.confidence >= 0.82:
                        signals.append(signal)
                        logger.info(f"✅ HIGH-CONF SIGNAL: {symbol} {signal.signal_type} (conf: {signal.confidence:.2f})")
                    elif signal.signal_type != 'HOLD':
                        logger.info(f"⏭️ BELOW THRESHOLD: {symbol} {signal.signal_type} (conf: {signal.confidence:.2f} < 0.82)")
                except Exception as e:
                    logger.error(f"Error getting signal for {symbol}: {str(e)}")
                    continue
        
        signals.sort(key=lambda x: x.confidence, reverse=True)
        logger.info(f"Returning {len(signals)} high-confidence signals (threshold >= 0.82)")
        return signals
    
    def save_signal_to_db(self, signal: IndianTradeSignal, user_id: int):
        """Save trading signal to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO signals (user_id, pair, direction, confidence, time, created_at, 
                                  entry_price, stop_loss, take_profit, strategy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, signal.symbol, signal.signal_type, signal.confidence,
                signal.timestamp, signal.timestamp, signal.entry_price,
                signal.stop_loss, signal.target_price, signal.strategy
            ))
            
            conn.commit()
            conn.close()
            logger.info(f"Signal saved for {signal.symbol}")
            
        except Exception as e:
            logger.error(f"Error saving signal: {str(e)}")

# Auto-trading functionality
class IndianAutoTrader:
    """Auto-trading system for Indian markets"""
    _active_instance = None
    _instance_lock = threading.Lock()
    
    def __init__(self, trading_system: IndianTradingSystem, user_id: int = 3, default_quantity: int = 1, initial_balance: float = 100000.0):
        self.trading_system = trading_system
        self.active_trades = {}
        self.running = False
        self.trading_thread = None
        self.trade_history = []
        self.total_pnl = 0.0
        self.user_id = user_id
        self.default_quantity = default_quantity
        self.initial_balance = initial_balance
        self.latest_prices = {}
        self.max_concurrent_trades = 5
        self.daily_pnl = 0.0
        self.daily_trade_date = datetime.now().strftime('%Y-%m-%d')
        self.max_daily_loss_pct = 0.02
        self.min_rr_ratio = 1.5
        self.capital_utilization_pct = 0.80
        self.trend_ema_period = 50
        self.min_volatility_pct = 0.003
        self.last_signal_cache = {}
        self.last_signal_cache_ts = 0
        # PILLAR 1: Per-symbol cooldown — {symbol: timestamp_of_last_close}
        self.symbol_cooldown = {}
        self.cooldown_seconds = 300  # 5 minutes cooldown after closing a trade
        # PILLAR 3: Signal persistence — require 2 consecutive confirms before entry
        self.signal_confirm_cache = {}  # {symbol: {'direction': str, 'count': int, 'first_seen': float}}
        self.min_signal_confirms = 2  # Must see same signal 2 times in a row
        # PILLAR 6: No re-entry same direction per day — {(symbol, direction): date}
        self.daily_direction_tracker = {}
        # PILLAR 5: Gemini AI validation (lazy init)
        self._gemini_client = None
        self._gemini_cache = {}  # {symbol: {'result': bool, 'ts': float}}
        self._gemini_cache_ttl = 120  # Cache Gemini results for 2 minutes
        # Thread safety lock for all mutable shared state
        self._lock = threading.Lock()
        # Drawdown streak tracking
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        # Tracks which trades have been partially scaled out (trade_id -> True)
        self.scaled_out = {}
        # Sector mapping for correlation cap
        self.sector_map = {
            'RELIANCE': 'Oil&Gas', 'TCS': 'IT', 'INFY': 'IT', 'WIPRO': 'IT',
            'HDFCBANK': 'Financial', 'ICICIBANK': 'Financial', 'KOTAKBANK': 'Financial', 'SBIN': 'Financial',
            'BAJFINANCE': 'Financial', 'AXISBANK': 'Financial',
            'BHARTIARTL': 'Telecom',
            'HINDUNILVR': 'FMCG', 'ITC': 'FMCG', 'NESTLEIND': 'FMCG', 'BRITANNIA': 'FMCG',
            'ASIANPAINT': 'Consumer', 'TITAN': 'Consumer',
            'MARUTI': 'Auto', 'M&M': 'Auto',
            'POWERGRID': 'Utilities', 'NTPC': 'Utilities',
            'NIFTY50': 'Index', 'BANKNIFTY': 'Index', 'SENSEX': 'Index', 'FINNIFTY': 'Index', 'MIDCPNIFTY': 'Index',
            'NIFTYREALTY': 'Index', 'NIFTYPVTBANK': 'Index', 'NIFTYPSUBANK': 'Index', 'NIFTYFIN': 'Index', 'NIFTYMEDIA': 'Index',
        }
        self.max_trades_per_sector = 2
        # Reload persisted active trades on startup
        self._load_active_trades_from_db()

    def _load_active_trades_from_db(self):
        """Reload active trades from database to survive restarts"""
        try:
            conn = sqlite3.connect(self.trading_system.db_path)
            cur = conn.cursor()
            cur.execute("SELECT id, symbol, type, entry_price, quantity, entry_time, strategy, confidence, stop_loss, target_price, COALESCE(partial_exit_done, 0) FROM active_trades WHERE user_id=?", (self.user_id,))
            for row in cur.fetchall():
                tid = row[0]
                entry_time_str = row[5]
                try:
                    entry_dt = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')
                    entry_epoch = entry_dt.timestamp()
                except Exception:
                    entry_epoch = time.time()

                partial_exit = bool(row[10])
                self.active_trades[tid] = {
                    'id': tid,
                    'symbol': row[1],
                    'type': row[2],
                    'entry_price': float(row[3]),
                    'quantity': int(row[4]),
                    'entry_time': entry_time_str,
                    'entry_epoch': entry_epoch,
                    'timestamp': entry_time_str,
                    'strategy': row[6] or 'Auto',
                    'confidence': float(row[7]) if row[7] else 0.0,
                    'target_price': float(row[9]) if row[9] is not None else 0.0,
                    'stop_loss': float(row[8]) if row[8] is not None else 0.0,
                    'partial_exit_done': partial_exit,
                    'status': 'ACTIVE'
                }
                if partial_exit:
                    self.scaled_out[tid] = True
                logger.info(f"Restored active trade: {tid} {row[1]} {row[2]} (SL: {self.active_trades[tid]['stop_loss']:.2f}, TP: {self.active_trades[tid]['target_price']:.2f})")
            conn.close()
            if self.active_trades:
                logger.info(f"Loaded {len(self.active_trades)} active trades from database")
        except Exception as e:
            logger.warning(f"Could not load active trades from DB: {e}")
        
    def start(self):
        """Start auto-trading"""
        with IndianAutoTrader._instance_lock:
            if IndianAutoTrader._active_instance and IndianAutoTrader._active_instance is not self:
                logger.info("Stopping previous duplicate IndianAutoTrader instance thread...")
                try:
                    IndianAutoTrader._active_instance.stop()
                except Exception as e:
                    logger.warning(f"Error stopping previous instance: {e}")
            IndianAutoTrader._active_instance = self

        if self.running and self.trading_thread and self.trading_thread.is_alive():
            logger.warning("Auto-trading already running")
            return
        
        # Reset state if thread is dead
        if self.trading_thread and not self.trading_thread.is_alive():
            logger.info("Previous trading thread was dead, restarting...")
            self.running = False
            
        self.running = True
        self.trading_thread = threading.Thread(target=self._trading_loop)
        self.trading_thread.daemon = True
        self.trading_thread.start()
        logger.info("Indian auto-trading started")
        
    def stop(self):
        """Stop auto-trading"""
        self.running = False
        if self.trading_thread:
            self.trading_thread.join(timeout=10)  # Wait up to 10s for clean exit
            if self.trading_thread.is_alive():
                logger.warning("Trading thread did not stop gracefully — may have been in long sleep")
        logger.info("Indian auto-trading stopped")

    @staticmethod
    def _interruptible_sleep(seconds, running_ref):
        """Sleep for `seconds` but check `running_ref` every 1s for fast shutdown.
        `running_ref` is a callable that returns True if still running."""
        for _ in range(int(seconds)):
            try:
                if not running_ref():
                    return
            except Exception:
                return
            time.sleep(1)

    def _trading_loop(self):
        """Main trading loop — auto-sleeps until next market open when closed"""
        logger.info("Trading loop started (v2 — profitability overhaul)")
        while self.running:
            # PILLAR 6: Global 20% Cumulative Drawdown Circuit Breaker
            if self._check_global_drawdown_limit():
                logger.error("🚨 Auto-trader halted due to global 20% drawdown circuit breaker.")
                break
            try:
                if self.trading_system.is_market_open():
                    # PILLAR 1: Opening bell filter — skip first 15 min (09:15-09:30)
                    try:
                        from datetime import timezone
                        ist = timezone(timedelta(hours=5, minutes=30))
                        now_ist = datetime.now(ist).time()
                        opening_bell_end = datetime.strptime('09:30', '%H:%M').time()
                        if now_ist < opening_bell_end:
                            logger.info(f"⏳ Opening bell filter: skipping until 09:30 IST (currently {now_ist.strftime('%H:%M')})")
                            self._interruptible_sleep(30, lambda: self.running)
                            continue
                    except Exception:
                        pass  # Non-critical, proceed if timezone fails

                    # Reset daily tracker at date change
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    if today_str != self.daily_trade_date:
                        self.daily_trade_date = today_str
                        self.daily_pnl = 0.0
                        self.daily_direction_tracker = {}
                        self.signal_confirm_cache = {}
                        # Streaks intentionally NOT reset — persistent across days for sizing protection
                        # self.consecutive_wins = 0
                        # self.consecutive_losses = 0

                    active_count = len(self.active_trades)
                    logger.info(f"Market open — {active_count}/{self.max_concurrent_trades} active trades")
                    
                    # FIXED: Removed `or True` bypass — only fetch signals when under limit
                    # But still fetch for reverse-signal exit detection
                    try:
                        signals = self.trading_system.get_all_signals()
                        logger.info(f"Generated {len(signals)} high-confidence signals")
                    except Exception as e:
                        logger.error(f"Error getting signals: {str(e)}")
                        signals = []
                    
                    # Cache signals for reverse-signal exit detection (still needed)
                    self.last_signal_cache = {}
                    for s in signals:
                        self.last_signal_cache[s.symbol.upper()] = s.signal_type
                    self.last_signal_cache_ts = time.time()
                    
                    # PILLAR 3: Signal persistence — update confirm counts
                    for signal in signals:
                        sym = signal.symbol.upper()
                        direction = signal.signal_type
                        if sym in self.signal_confirm_cache:
                            cached = self.signal_confirm_cache[sym]
                            if cached['direction'] == direction:
                                cached['count'] += 1
                            else:
                                # Direction changed, reset counter
                                self.signal_confirm_cache[sym] = {'direction': direction, 'count': 1, 'first_seen': time.time()}
                        else:
                            self.signal_confirm_cache[sym] = {'direction': direction, 'count': 1, 'first_seen': time.time()}
                    
                    # Only try to enter new trades if under the limit
                    if active_count < self.max_concurrent_trades:
                        for signal in signals:
                            if len(self.active_trades) >= self.max_concurrent_trades:
                                logger.info("Max concurrent trades reached, stopping new entries")
                                break
                            
                            sym = signal.symbol.upper()
                            confirm = self.signal_confirm_cache.get(sym, {})
                            
                            # PILLAR 3 / USER ENHANCEMENT: Confidence-Based Confirmation Gate.
                            # High-confidence signals (>= 85%) enter immediately (required_confirms = 1) to capture the best entry price.
                            # Standard-confidence signals (< 85%) require 2 confirmations to protect against high-noise market fluctuations.
                            required_confirms = 1 if signal.confidence >= 0.85 else self.min_signal_confirms
                            
                            if confirm.get('count', 0) < required_confirms:
                                logger.info(f"⏳ WAITING CONFIRM: {sym} {signal.signal_type} ({confirm.get('count', 0)}/{required_confirms})")
                                continue
                            
                            logger.info(f"🎯 CONFIRMED & EXECUTING: {signal.symbol} {signal.signal_type} (conf: {signal.confidence:.2f}, confirms: {confirm.get('count', 0)})")
                            self._execute_trade(signal)
                    else:
                        logger.info(f"At max concurrent trades ({self.max_concurrent_trades}), monitoring only")
                    
                    self._monitor_trades()
                    
                    # SLOWED from 10s → 30s to reduce noise and over-trading
                    self._interruptible_sleep(30, lambda: self.running)
                else:
                    next_open = self._seconds_until_next_market_open()
                    if next_open and next_open > 0:
                        hrs = next_open // 3600
                        mins = (next_open % 3600) // 60
                        logger.info(f"Market closed — sleeping {hrs}h {mins}m until next open")
                        sleep_for = min(next_open, 3600)
                        self._interruptible_sleep(sleep_for, lambda: self.running)
                    else:
                        self._interruptible_sleep(60, lambda: self.running)
                
            except Exception as e:
                logger.error(f"Error in trading loop: {str(e)}")
                self._interruptible_sleep(120, lambda: self.running)

    def _seconds_until_next_market_open(self) -> int:
        """Calculate seconds until the next market open time"""
        try:
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist)
            market_open_today = now.replace(hour=9, minute=15, second=0, microsecond=0)
            if now.weekday() < 5 and now.time() < market_open_today.time():
                return int((market_open_today - now).total_seconds())
            for days_ahead in range(1, 8):
                next_day = now + timedelta(days=days_ahead)
                if next_day.weekday() < 5:
                    next_open = next_day.replace(hour=9, minute=15, second=0, microsecond=0)
                    return int((next_open - now).total_seconds())
            return 3600
        except Exception as e:
            logger.error(f"Error calculating next market open: {e}")
            return 3600

    def on_price_update(self, symbol: str, price: float):
        """Handle real-time price ticks from WebSocket for instant reactions"""
        if not self.running:
            return
        
        # Reject clearly bad price ticks (below 1 paisa or absurd values)
        if price <= 0 or price > 500000:
            logger.warning(f"⚠️ WebSocket bad tick for {symbol}: {price} — rejected")
            return
        
        # Validate against expected range
        if not self.trading_system.validate_price(symbol, price):
            logger.warning(f"⚠️ WebSocket price out of range for {symbol}: {price} — rejected")
            return
            
        self.latest_prices[symbol] = price

        # Update current_price on all active trades for this symbol
        with self._lock:
            for trade_id, trade in list(self.active_trades.items()):
                if trade['symbol'] == symbol:
                    # Per-trade sanity check against entry price before storing
                    entry = trade.get('entry_price', 0)
                    if entry > 0:
                        deviation = abs(price - entry) / entry
                        if deviation > 0.50:
                            logger.warning(f"⚠️ WebSocket tick for {symbol} deviates {deviation*100:.1f}% from entry {entry} — skipped")
                            continue
                    trade['current_price'] = price
                    self._evaluate_trade_exit(trade_id, trade, price)

    def _update_trailing_stop(self, trade_id: str, trade: dict, current_price: float):
        """ATR-based trailing stop: lock profits while giving room for trends."""
        atr_pct = self._get_atr_pct(trade['symbol'])
        # Session-based volatility bands: tighter stops at open/close, wider at midday
        try:
            from datetime import timezone, timedelta
            ist = timezone(timedelta(hours=5, minutes=30))
            now_ist = datetime.now(ist).time()
            open_session = datetime.strptime('09:15', '%H:%M').time()
            mid_session = datetime.strptime('11:30', '%H:%M').time()
            late_session = datetime.strptime('14:00', '%H:%M').time()
            close_session = datetime.strptime('15:00', '%H:%M').time()
            session_mult = 1.0
            if now_ist < mid_session:
                session_mult = 0.7  # Tighter in early session
            elif now_ist >= late_session:
                session_mult = 0.6  # Tighter in late session (lock profits before close)
            if now_ist >= close_session:
                session_mult = 0.4  # Very tight in last 30 min
        except Exception:
            session_mult = 1.0
        trail_dist = max(atr_pct * 1.5, 0.005) * trade['entry_price'] * session_mult
        
        # USER ENHANCEMENT: Tighten trailing stop by 50% during extended time maturity to lock profits
        if trade.get('extended_maturity'):
            trail_dist = trail_dist * 0.5
            
        pct_from_entry = abs(current_price - trade['entry_price']) / trade['entry_price']
        
        # Move to breakeven once 1 ATR in profit
        if 'breakeven_set' not in trade:
            if pct_from_entry >= atr_pct:
                if trade['type'] == 'BUY' and current_price > trade['entry_price']:
                    new_sl = trade['entry_price'] * 1.001
                    if new_sl > trade['stop_loss']:
                        trade['stop_loss'] = new_sl
                        trade['breakeven_set'] = True
                        logger.info(f"🔒 Breakeven set for {trade_id} (BUY)")
                elif trade['type'] == 'SELL' and current_price < trade['entry_price']:
                    new_sl = trade['entry_price'] * 0.999
                    if new_sl < trade['stop_loss']:
                        trade['stop_loss'] = new_sl
                        trade['breakeven_set'] = True
                        logger.info(f"🔒 Breakeven set for {trade_id} (SELL)")
            # Gradually tighten trailing stop even before breakeven using 3x wider trail distance
            pre_breakeven_dist = trail_dist * 3
            if trade['type'] == 'BUY':
                new_stop = current_price - pre_breakeven_dist
                if current_price > trade['entry_price'] and new_stop > trade['stop_loss']:
                    trade['stop_loss'] = new_stop
            elif trade['type'] == 'SELL':
                new_stop = current_price + pre_breakeven_dist
                if current_price < trade['entry_price'] and new_stop < trade['stop_loss']:
                    trade['stop_loss'] = new_stop
            return
        
        # ATR-based trailing after breakeven
        if trade['type'] == 'BUY':
            new_stop = current_price - trail_dist
            if current_price > trade['entry_price'] and new_stop > trade['stop_loss']:
                trade['stop_loss'] = new_stop
                logger.info(f"📈 ATR Trailing {trade_id} (BUY) -> SL: {new_stop:.2f}")
                try:
                    conn = sqlite3.connect(self.trading_system.db_path)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE active_trades SET stop_loss = ? WHERE id = ?", (float(new_stop), trade_id))
                    conn.commit()
                    conn.close()
                except Exception as db_e:
                    logger.error(f"Failed to update stop_loss in DB for {trade_id}: {db_e}")
        elif trade['type'] == 'SELL':
            new_stop = current_price + trail_dist
            if current_price < trade['entry_price'] and new_stop < trade['stop_loss']:
                trade['stop_loss'] = new_stop
                logger.info(f"📉 ATR Trailing {trade_id} (SELL) -> SL: {new_stop:.2f}")
                try:
                    conn = sqlite3.connect(self.trading_system.db_path)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE active_trades SET stop_loss = ? WHERE id = ?", (float(new_stop), trade_id))
                    conn.commit()
                    conn.close()
                except Exception as db_e:
                    logger.error(f"Failed to update stop_loss in DB for {trade_id}: {db_e}")

    def _is_price_sane(self, symbol: str, price: float, entry_price: float) -> bool:
        """Sanity check: price must be within 50% of entry and within absolute bounds"""
        if price <= 0:
            return False
        # Within 50% of entry price
        if entry_price > 0:
            deviation = abs(price - entry_price) / entry_price
            if deviation > 0.50:
                logger.warning(f"⚠️ Price sanity FAIL: {symbol} price={price:.2f} deviates {deviation*100:.1f}% from entry={entry_price:.2f}")
                return False
        # Within absolute bounds (dynamic, not hardcoded ranges)
        if price < self.trading_system._absolute_price_floor or price > self.trading_system._absolute_price_ceiling:
            logger.warning(f"⚠️ Price range FAIL: {symbol} price={price:.2f} outside absolute bounds")
            return False
        return True

    def _evaluate_trade_exit(self, trade_id: str, trade: dict, current_price: float):
        """Evaluate if an active trade needs to be closed based on the current price"""
        if trade_id not in self.active_trades:
            return
        
        # PRICE SANITY CHECK: reject clearly bad data before acting on it
        if not self._is_price_sane(trade['symbol'], current_price, trade['entry_price']):
            logger.warning(f"⏭️ Skipping exit evaluation for {trade_id} due to bad price {current_price:.2f}")
            return

        # STALE PRICE GUARD: Skip exit evaluation for first 60 seconds after entry
        # to prevent stale cached prices from triggering immediate exits
        entry_epoch = float(trade.get('entry_epoch') or time.time())
        trade_age_seconds = time.time() - entry_epoch
        if trade_age_seconds < 60:
            return

        # Update trailing stops before evaluating exits
        self._update_trailing_stop(trade_id, trade, current_price)

        # SCALE OUT: if price has reached 1:1 R:R AND trade is IN PROFIT,
        # close 50% via the robust _partial_close_trade method (broker order, trade history, DB persist)
        if trade_id not in self.scaled_out and not trade.get('partial_exit_done'):
            try:
                stop_loss = trade.get('stop_loss', 0) or trade.get('initial_stop_loss', 0)
                if stop_loss > 0 and trade['entry_price'] > 0:
                    risk_per_unit = abs(trade['entry_price'] - stop_loss)
                    if trade['type'] == 'BUY':
                        reward_per_unit = current_price - trade['entry_price']
                    else:
                        reward_per_unit = trade['entry_price'] - current_price
                    rr_achieved = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0
                    # PROFIT DIRECTION CHECK: only scale out when trade is actually in profit
                    in_profit = (trade['type'] == 'BUY' and current_price > trade['entry_price']) or                                 (trade['type'] == 'SELL' and current_price < trade['entry_price'])
                    if rr_achieved >= 1.0 and in_profit:
                        self._partial_close_trade(trade_id, 'Scale Out 1:1', current_price, 0.5)
                        self.scaled_out[trade_id] = True
            except Exception as e:
                logger.warning(f"Scale-out check failed for {trade_id}: {e}")

        # REVERSE SIGNAL EXIT — if latest signal contradicts trade direction, exit
        # REQUIRE 2 consecutive confirms AND 15 min minimum hold to avoid false flips
        sym = trade['symbol'].upper()
        if sym in self.last_signal_cache:
            latest_signal = self.last_signal_cache[sym]
            entry_epoch = float(trade.get('entry_epoch') or time.time())
            trade_age_seconds = time.time() - entry_epoch
            confirm = self.signal_confirm_cache.get(sym, {})
            reverse_confirms = confirm.get('count', 0) if confirm.get('direction') == latest_signal else 0
            if trade_age_seconds >= 900 and reverse_confirms >= 2:
                if latest_signal == 'BUY' and trade['type'] == 'SELL':
                    self._close_trade(trade_id, 'Reverse Signal (BUY)', current_price)
                    return
                elif latest_signal == 'SELL' and trade['type'] == 'BUY':
                    self._close_trade(trade_id, 'Reverse Signal (SELL)', current_price)
                    return
            
        # Auto-close near market end (15:29:30 to 15:31:00 IST)
        try:
            from datetime import timezone, timedelta
            ist = timezone(timedelta(hours=5, minutes=30))
            now_ist = datetime.now(ist).time()
            market_close_guard_start = datetime.strptime('15:29:30', '%H:%M:%S').time()
            market_close_guard_end = datetime.strptime('15:31:00', '%H:%M:%S').time()
            if market_close_guard_start <= now_ist <= market_close_guard_end:
                self._close_trade(trade_id, 'Market Close Exit', current_price)
                return
        except Exception as _:
            pass

        # PILLAR 6 / USER ENHANCEMENT: Momentum-Based Time Exit Extension (with 15-minute extension for winners)
        try:
            entry_epoch = float(trade.get('entry_epoch') or time.time())
            trade_age_seconds = time.time() - entry_epoch
            standard_limit = 45 * 60  # 45 minutes
            extended_limit = 60 * 60  # 60 minutes
            
            if trade_age_seconds >= standard_limit:
                is_in_profit = False
                if trade['type'] == 'BUY' and current_price > trade['entry_price']:
                    is_in_profit = True
                elif trade['type'] == 'SELL' and current_price < trade['entry_price']:
                    is_in_profit = True
                
                # Check if the AI still supports the trade direction
                sym = trade['symbol'].upper()
                ai_still_supports = False
                if sym in self.last_signal_cache:
                    if self.last_signal_cache[sym] == trade['type']:
                        ai_still_supports = True
                
                if is_in_profit and ai_still_supports and trade_age_seconds < extended_limit:
                    # Extend maturity by another 15 minutes!
                    if 'extended_maturity' not in trade:
                        trade['extended_maturity'] = True
                        logger.info(f"🚀 TIME EXTENSION for {trade_id} ({trade['symbol']}): Trade is in profit and AI still supports direction — extending to 60-min with a 50% tighter trailing stop!")
                else:
                    reason_str = 'Max Duration Exit (60min Extended)' if trade.get('extended_maturity') else 'Max Duration Exit (45min)'
                    self._close_trade(trade_id, reason_str, current_price)
                    return
        except Exception as e:
            logger.warning(f"Error in momentum-based time exit extension: {e}")
        
        # Check stop loss
        if trade['type'] == 'BUY' and current_price <= trade['stop_loss']:
            self._close_trade(trade_id, 'Stop Loss Hit', current_price)
        elif trade['type'] == 'SELL' and current_price >= trade['stop_loss']:
            self._close_trade(trade_id, 'Stop Loss Hit', current_price)
            
        # PILLAR 6: Check target — FULL CLOSE at target (not partial)
        # Partial close with qty=1 was causing guaranteed losses on the remaining half
        elif trade['type'] == 'BUY' and current_price >= trade['target_price']:
            self._close_trade(trade_id, '🎯 Target Hit (FULL)', current_price)
        elif trade['type'] == 'SELL' and current_price <= trade['target_price']:
            self._close_trade(trade_id, '🎯 Target Hit (FULL)', current_price)

    def _partial_close_trade(self, trade_id: str, reason: str, exit_price: float, close_ratio: float = 0.5):
        """Close a portion of the trade and move stop loss to breakeven"""
        try:
            if trade_id in self.active_trades:
                trade = self.active_trades[trade_id]
                if trade.get('partial_exit_done'):
                    return

                original_quantity = trade.get('quantity', self.default_quantity)
                close_quantity = max(1, int(original_quantity * close_ratio))
                remaining_quantity = original_quantity - close_quantity
                
                if remaining_quantity <= 0:
                    # If the position cannot be split (e.g., quantity = 1), just do a full close
                    self._close_trade(trade_id, reason, exit_price)
                    return

                logger.info(f"Partial closing trade {trade_id}: {reason} - Qty: {close_quantity}")
                
                # Place partial closing order (only real broker in LIVE mode)
                if self.trading_system.is_live() and self.trading_system.angel_one and self.trading_system.angel_one.is_connected:
                    close_type = "SELL" if trade['type'] == "BUY" else "BUY"
                    order_response = self.trading_system.angel_one.place_order(
                        symbol=trade['symbol'],
                        quantity=close_quantity,
                        order_type=close_type,
                        product_type="INTRADAY",
                        price=exit_price
                    )
                    if not order_response.get("status"):
                        logger.error(f"Failed to partial close broker order for {trade['symbol']}: {order_response.get('error')}")
                else:
                    logger.info(f"SIMULATED partial close: {trade['symbol']} qty={close_quantity} @ {exit_price}")

                # Calculate absolute P&L amount for the partial close
                entry_price = trade['entry_price']
                if trade['type'] == 'BUY':
                    pnl_amount = (exit_price - entry_price) * close_quantity
                else:
                    pnl_amount = (entry_price - exit_price) * close_quantity

                logger.info(f"Trade {trade_id} Partial P&L amount: {pnl_amount:.2f}")
                self.total_pnl += pnl_amount
                
                # Record the partial trade history
                partial_trade_record = {
                    'id': f"{trade_id}_partial",
                    'symbol': trade['symbol'],
                    'type': trade['type'],
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'quantity': close_quantity,
                    'reason': reason,
                    'pnl_amount': pnl_amount,
                    'exit_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                self.trade_history.append(partial_trade_record)
                
                # Save the old stop loss for logging before moving to breakeven
                old_stop_loss = trade.get('stop_loss', 0) or 0

                # Update the in-memory trade object for the remaining portion
                trade['quantity'] = remaining_quantity
                trade['partial_exit_done'] = True
                
                # Move stop loss to breakeven to secure the rest of the trade
                if trade['type'] == 'BUY' and entry_price > old_stop_loss:
                    trade['stop_loss'] = entry_price
                    logger.info(f"Moved Stop Loss to breakeven ({entry_price}) for {trade_id}")
                elif trade['type'] == 'SELL' and entry_price < old_stop_loss:
                    trade['stop_loss'] = entry_price
                    logger.info(f"Moved Stop Loss to breakeven ({entry_price}) for {trade_id}")

                # Persist partial close to SQLite
                try:
                    conn = sqlite3.connect(self.trading_system.db_path)
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO trades (user_id, symbol, direction, entry_price, exit_price, quantity, status, entry_time, exit_time, profit_loss, stop_loss, take_profit)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        self.user_id, trade['symbol'], trade['type'], float(entry_price),
                        float(exit_price), float(close_quantity), 'CLOSED',
                        trade.get('entry_time', partial_trade_record['exit_time']), partial_trade_record['exit_time'], float(pnl_amount),
                        float(old_stop_loss),
                        float(trade.get('target_price', trade.get('take_profit', 0)) or 0)
                    ))
                    
                    cursor.execute('SELECT portfolio_value FROM portfolio_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (self.user_id,))
                    row = cursor.fetchone()
                    last_value = float(row[0]) if row else float(self.initial_balance)
                    new_value = last_value + float(pnl_amount)
                    
                    cursor.execute('INSERT INTO portfolio_history (user_id, portfolio_value, timestamp) VALUES (?, ?, ?)',
                                   (self.user_id, new_value, partial_trade_record['exit_time']))
                    
                    cursor.execute('UPDATE active_trades SET quantity = ?, partial_exit_done = 1, stop_loss = ? WHERE id = ?',
                                   (remaining_quantity, trade['stop_loss'], trade_id))
                    
                    conn.commit()
                    conn.close()
                except Exception as db_err:
                    logger.error(f"Error updating portfolio/partial trades in DB: {db_err}")

                # Log activity
                try:
                    self.trading_system.log_activity(
                        f'PARTIAL({reason})', trade['symbol'],
                        entry_price, exit_price, close_quantity,
                        pnl_amount, self.initial_balance + self.total_pnl,
                        trade.get('strategy', 'Auto')
                    )
                except Exception:
                    pass

                # Emit Socket.IO event to update the frontend UI without refresh
                try:
                    from app import socketio
                    socketio.emit('trade_partial_close', {
                        'trade_id': trade_id,
                        'symbol': trade['symbol'],
                        'reason': reason,
                        'pnl': float(pnl_amount),
                        'remaining_quantity': remaining_quantity,
                        'new_stop_loss': trade['stop_loss']
                    })
                except Exception as emit_err:
                    logger.error(f"Socket.IO emit error: {emit_err}")

        except Exception as e:
            logger.error(f"Error partial closing trade: {str(e)}")

    def _get_atr_pct(self, symbol: str) -> float:
        """Get ATR percentage for a symbol to gauge volatility"""
        try:
            df = self.trading_system.get_indian_market_data(symbol, period='1mo', interval='1d')
            if df is not None and not df.empty and len(df) > 14:
                from numpy import nan
                high = df['High'].values
                low = df['Low'].values
                close = df['Close'].values
                tr = np.maximum(high[1:] - low[1:],
                    np.maximum(abs(high[1:] - close[:-1]),
                               abs(low[1:] - close[:-1])))
                atr = np.mean(tr[-14:])
                return atr / close[-1] if close[-1] > 0 else 0.02
        except Exception:
            pass
        return 0.02

    def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit is hit. Returns True if trading should stop."""
        # NOTE: daily_pnl is reset at day boundary in _trading_loop (line 1583), NOT here
        # to avoid race with _close_trade updating daily_pnl mid-day.
        daily_loss_limit = self.initial_balance * self.max_daily_loss_pct
        if self.daily_pnl <= -daily_loss_limit:
            logger.warning(f"⚠️ DAILY LOSS LIMIT HIT: ₹{self.daily_pnl:.2f} (limit: -₹{daily_loss_limit:.2f}) — stopping new entries")
            return True
        return False

    def _check_global_drawdown_limit(self) -> bool:
        """Check if cumulative drawdown exceeds 20% of initial investment. Halts trading if hit."""
        max_loss = self.initial_balance * 0.20  # 20% Global Halt
        current_pnl = self.total_pnl
        if current_pnl <= -max_loss:
            logger.warning(f"🚨 GLOBAL DRAWDOWN LIMIT HIT (20%): Cumulative P&L is ₹{current_pnl:.2f} (limit: -₹{max_loss:.2f}) — halting trading system!")
            self.running = False
            try:
                # Log critical halt to session log
                self.trading_system.log_activity(
                    'CRITICAL_HALT', 'GLOBAL', 0, 0, 0, current_pnl, 
                    self.initial_balance + current_pnl, 
                    'Drawdown Limit Hit (20% Global Halt)'
                )
            except Exception:
                pass
            return True
        return False

    def _check_correlation(self, symbol: str) -> bool:
        """Skip trade if sector already has max_trades_per_sector active positions."""
        symbol_upper = symbol.upper()
        # Resolve symbol to sector using the sector_map
        symbol_sector = None
        for sym, sec in self.sector_map.items():
            if sym in symbol_upper or symbol_upper in sym:
                symbol_sector = sec
                break
        if not symbol_sector:
            return True
        # Count how many active trades are in the same sector
        sector_count = 0
        with self._lock:
            for trade in self.active_trades.values():
                tsym = trade['symbol'].upper()
                for sym, sec in self.sector_map.items():
                    if sym in tsym or tsym in sym:
                        if sec == symbol_sector:
                            sector_count += 1
                            break
        if sector_count >= self.max_trades_per_sector:
            logger.info(f"⏭️ Skipping {symbol} ({symbol_sector}) — already {sector_count} active trades in this sector (max {self.max_trades_per_sector})")
            return False
        return True

    def _validate_with_gemini(self, signal: IndianTradeSignal) -> bool:
        """PILLAR 5: Use Gemini AI to validate a signal before execution"""
        try:
            sym = signal.symbol.upper()
            # Check cache first
            cached = self._gemini_cache.get(sym)
            if cached and (time.time() - cached['ts']) < self._gemini_cache_ttl:
                return cached['result']
            
            # Lazy-init Gemini client
            if self._gemini_client is None:
                try:
                    from ai_models.gemini_explainer import GeminiAPIClient
                    self._gemini_client = GeminiAPIClient()
                    if not self._gemini_client.is_active():
                        logger.warning("Gemini API key not set — skipping validation")
                        return True
                except Exception as e:
                    logger.warning(f"Gemini client init failed: {e} — skipping validation")
                    return True  # Allow trade if Gemini unavailable
            
            if not self._gemini_client.is_active():
                return True  # Allow if no API key
            
            prompt = (
                f"You are a professional Indian stock market analyst. "
                f"Evaluate this intraday trade signal and respond with ONLY the word 'APPROVE' or 'REJECT'.\n\n"
                f"Signal: {signal.signal_type} {signal.symbol}\n"
                f"Entry Price: ₹{signal.entry_price:.2f}\n"
                f"Target: ₹{signal.target_price:.2f} ({abs(signal.target_price - signal.entry_price) / signal.entry_price * 100:.1f}%)\n"
                f"Stop Loss: ₹{signal.stop_loss:.2f} ({abs(signal.stop_loss - signal.entry_price) / signal.entry_price * 100:.1f}%)\n"
                f"Confidence: {signal.confidence:.0%}\n"
                f"Strategy: {signal.strategy}\n"
                f"Risk/Reward: {signal.risk_reward_ratio:.2f}\n\n"
                f"Consider: Is this a good risk/reward setup? Is the direction aligned with the current market trend? "
                f"Respond APPROVE or REJECT only."
            )
            
            response = self._gemini_client._call_ai_api(prompt)
            result = 'APPROVE' in response.upper() if response else True
            
            # Cache result
            self._gemini_cache[sym] = {'result': result, 'ts': time.time()}
            
            if not result:
                logger.info(f"🤖 Gemini REJECTED {signal.symbol} {signal.signal_type}")
            else:
                logger.info(f"🤖 Gemini APPROVED {signal.symbol} {signal.signal_type}")
            
            return result
        except Exception as e:
            logger.warning(f"Gemini validation error: {e} — allowing trade")
            return True  # Allow trade if Gemini fails

    def _execute_trade(self, signal: IndianTradeSignal):
        """Execute a trade based on signal"""
        try:
            # PILLAR 1: Block index symbols (final safety net)
            clean_sym = signal.symbol.replace('.NS', '').replace('.BO', '').upper()
            if clean_sym in BLOCKED_SYMBOLS:
                logger.info(f"🚫 BLOCKED: {signal.symbol} is an index — cannot trade")
                return

            # PRICE SANITY CHECK before entering
            if not self.trading_system.validate_price(signal.symbol, signal.entry_price):
                logger.error(f"❌ REJECTED trade for {signal.symbol}: entry price {signal.entry_price} is invalid")
                return

            # MARKET CLOSE GUARD — no new entries after 14:45 IST (45 min before close)
            try:
                from datetime import timezone, timedelta
                ist = timezone(timedelta(hours=5, minutes=30))
                now_ist = datetime.now(ist).time()
                close_guard = datetime.strptime('14:45', '%H:%M').time()
                if now_ist >= close_guard:
                    logger.info(f"⏭️ Skipping {signal.symbol} — market close guard: {now_ist.strftime('%H:%M')} >= 14:45")
                    return
            except Exception:
                pass

            # PILLAR 1: Per-symbol cooldown — wait 5 min after closing a trade on same symbol
            last_close_ts = self.symbol_cooldown.get(clean_sym, 0)
            if time.time() - last_close_ts < self.cooldown_seconds:
                remaining = int(self.cooldown_seconds - (time.time() - last_close_ts))
                logger.info(f"⏳ COOLDOWN: {signal.symbol} — {remaining}s remaining before re-entry allowed")
                return

            # PILLAR 6: No re-entry same direction per day
            direction_key = (clean_sym, signal.signal_type)
            if direction_key in self.daily_direction_tracker:
                logger.info(f"🚫 NO-REENTRY: Already traded {signal.symbol} {signal.signal_type} today — blocked")
                return
                
            # GLOBAL DRAWDOWN LIMIT
            if self._check_global_drawdown_limit():
                logger.info(f"⏭️ Skipping {signal.symbol} — global 20% drawdown limit reached")
                return

            # DAILY LOSS LIMIT
            if self._check_daily_loss_limit():
                logger.info(f"⏭️ Skipping {signal.symbol} — daily loss limit reached")
                return

            # RISK/REWARD FILTER — skip trades with poor R:R
            if signal.risk_reward_ratio < self.min_rr_ratio:
                logger.info(f"⏭️ Skipping {signal.symbol} {signal.signal_type}: R:R {signal.risk_reward_ratio:.2f} < {self.min_rr_ratio}")
                return

            # TREND FILTER — only trade in direction of 50-EMA
            try:
                df = self.trading_system.get_indian_market_data(signal.symbol)
                if df is not None and not df.empty and len(df) > self.trend_ema_period:
                    col = 'close' if 'close' in df.columns else 'Close'
                    closes = df[col].values
                    weights = np.exp(np.linspace(-1., 0., self.trend_ema_period))
                    weights /= weights.sum()
                    ema50 = np.dot(weights, closes[-self.trend_ema_period:])
                    current = closes[-1]
                    if signal.signal_type == 'BUY' and current < ema50 * 0.98:
                        logger.info(f"⏭️ Skipping {signal.symbol} BUY: price {current:.2f} below 50-EMA {ema50:.2f}")
                        return
                    if signal.signal_type == 'SELL' and current > ema50 * 1.02:
                        logger.info(f"⏭️ Skipping {signal.symbol} SELL: price {current:.2f} above 50-EMA {ema50:.2f}")
                        return
            except Exception:
                pass  # non-critical filter

            # VOLATILITY FILTER — skip if ATR % is too low (not enough movement)
            atr_pct = self._get_atr_pct(signal.symbol)
            if atr_pct < self.min_volatility_pct:
                logger.info(f"⏭️ Skipping {signal.symbol}: ATR {atr_pct:.3%} below minimum {self.min_volatility_pct:.3%}")
                return

            # CORRELATION CHECK — avoid over-concentration in one sector
            if not self._check_correlation(signal.symbol):
                return

            # Prevent duplicate trades for the same symbol (in-memory + DB double check)
            with self._lock:
                for existing in self.active_trades.values():
                    if existing['symbol'] == signal.symbol:
                        logger.debug(f"Skipping duplicate trade for {signal.symbol} — already active")
                        return
            try:
                conn = sqlite3.connect(self.trading_system.db_path)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM active_trades WHERE symbol=?", (signal.symbol,))
                if cur.fetchone()[0] > 0:
                    logger.debug(f"Skipping duplicate trade for {signal.symbol} — already in DB")
                    conn.close()
                    return
                conn.close()
            except Exception:
                pass

            # PILLAR 5: Gemini AI validation removed — was advisory only and wasted 5-10s per trade

            # PILLAR 6: Record direction for no-reentry tracking
            clean_sym = signal.symbol.replace('.NS', '').replace('.BO', '').upper()
            direction_key = (clean_sym, signal.signal_type)
            self.daily_direction_tracker[direction_key] = datetime.now().strftime('%Y-%m-%d')

            # Calculate dynamic quantity based on capital allocation (split balance across max concurrent trades)
            try:
                current_balance = (self.initial_balance + self.total_pnl) * self.capital_utilization_pct
                # Subtract already-locked margin from available capital to prevent over-allocation
                locked_margin = sum(
                    t.get('entry_price', 0) * t.get('quantity', 0)
                    for t in self.active_trades.values()
                )
                available_capital = max(0, current_balance - locked_margin)
                remaining_slots = max(self.max_concurrent_trades - len(self.active_trades), 1)
                allocated_capital = available_capital / remaining_slots
                if allocated_capital <= 0:
                    logger.warning(f"Zero/negative available capital ({allocated_capital:.2f}), skipping trade")
                    return
                base_quantity = int(allocated_capital / signal.entry_price)
                # Confidence-weighted sizing: 0.5x at 40% to 1.5x at 90%+ confidence
                confidence_mult = min(1.5, max(0.5, signal.confidence / 0.80))
                # Drawdown streak protection: halve size after 3 consecutive losses, no win boost
                streak_mult = 0.5 if self.consecutive_losses >= 3 else 1.0
                trade_qty = max(1, int(base_quantity * confidence_mult * streak_mult))
                logger.info(f"📊 Sizing: base={base_quantity} × conf={confidence_mult:.2f} × streak={streak_mult:.2f} = {trade_qty} qty")
            except Exception as e:
                logger.warning(f"Error calculating dynamic quantity: {e} — falling back to default quantity")
                trade_qty = self.default_quantity

            # Execute Live Order (only real broker in LIVE mode)
            if self.trading_system.is_live() and self.trading_system.angel_one and self.trading_system.angel_one.is_connected:
                order_response = self.trading_system.angel_one.place_order(
                    symbol=signal.symbol,
                    quantity=trade_qty,
                    order_type=signal.signal_type,
                    product_type="INTRADAY",
                    price=signal.entry_price
                )
                if not order_response.get("status"):
                    logger.error(f"Broker order failed for {signal.symbol}: {order_response.get('error')}")
                    return
                else:
                    logger.info(f"Broker order successful: {order_response.get('data', {}).get('orderid')}")
            else:
                logger.info(f"SIMULATED entry: {signal.signal_type} {signal.symbol} qty={trade_qty} @ {signal.entry_price}")

            trade_id = f"indian_{signal.symbol}_{int(time.time())}"
            entry_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Create trade record
            trade = {
                'id': trade_id,
                'symbol': signal.symbol,
                'type': signal.signal_type,
                'entry_price': signal.entry_price,
                'target_price': signal.target_price,
                'stop_loss': signal.stop_loss,
                'initial_stop_loss': signal.stop_loss,
                'quantity': trade_qty,
                'strategy': signal.strategy,
                'confidence': signal.confidence,
                'timestamp': entry_time_str,
                # Track entry times for duration-based exits
                'entry_epoch': time.time(),
                'entry_time': entry_time_str,
                'status': 'ACTIVE'
            }
            
            with self._lock:
                self.active_trades[trade_id] = trade
            logger.info(f"✅ TRADE EXECUTED: {trade_id} - {signal.symbol} {signal.signal_type} @ {signal.entry_price}")
            logger.info(f"   Target: {signal.target_price}, Stop Loss: {signal.stop_loss}")

            # Seed latest_prices with a fresh price to prevent stale-price exits
            try:
                fresh_data = self.trading_system.get_indian_market_data(signal.symbol, period='1d')
                if fresh_data is not None and not fresh_data.empty:
                    fresh_price = float(fresh_data['Close'].iloc[-1])
                    with self._lock:
                        self.latest_prices[signal.symbol] = fresh_price
                    logger.info(f"Seeded latest_prices[{signal.symbol}] = {fresh_price}")
            except Exception:
                pass

            # Log entry activity
            try:
                self.trading_system.log_activity(
                    f'ENTRY({signal.signal_type})', signal.symbol,
                    signal.entry_price, 0, trade_qty,
                    0, self.initial_balance + self.total_pnl,
                    signal.strategy
                )
            except Exception:
                pass
            
            # Persist active trade to DB for resilience
            try:
                conn = sqlite3.connect(self.trading_system.db_path)
                cur = conn.cursor()
                cur.execute('''
                    INSERT OR REPLACE INTO active_trades(id, symbol, type, entry_price, quantity, entry_time, user_id, strategy, confidence, stop_loss, target_price)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    trade_id,
                    signal.symbol,
                    signal.signal_type,
                    float(signal.entry_price),
                    int(trade_qty),
                    trade['entry_time'],
                    int(self.user_id),
                    signal.strategy,
                    float(signal.confidence),
                    float(signal.stop_loss),
                    float(signal.target_price)
                ))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to persist active trade {trade_id}: {e}")

        except Exception as e:
            logger.error(f"❌ Error executing trade: {str(e)}")
    
    def _monitor_trades(self):
        """Monitor and manage active trades"""
        try:
            for trade_id, trade in list(self.active_trades.items()):
                current_price = self.latest_prices.get(trade['symbol'])
                
                # Validate WebSocket price before using it
                if current_price:
                    entry = trade.get('entry_price', 0)
                    if entry > 0 and abs(current_price - entry) / entry > 0.50:
                        logger.warning(f"WebSocket price {current_price} for {trade['symbol']} too far from entry {entry}, fetching fresh price")
                        current_price = None  # Force fallback
                
                if not current_price:
                    # Fallback to API if WebSocket hasn't pushed a price yet or price is bad
                    data = self.trading_system.get_indian_market_data(trade['symbol'], period='1d')
                    if data is not None and not data.empty:
                        current_price = float(data['Close'].iloc[-1])
                        # Validate fallback price too
                        if self.trading_system.validate_price(trade['symbol'], current_price):
                            self.latest_prices[trade['symbol']] = current_price
                        else:
                            continue  # Skip this cycle, price data unreliable
                
                if current_price:
                    self._evaluate_trade_exit(trade_id, trade, current_price)
                    
        except Exception as e:
            logger.error(f"Error monitoring trades: {str(e)}")
    
    def _close_trade(self, trade_id: str, reason: str, exit_price: float):
        """Close a trade"""
        try:
            # Minimize lock section: only in-memory state mutations need the lock
            with self._lock:
                if trade_id not in self.active_trades:
                    return
                trade = self.active_trades[trade_id]
            logger.info(f"Closing trade {trade_id}: {reason}")

            # Place closing order (only real broker in LIVE mode) — outside lock
            if self.trading_system.is_live() and self.trading_system.angel_one and self.trading_system.angel_one.is_connected:
                close_type = "SELL" if trade['type'] == "BUY" else "BUY"
                order_response = self.trading_system.angel_one.place_order(
                    symbol=trade['symbol'],
                    quantity=trade.get('quantity', self.default_quantity),
                    order_type=close_type,
                    product_type="INTRADAY",
                    price=exit_price
                )
                if not order_response.get("status"):
                    logger.error(f"Failed to close broker order for {trade['symbol']}: {order_response.get('error')}")
            else:
                logger.info(f"SIMULATED close: {trade['symbol']} {trade['type']} qty={trade.get('quantity', self.default_quantity)} @ {exit_price}")

            # Calculate absolute P&L amount
            quantity = trade.get('quantity', self.default_quantity)
            entry_price = trade['entry_price']
            if trade['type'] == 'BUY':
                pnl_amount = (exit_price - entry_price) * quantity
            else:
                pnl_amount = (entry_price - exit_price) * quantity

            logger.info(f"Trade {trade_id} P&L amount: {pnl_amount:.2f}")

            # In-memory state mutations under lock (fast)
            with self._lock:
                clean_sym = trade['symbol'].replace('.NS', '').replace('.BO', '').upper()
                self.symbol_cooldown[clean_sym] = time.time()
                self.signal_confirm_cache.pop(clean_sym, None)

                self.total_pnl += pnl_amount
                self.daily_pnl += pnl_amount
                if pnl_amount > 0:
                    self.consecutive_wins += 1
                    self.consecutive_losses = 0
                else:
                    self.consecutive_losses += 1
                    self.consecutive_wins = 0
                logger.info(f"Streak: {self.consecutive_wins}W / {self.consecutive_losses}L")
                closed_trade = {
                    'id': trade_id,
                    'symbol': trade['symbol'],
                    'type': trade['type'],
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'quantity': quantity,
                    'reason': reason,
                    'pnl_amount': pnl_amount,
                    'exit_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                self.trade_history.append(closed_trade)
                self.active_trades.pop(trade_id, None)

            # DB and network operations — outside lock
            try:
                conn = sqlite3.connect(self.trading_system.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO trades (user_id, symbol, direction, entry_price, exit_price, quantity, status, entry_time, exit_time, profit_loss)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    self.user_id,
                    trade['symbol'],
                    trade['type'],
                    float(entry_price),
                    float(exit_price),
                    float(quantity),
                    'CLOSED',
                    trade['timestamp'],
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    float(pnl_amount)
                ))
                cursor.execute('''
                    SELECT portfolio_value FROM portfolio_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1
                ''', (self.user_id,))
                row = cursor.fetchone()
                last_value = float(row[0]) if row else float(self.initial_balance)
                new_value = last_value + float(pnl_amount)
                cursor.execute('''
                    INSERT INTO portfolio_history (user_id, portfolio_value, timestamp)
                    VALUES (?, ?, ?)
                ''', (self.user_id, new_value, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                try:
                    cursor.execute('DELETE FROM active_trades WHERE id=?', (trade_id,))
                except Exception:
                    pass
                conn.commit()
                conn.close()
            except Exception as db_err:
                logger.error(f"Error updating portfolio/trades in DB: {db_err}")

            try:
                self.trading_system.log_activity(
                    f'CLOSE({reason})', trade['symbol'],
                    entry_price, exit_price, quantity,
                    pnl_amount, self.initial_balance + self.total_pnl,
                    trade.get('strategy', 'Auto')
                )
            except Exception:
                pass

            try:
                from app import socketio
                socketio.emit('trade_closed', {
                    'trade_id': trade_id,
                    'symbol': trade['symbol'],
                    'reason': reason,
                    'pnl': float(pnl_amount)
                })
            except Exception as emit_err:
                pass
                
        except Exception as e:
            logger.error(f"Error closing trade: {str(e)}")
    
    def get_active_trades(self) -> Dict:
        """Get all active trades"""
        return self.active_trades.copy()
    
    def get_performance_summary(self) -> Dict:
        """Get trading performance summary"""
        try:
            total_trades = len(self.trade_history) if hasattr(self, 'trade_history') else 0
            active_trades = len(self.active_trades)
            
            # Check if thread is actually alive
            thread_alive = self.trading_thread and self.trading_thread.is_alive() if hasattr(self, 'trading_thread') else False
            
            if self.running and thread_alive:
                if self.trading_system.is_market_open():
                    actual_status = 'Running'
                else:
                    try:
                        import pytz
                        ist = pytz.timezone('Asia/Kolkata')
                        now = datetime.now(ist)
                        today = now.date()
                        if now.weekday() >= 5:
                            actual_status = 'Closed (Weekend)'
                        elif today in self.trading_system.get_nse_holidays(now.year):
                            actual_status = 'Paused (Holiday)'
                        else:
                            actual_status = 'Sleeping (Market Closed)'
                    except Exception:
                        actual_status = 'Running (Market Closed)'
            else:
                actual_status = 'Stopped'
            
            # Calculate P&L metrics
            total_pnl = getattr(self, 'total_pnl', 0.0)
            
            # Calculate win rate
            win_rate = 0.0
            if hasattr(self, 'trade_history') and self.trade_history:
                wins = sum(1 for t in self.trade_history if t.get('pnl_amount', 0) > 0)
                win_rate = (wins / len(self.trade_history)) * 100.0 if self.trade_history else 0.0
            
            return {
                'total_trades': total_trades,
                'active_trades': active_trades,
                'status': actual_status,
                'thread_alive': thread_alive,
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_rate, 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting performance summary: {str(e)}")
            return {}
