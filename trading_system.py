import pandas as pd
import numpy as np
import yfinance as yf
import time
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple
from angel_one_api import AngelOneAPI, AngelOneDataProvider
from cache_manager import cache_manager
from rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

class TradingSystem:
    def __init__(self, angel_one_client=None):
        self.strategies = {
            'rsi': self.rsi_strategy,
            'macd': self.macd_strategy,
            'bollinger': self.bollinger_strategy,
            'moving_average': self.moving_average_strategy
        }
        self.timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        self.cache = {}
        self.cache_duration = timedelta(minutes=5)
        
        # Initialize Angel One integration
        if angel_one_client:
            self.angel_one = angel_one_client
            self.data_provider = AngelOneDataProvider(angel_one_client)
        else:
            # Disable mock; require Angel One configuration first
            self.angel_one = None
            self.data_provider = None

    def analyze_market(self, symbol: str, interval: str = '1d') -> Dict:
        """Analyze market data and generate trading signals"""
        try:
            # Get historical data
            data = self.get_historical_data(symbol, interval=interval)
            if data is None or data.empty:
                logger.error(f"No data available for {symbol}")
                return {
                    'symbol': symbol,
                    'signal': 'NEUTRAL',
                    'confidence': 0.0,
                    'indicators': {},
                    'timestamp': datetime.now().isoformat()
                }

            # Calculate indicators
            indicators = self.calculate_indicators(data)
            if not indicators:
                logger.error(f"Failed to calculate indicators for {symbol}")
                return {
                    'symbol': symbol,
                    'signal': 'NEUTRAL',
                    'confidence': 0.0,
                    'indicators': {},
                    'timestamp': datetime.now().isoformat()
                }

            # Generate signals from each strategy
            signals = []
            confidences = []

            # RSI Strategy
            rsi_signal, rsi_conf = self.rsi_strategy(indicators['rsi'])
            signals.append(rsi_signal)
            confidences.append(rsi_conf)

            # MACD Strategy
            macd_signal, macd_conf = self.macd_strategy(
                indicators['macd'],
                indicators['macd_signal']
            )
            signals.append(macd_signal)
            confidences.append(macd_conf)

            # Bollinger Bands Strategy
            bb_signal, bb_conf = self.bollinger_strategy(
                data['Close'].iloc[-1],
                indicators['bb_upper'],
                indicators['bb_lower']
            )
            signals.append(bb_signal)
            confidences.append(bb_conf)

            # Moving Average Strategy
            ma_signal, ma_conf = self.moving_average_strategy(
                data['Close'].iloc[-1],
                indicators['sma_20'],
                indicators['sma_50']
            )
            signals.append(ma_signal)
            confidences.append(ma_conf)

            # Combine signals
            final_signal, confidence = self.combine_signals(signals, confidences)

            return {
                'symbol': symbol,
                'signal': final_signal,
                'confidence': confidence,
                'indicators': indicators,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error analyzing market for {symbol}: {str(e)}")
            return {
                'symbol': symbol,
                'signal': 'NEUTRAL',
                'confidence': 0.0,
                'indicators': {},
                'timestamp': datetime.now().isoformat()
            }

    def get_historical_data(self, symbol: str, interval: str = '1d', period: str = '1y') -> Optional[pd.DataFrame]:
        """Get historical data using Angel One API only (no fallback)"""
        try:
            # Check cache first using the new cache manager
            cache_key = f"market_data_{symbol}_{interval}_{period}"
            cached_data = cache_manager.get(cache_key)
            
            if cached_data is not None:
                logger.debug(f"Cache hit for {symbol} - returning cached data")
                return cached_data
            
            if not self.data_provider:
                logger.error("Angel One data provider unavailable. Configure Angel One first.")
                return pd.DataFrame()

            try:
                data = self.data_provider.get_historical_data(symbol, interval, period)
                if not data.empty:
                    cache_manager.set(cache_key, data)
                    logger.debug(f"Data cached for {symbol}")
                    return data
            except Exception as e:
                logger.warning(f"Angel One API failed for {symbol}: {str(e)}")

            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
            return pd.DataFrame()
    
    def _is_indian_symbol(self, symbol: str) -> bool:
        """Check if symbol is an Indian market symbol"""
        indian_symbols = [
            'NIFTY50', 'BANKNIFTY', 'SENSEX', 'RELIANCE', 'TCS', 'HDFCBANK', 
            'INFY', 'ICICIBANK', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 
            'BAJFINANCE', 'HINDUNILVR'
        ]
        clean_symbol = symbol.replace('.NS', '')
        return clean_symbol in indian_symbols
    
    # yfinance fallback disabled

    # mock generation disabled

    def _get_symbol_characteristics(self, symbol: str) -> Tuple[float, float, float]:
        """Get realistic characteristics for different symbols"""
        characteristics = {
            # US Stocks
            'AAPL': (150.0, 0.025, 0.001),  # price, volatility, spread
            'SPY': (400.0, 0.015, 0.0005),
            'QQQ': (350.0, 0.020, 0.0005),
            'TSLA': (200.0, 0.040, 0.002),
            'MSFT': (300.0, 0.022, 0.001),
            'GOOGL': (120.0, 0.025, 0.001),
            'AMZN': (130.0, 0.030, 0.001),
            'META': (250.0, 0.035, 0.001),
            'NVDA': (400.0, 0.045, 0.002),
            'JPM': (150.0, 0.020, 0.001),
            'V': (250.0, 0.018, 0.001),
            
            # Commodities
            'GOLD': (2000.0, 0.015, 0.0005),
            'GC=F': (2000.0, 0.015, 0.0005),
            'OIL': (80.0, 0.030, 0.001),
            'CL=F': (80.0, 0.030, 0.001),
            
            # Forex
            'EURUSD': (1.08, 0.008, 0.0001),
            'GBPUSD': (1.25, 0.010, 0.0001),
            'USDJPY': (150.0, 0.012, 0.0001),
            
            # Indian Markets
            'NIFTY50': (19500.0, 0.020, 0.0005),
            'BANKNIFTY': (44500.0, 0.025, 0.0005),
            'SENSEX': (65000.0, 0.018, 0.0005),
            'RELIANCE': (2500.0, 0.025, 0.001),
            'TCS': (3800.0, 0.020, 0.001),
            'HDFCBANK': (1650.0, 0.022, 0.001),
            'INFY': (1500.0, 0.018, 0.001),
            'ICICIBANK': (950.0, 0.025, 0.001),
            'SBIN': (650.0, 0.030, 0.001),
            'BHARTIARTL': (950.0, 0.025, 0.001),
            'KOTAKBANK': (1850.0, 0.020, 0.001),
            'BAJFINANCE': (7500.0, 0.035, 0.002),
            'HINDUNILVR': (2500.0, 0.015, 0.001)
        }
        
        return characteristics.get(symbol, (100.0, 0.020, 0.001))  # Default values

    def calculate_indicators(self, data: pd.DataFrame) -> Dict:
        """Calculate comprehensive technical indicators"""
        try:
            if data.empty or len(data) < 20:  # Need minimum data for calculations
                return None

            close_prices = data['Close']
            high_prices = data['High']
            low_prices = data['Low']
            volume = data['Volume']

            # RSI (Relative Strength Index)
            delta = close_prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # MACD (Moving Average Convergence Divergence)
            exp1 = close_prices.ewm(span=12, adjust=False).mean()
            exp2 = close_prices.ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            macd_signal = macd.ewm(span=9, adjust=False).mean()
            macd_histogram = macd - macd_signal

            # Bollinger Bands
            sma_20 = close_prices.rolling(window=20).mean()
            std_20 = close_prices.rolling(window=20).std()
            bb_upper = sma_20 + (std_20 * 2)
            bb_lower = sma_20 - (std_20 * 2)
            bb_middle = sma_20
            bb_width = (bb_upper - bb_lower) / bb_middle

            # Moving Averages
            sma_5 = close_prices.rolling(window=5).mean()
            sma_10 = close_prices.rolling(window=10).mean()
            sma_20 = close_prices.rolling(window=20).mean()
            sma_50 = close_prices.rolling(window=50).mean()
            sma_200 = close_prices.rolling(window=200).mean()

            # Exponential Moving Averages
            ema_12 = close_prices.ewm(span=12, adjust=False).mean()
            ema_26 = close_prices.ewm(span=26, adjust=False).mean()
            ema_50 = close_prices.ewm(span=50, adjust=False).mean()

            # Stochastic Oscillator
            lowest_low = low_prices.rolling(window=14).min()
            highest_high = high_prices.rolling(window=14).max()
            k_percent = 100 * ((close_prices - lowest_low) / (highest_high - lowest_low))
            d_percent = k_percent.rolling(window=3).mean()

            # Williams %R
            williams_r = -100 * ((highest_high - close_prices) / (highest_high - lowest_low))

            # Average True Range (ATR)
            tr1 = high_prices - low_prices
            tr2 = abs(high_prices - close_prices.shift(1))
            tr3 = abs(low_prices - close_prices.shift(1))
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = true_range.rolling(window=14).mean()

            # Volume indicators
            volume_sma = volume.rolling(window=20).mean()
            volume_ratio = volume / volume_sma
            price_volume_trend = (close_prices.diff() * volume).cumsum()

            # Support and Resistance levels
            support_levels = self._find_support_resistance_levels(close_prices, 'support')
            resistance_levels = self._find_support_resistance_levels(close_prices, 'resistance')

            # Volatility indicators
            volatility = close_prices.pct_change().rolling(window=20).std()
            vix_equivalent = volatility * 100 * np.sqrt(252)  # Annualized volatility

            return {
                # Momentum indicators
                'rsi': rsi.iloc[-1] if not rsi.empty else 50,
                'stochastic_k': k_percent.iloc[-1] if not k_percent.empty else 50,
                'stochastic_d': d_percent.iloc[-1] if not d_percent.empty else 50,
                'williams_r': williams_r.iloc[-1] if not williams_r.empty else -50,
                
                # Trend indicators
                'macd': macd.iloc[-1] if not macd.empty else 0,
                'macd_signal': macd_signal.iloc[-1] if not macd_signal.empty else 0,
                'macd_histogram': macd_histogram.iloc[-1] if not macd_histogram.empty else 0,
                
                # Moving averages
                'sma_5': sma_5.iloc[-1] if not sma_5.empty else close_prices.iloc[-1],
                'sma_10': sma_10.iloc[-1] if not sma_10.empty else close_prices.iloc[-1],
                'sma_20': sma_20.iloc[-1] if not sma_20.empty else close_prices.iloc[-1],
                'sma_50': sma_50.iloc[-1] if not sma_50.empty else close_prices.iloc[-1],
                'sma_200': sma_200.iloc[-1] if not sma_200.empty else close_prices.iloc[-1],
                'ema_12': ema_12.iloc[-1] if not ema_12.empty else close_prices.iloc[-1],
                'ema_26': ema_26.iloc[-1] if not ema_26.empty else close_prices.iloc[-1],
                'ema_50': ema_50.iloc[-1] if not ema_50.empty else close_prices.iloc[-1],
                
                # Bollinger Bands
                'bb_upper': bb_upper.iloc[-1] if not bb_upper.empty else close_prices.iloc[-1],
                'bb_middle': bb_middle.iloc[-1] if not bb_middle.empty else close_prices.iloc[-1],
                'bb_lower': bb_lower.iloc[-1] if not bb_lower.empty else close_prices.iloc[-1],
                'bb_width': bb_width.iloc[-1] if not bb_width.empty else 0,
                
                # Volatility
                'atr': atr.iloc[-1] if not atr.empty else 0,
                'volatility': volatility.iloc[-1] if not volatility.empty else 0,
                'vix_equivalent': vix_equivalent.iloc[-1] if not vix_equivalent.empty else 0,
                
                # Volume
                'volume_ratio': volume_ratio.iloc[-1] if not volume_ratio.empty else 1,
                'price_volume_trend': price_volume_trend.iloc[-1] if not price_volume_trend.empty else 0,
                
                # Support/Resistance
                'support_levels': support_levels,
                'resistance_levels': resistance_levels,
                
                # Current price
                'current_price': close_prices.iloc[-1]
            }
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return None

    def _find_support_resistance_levels(self, prices: pd.Series, level_type: str = 'support') -> List[float]:
        """Find support and resistance levels using pivot points"""
        try:
            if len(prices) < 20:
                return []
            
            levels = []
            window = 5
            
            for i in range(window, len(prices) - window):
                if level_type == 'support':
                    # Check if current price is a local minimum
                    if prices.iloc[i] == prices.iloc[i-window:i+window+1].min():
                        levels.append(prices.iloc[i])
                else:  # resistance
                    # Check if current price is a local maximum
                    if prices.iloc[i] == prices.iloc[i-window:i+window+1].max():
                        levels.append(prices.iloc[i])
            
            # Return the most recent and significant levels
            if level_type == 'support':
                levels = sorted(levels)[-3:]  # Top 3 support levels
            else:
                levels = sorted(levels, reverse=True)[-3:]  # Top 3 resistance levels
            
            return levels
            
        except Exception as e:
            logger.error(f"Error finding {level_type} levels: {str(e)}")
            return []

    def rsi_strategy(self, rsi: float) -> Tuple[str, float]:
        """RSI-based trading strategy"""
        try:
            if rsi > 70:
                return 'SELL', min((rsi - 70) / 30, 1.0)
            elif rsi < 30:
                return 'BUY', min((30 - rsi) / 30, 1.0)
            return 'NEUTRAL', 0.0
        except Exception as e:
            logger.error(f"Error in RSI strategy: {str(e)}")
            return 'NEUTRAL', 0.0

    def macd_strategy(self, macd: float, signal: float) -> Tuple[str, float]:
        """MACD-based trading strategy"""
        try:
            if macd > signal:
                return 'BUY', min(abs(macd - signal) / abs(signal), 1.0)
            elif macd < signal:
                return 'SELL', min(abs(macd - signal) / abs(signal), 1.0)
            return 'NEUTRAL', 0.0
        except Exception as e:
            logger.error(f"Error in MACD strategy: {str(e)}")
            return 'NEUTRAL', 0.0

    def bollinger_strategy(self, price: float, upper: float, lower: float) -> Tuple[str, float]:
        """Bollinger Bands-based trading strategy"""
        try:
            if price > upper:
                return 'SELL', min((price - upper) / upper, 1.0)
            elif price < lower:
                return 'BUY', min((lower - price) / lower, 1.0)
            return 'NEUTRAL', 0.0
        except Exception as e:
            logger.error(f"Error in Bollinger Bands strategy: {str(e)}")
            return 'NEUTRAL', 0.0

    def moving_average_strategy(self, price: float, sma_20: float, sma_50: float) -> Tuple[str, float]:
        """Moving Average-based trading strategy"""
        try:
            if price > sma_20 and sma_20 > sma_50:
                return 'BUY', min((price - sma_20) / sma_20, 1.0)
            elif price < sma_20 and sma_20 < sma_50:
                return 'SELL', min((sma_20 - price) / sma_20, 1.0)
            return 'NEUTRAL', 0.0
        except Exception as e:
            logger.error(f"Error in Moving Average strategy: {str(e)}")
            return 'NEUTRAL', 0.0

    def combine_signals(self, signals: List[str], confidences: List[float]) -> Tuple[str, float]:
        """Combine signals from different strategies"""
        try:
            if not signals or not confidences:
                return 'NEUTRAL', 0.0

            # Count signals
            buy_count = signals.count('BUY')
            sell_count = signals.count('SELL')
            neutral_count = signals.count('NEUTRAL')

            # Calculate weighted confidence
            total_confidence = sum(confidences)
            if total_confidence == 0:
                return 'NEUTRAL', 0.0

            # Determine final signal
            if buy_count > sell_count and buy_count > neutral_count:
                return 'BUY', total_confidence / len(signals)
            elif sell_count > buy_count and sell_count > neutral_count:
                return 'SELL', total_confidence / len(signals)
            return 'NEUTRAL', 0.0
        except Exception as e:
            logger.error(f"Error combining signals: {str(e)}")
            return 'NEUTRAL', 0.0

    def calculate_risk_metrics(self, trades: List[Dict]) -> Dict:
        """Calculate risk metrics for trading performance"""
        try:
            if not trades:
                return {
                    'win_rate': 0,
                    'profit_factor': 0,
                    'average_win': 0,
                    'average_loss': 0,
                    'max_drawdown': 0,
                    'sharpe_ratio': 0
                }
                
            # Calculate basic metrics
            winning_trades = [t for t in trades if t.get('profit', 0) > 0]
            losing_trades = [t for t in trades if t.get('profit', 0) < 0]
            
            win_rate = len(winning_trades) / len(trades) if trades else 0
            
            total_profit = sum(t.get('profit', 0) for t in winning_trades)
            total_loss = abs(sum(t.get('profit', 0) for t in losing_trades))
            
            profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
            
            average_win = total_profit / len(winning_trades) if winning_trades else 0
            average_loss = total_loss / len(losing_trades) if losing_trades else 0
            
            # Calculate drawdown
            cumulative_returns = np.cumsum([t.get('profit', 0) for t in trades])
            max_drawdown = 0
            peak = cumulative_returns[0]
            
            for value in cumulative_returns:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak if peak > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)
                
            # Calculate Sharpe ratio (assuming risk-free rate of 0)
            returns = np.array([t.get('profit', 0) for t in trades])
            sharpe_ratio = np.mean(returns) / np.std(returns) if len(returns) > 1 and np.std(returns) > 0 else 0
            
            return {
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'average_win': average_win,
                'average_loss': average_loss,
                'max_drawdown': max_drawdown,
                'sharpe_ratio': sharpe_ratio
            }
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {str(e)}")
            return {}

    def get_trading_signals(self, symbol: str, interval: str = '1d') -> Dict:
        """Get trading signals for a symbol"""
        try:
            # Get historical data
            data = self.get_historical_data(symbol, interval=interval)
            if data is None or data.empty:
                logger.error(f"No data available for {symbol}")
                return None

            # Calculate indicators
            indicators = self.calculate_indicators(data)
            if not indicators:
                logger.error(f"Failed to calculate indicators for {symbol}")
                return None

            # Generate signals from each strategy
            signals = []
            confidences = []

            # RSI Strategy
            rsi_signal, rsi_conf = self.rsi_strategy(indicators['rsi'])
            signals.append(rsi_signal)
            confidences.append(rsi_conf)

            # MACD Strategy
            macd_signal, macd_conf = self.macd_strategy(
                indicators['macd'],
                indicators['macd_signal']
            )
            signals.append(macd_signal)
            confidences.append(macd_conf)

            # Bollinger Bands Strategy
            bb_signal, bb_conf = self.bollinger_strategy(
                data['Close'].iloc[-1],
                indicators['bb_upper'],
                indicators['bb_lower']
            )
            signals.append(bb_signal)
            confidences.append(bb_conf)

            # Moving Average Strategy
            ma_signal, ma_conf = self.moving_average_strategy(
                data['Close'].iloc[-1],
                indicators['sma_20'],
                indicators['sma_50']
            )
            signals.append(ma_signal)
            confidences.append(ma_conf)

            # Combine signals
            final_signal, confidence = self.combine_signals(signals, confidences)

            return {
                'symbol': symbol,
                'type': final_signal,
                'confidence': round(confidence * 100, 2),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting trading signals for {symbol}: {str(e)}")
            return None