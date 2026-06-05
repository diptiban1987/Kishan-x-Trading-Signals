from typing import Dict, List, Optional, Tuple
import numpy as np
import logging
import os
from datetime import datetime, timedelta
import sqlite3
import pandas as pd
from angel_one_api import AngelOneAPI, AngelOneDataProvider

logger = logging.getLogger(__name__)

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

class RiskManager:
    def __init__(self, db_path: str = None, angel_one_client=None):
        self.db_path = db_path if db_path is not None else _get_db_path()
        self.max_position_size = 0.02  # 2% of portfolio per trade
        self.max_daily_loss = 0.05    # 5% of portfolio per day
        self.max_drawdown = 0.15      # 15% maximum drawdown
        self.stop_loss_pct = 0.02     # 2% stop loss
        self.take_profit_pct = 0.04   # 4% take profit
        self.max_concurrent_trades = 5  # Maximum concurrent positions
        self.correlation_threshold = 0.7  # Maximum correlation between positions
        self.volatility_adjustment = True  # Adjust position size based on volatility
        self.sector_exposure_limit = 0.3  # Maximum 30% exposure to any sector
        
        # Initialize Angel One integration
        if angel_one_client:
            self.angel_one = angel_one_client
            self.data_provider = AngelOneDataProvider(angel_one_client)
        else:
            # Disable mock; require Angel One configuration first
            self.angel_one = None
            self.data_provider = None

    def check_risk_limits(self, user_id: int, symbol: str, quantity: float) -> Tuple[bool, str]:
        """Enhanced risk management with multiple checks"""
        try:
            # Get user's portfolio value
            portfolio_value = self.get_portfolio_value(user_id)
            if portfolio_value is None:
                return False, "Could not retrieve portfolio value"

            # Get current position size
            position_size = self.get_position_size(user_id, symbol)
            
            # Calculate new position value
            current_price_data = self.get_current_price(symbol)
            if current_price_data is None:
                return False, "Could not retrieve current price"
            
            current_price = current_price_data['price']
            new_position_value = current_price * quantity
            
            # Check position size limit
            if new_position_value > portfolio_value * self.max_position_size:
                return False, f"Position size exceeds {self.max_position_size * 100}% of portfolio"

            # Check concurrent trades limit
            active_trades = self.get_active_trades_count(user_id)
            if active_trades >= self.max_concurrent_trades:
                return False, f"Maximum concurrent trades limit ({self.max_concurrent_trades}) reached"

            # Check daily loss limit
            daily_pnl = self.get_daily_pnl(user_id)
            if daily_pnl < -portfolio_value * self.max_daily_loss:
                return False, f"Daily loss limit of {self.max_daily_loss * 100}% reached"

            # Check drawdown limit
            drawdown = self.calculate_drawdown(user_id)
            if drawdown > self.max_drawdown:
                return False, f"Maximum drawdown of {self.max_drawdown * 100}% reached"

            # Check sector exposure
            sector_exposure = self.get_sector_exposure(user_id, symbol)
            if sector_exposure > self.sector_exposure_limit:
                return False, f"Sector exposure limit of {self.sector_exposure_limit * 100}% reached"

            # Check correlation with existing positions
            correlation_risk = self.check_correlation_risk(user_id, symbol)
            if correlation_risk:
                return False, f"High correlation with existing positions"

            return True, "Risk checks passed"
        except Exception as e:
            logger.error(f"Error checking risk limits: {str(e)}")
            return False, str(e)

    def calculate_position_size(self, user_id: int, symbol: str, risk_per_trade: float = 0.02) -> Optional[float]:
        """Calculate optimal position size based on risk parameters"""
        try:
            # Get portfolio value
            portfolio_value = self.get_portfolio_value(user_id)
            if portfolio_value is None:
                return None

            # Get current price and volatility
            current_price_data = self.get_current_price(symbol)
            volatility = self.calculate_volatility(symbol)
            
            if current_price_data is None or volatility is None:
                return None

            current_price = current_price_data['price']
            # Calculate position size based on risk
            risk_amount = portfolio_value * risk_per_trade
            position_size = risk_amount / (current_price * volatility)
            
            return position_size
        except Exception as e:
            logger.error(f"Error calculating position size: {str(e)}")
            return None

    def get_portfolio_value(self, user_id: int) -> Optional[float]:
        """Get user's current portfolio value"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get cash balance
            cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
            cash_balance = cursor.fetchone()[0]
            
            # Get value of all positions
            cursor.execute('''
                SELECT symbol, quantity, current_price 
                FROM positions 
                WHERE user_id = ?
            ''', (user_id,))
            positions = cursor.fetchall()
            
            position_value = sum(quantity * price for _, quantity, price in positions)
            
            return cash_balance + position_value
        except Exception as e:
            logger.error(f"Error getting portfolio value: {str(e)}")
            return None
        finally:
            if conn:
                conn.close()

    def get_position_size(self, user_id: int, symbol: str) -> float:
        """Get current position size for symbol"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT quantity 
                FROM positions 
                WHERE user_id = ? AND symbol = ?
            ''', (user_id, symbol))
            
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting position size: {str(e)}")
            return 0
        finally:
            if conn:
                conn.close()

    def get_current_price(self, symbol: str) -> Optional[Dict]:
        """Get current price for symbol using Angel One API"""
        try:
            # Try Angel One API first for Indian symbols
            if self._is_indian_symbol(symbol):
                try:
                    price_data = self.data_provider.get_real_time_price(symbol)
                    if price_data and 'price' in price_data:
                        return price_data
                except Exception as e:
                    logger.warning(f"Angel One API failed for {symbol}: {str(e)}")
            
            # Try to get from database as fallback
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT close, timestamp 
                FROM market_data 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (symbol,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {'price': result[0], 'timestamp': result[1]}
            
            # No external fallback
            return None
            
        except Exception as e:
            logger.error(f"Error getting current price: {str(e)}")
            return None
    
    def _is_indian_symbol(self, symbol: str) -> bool:
        """Check if symbol is an Indian market symbol"""
        indian_symbols = [
            'NIFTY50', 'BANKNIFTY', 'SENSEX', 'RELIANCE', 'TCS', 'HDFCBANK', 
            'INFY', 'ICICIBANK', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 
            'BAJFINANCE', 'HINDUNILVR'
        ]
        clean_symbol = symbol.replace('.NS', '')
        return clean_symbol in indian_symbols

    def get_daily_pnl(self, user_id: int) -> float:
        """Get user's daily profit/loss"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            today = datetime.now().date()
            cursor.execute('''
                SELECT SUM(profit_loss) 
                FROM trades 
                WHERE user_id = ? 
                AND DATE(entry_time) = ?
            ''', (user_id, today))
            
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result[0] is not None else 0
        except Exception as e:
            logger.error(f"Error getting daily P&L: {str(e)}")
            return 0

    def calculate_drawdown(self, user_id: int) -> float:
        """Calculate current drawdown"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get portfolio value history
            cursor.execute('''
                SELECT portfolio_value, timestamp 
                FROM portfolio_history 
                WHERE user_id = ? 
                ORDER BY timestamp DESC
            ''', (user_id,))
            
            history = cursor.fetchall()
            conn.close()
            
            if not history:
                return 0
            
            # Calculate drawdown
            peak = max(value for value, _ in history)
            current = history[0][0]
            
            return (peak - current) / peak if peak > 0 else 0
        except Exception as e:
            logger.error(f"Error calculating drawdown: {str(e)}")
            return 0

    def calculate_volatility(self, symbol: str, window: int = 20) -> Optional[float]:
        """Calculate price volatility"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT close 
                FROM market_data 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (symbol, window))
            
            prices = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            if len(prices) < 2:
                return None
            
            returns = np.diff(np.log(prices))
            volatility = np.std(returns) * np.sqrt(252)  # Annualized volatility
            
            return volatility
        except Exception as e:
            logger.error(f"Error calculating volatility: {str(e)}")
            return None

    def update_risk_limits(self, user_id: int, limits: Dict) -> bool:
        """Update user's risk limits"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE risk_limits 
                SET max_position_size = ?,
                    max_daily_loss = ?,
                    max_drawdown = ?,
                    updated_at = ?
                WHERE user_id = ?
            ''', (
                limits.get('max_position_size', self.max_position_size),
                limits.get('max_daily_loss', self.max_daily_loss),
                limits.get('max_drawdown', self.max_drawdown),
                datetime.now().isoformat(),
                user_id
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error updating risk limits: {str(e)}")
            return False

    def get_risk_metrics(self, trades: List[Dict]) -> Dict:
        """Calculate risk metrics for trading performance"""
        try:
            if not trades:
                return {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0,
                    'average_win': 0,
                    'average_loss': 0,
                    'largest_win': 0,
                    'largest_loss': 0,
                    'profit_factor': 0,
                    'max_drawdown': 0
                }
                
            # Calculate basic metrics
            winning_trades = [t for t in trades if t.get('profit', 0) > 0]
            losing_trades = [t for t in trades if t.get('profit', 0) < 0]
            
            total_trades = len(trades)
            winning_trades_count = len(winning_trades)
            losing_trades_count = len(losing_trades)
            
            win_rate = winning_trades_count / total_trades if total_trades > 0 else 0
            
            # Calculate profit metrics
            total_profit = sum(t.get('profit', 0) for t in winning_trades)
            total_loss = abs(sum(t.get('profit', 0) for t in losing_trades))
            
            average_win = total_profit / winning_trades_count if winning_trades_count > 0 else 0
            average_loss = total_loss / losing_trades_count if losing_trades_count > 0 else 0
            
            largest_win = max((t.get('profit', 0) for t in winning_trades), default=0)
            largest_loss = min((t.get('profit', 0) for t in losing_trades), default=0)
            
            profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
            
            # Calculate drawdown
            cumulative_returns = np.cumsum([t.get('profit', 0) for t in trades])
            max_drawdown = 0
            peak = cumulative_returns[0]
            
            for value in cumulative_returns:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak if peak > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)
                
            return {
                'total_trades': total_trades,
                'winning_trades': winning_trades_count,
                'losing_trades': losing_trades_count,
                'win_rate': win_rate,
                'average_win': average_win,
                'average_loss': average_loss,
                'largest_win': largest_win,
                'largest_loss': largest_loss,
                'profit_factor': profit_factor,
                'max_drawdown': max_drawdown
            }
            
        except Exception as e:
            logger.error(f'Error calculating risk metrics: {str(e)}')
            return {} 

    def calculate_position_size(self, trade_data: dict) -> float:
        """Calculate position size based on risk parameters"""
        try:
            portfolio_value = self.get_portfolio_value(trade_data['user_id'])
            price_volatility = self._get_historical_volatility(trade_data['symbol'])
            
            # Dynamic position sizing formula
            base_size = portfolio_value * self.max_position_size
            volatility_adjusted = base_size * (1 - price_volatility)
            
            # Ensure minimum position size
            return max(volatility_adjusted, portfolio_value * 0.005)
        except Exception as e:
            logger.error(f"Position calculation error: {str(e)}")
            return 0.0

    def _get_historical_volatility(self, symbol: str) -> float:
        """Calculate 30-day historical volatility"""
        try:
            conn = sqlite3.connect(self.db_path)
            df = pd.read_sql(
                f"SELECT close FROM market_data WHERE symbol = '{symbol}' ORDER BY timestamp DESC LIMIT 30",
                conn
            )
            returns = np.log(df['close'] / df['close'].shift(1))
            return returns.std() * np.sqrt(252)
        except Exception as e:
            logger.error(f"Volatility calculation error: {str(e)}")
            return 0.0

    def get_active_trades_count(self, user_id: int) -> int:
        """Get count of active trades for user"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) 
                FROM trades 
                WHERE user_id = ? AND status = 'ACTIVE'
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting active trades count: {str(e)}")
            return 0

    def get_sector_exposure(self, user_id: int, symbol: str) -> float:
        """Calculate sector exposure for a symbol"""
        try:
            # Map symbols to sectors (simplified)
            sector_map = {
                'RELIANCE': 'Energy',
                'TCS': 'Technology',
                'HDFCBANK': 'Banking',
                'ICICIBANK': 'Banking',
                'SBIN': 'Banking',
                'KOTAKBANK': 'Banking',
                'INFY': 'Technology',
                'BHARTIARTL': 'Telecom',
                'HINDUNILVR': 'FMCG',
                'BAJFINANCE': 'Financial Services'
            }
            
            symbol_sector = sector_map.get(symbol, 'Other')
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get total portfolio value
            portfolio_value = self.get_portfolio_value(user_id)
            if not portfolio_value:
                return 0.0
            
            # Get sector exposure
            sector_value = 0.0
            for sym, sector in sector_map.items():
                if sector == symbol_sector:
                    position_size = self.get_position_size(user_id, sym)
                    if position_size > 0:
                        price_data = self.get_current_price(sym)
                        if price_data:
                            sector_value += position_size * price_data['price']
            
            return sector_value / portfolio_value if portfolio_value > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating sector exposure: {str(e)}")
            return 0.0

    def check_correlation_risk(self, user_id: int, symbol: str) -> bool:
        """Check if new position would create high correlation risk"""
        try:
            # Get existing positions
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT symbol, quantity 
                FROM positions 
                WHERE user_id = ? AND quantity > 0
            ''', (user_id,))
            
            existing_positions = cursor.fetchall()
            conn.close()
            
            if not existing_positions:
                return False
            
            # Simple correlation check based on symbol similarity
            for existing_symbol, _ in existing_positions:
                if self._calculate_symbol_correlation(symbol, existing_symbol) > self.correlation_threshold:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking correlation risk: {str(e)}")
            return False

    def _calculate_symbol_correlation(self, symbol1: str, symbol2: str) -> float:
        """Calculate correlation between two symbols (simplified)"""
        try:
            # High correlation pairs
            high_correlation_pairs = [
                ('HDFCBANK', 'ICICIBANK'),
                ('HDFCBANK', 'SBIN'),
                ('ICICIBANK', 'SBIN'),
                ('TCS', 'INFY'),
                ('NIFTY50', 'SENSEX')
            ]
            
            # Check if symbols are in high correlation pairs
            for pair in high_correlation_pairs:
                if (symbol1 in pair and symbol2 in pair) or (symbol2 in pair and symbol1 in pair):
                    return 0.8
            
            # Check if same sector
            banking_symbols = ['HDFCBANK', 'ICICIBANK', 'SBIN', 'KOTAKBANK']
            tech_symbols = ['TCS', 'INFY']
            
            if (symbol1 in banking_symbols and symbol2 in banking_symbols) or \
               (symbol1 in tech_symbols and symbol2 in tech_symbols):
                return 0.6
            
            return 0.2  # Low correlation
            
        except Exception as e:
            logger.error(f"Error calculating symbol correlation: {str(e)}")
            return 0.0

    def calculate_advanced_position_size(self, user_id: int, symbol: str, risk_per_trade: float = 0.02) -> Optional[float]:
        """Calculate position size with volatility adjustment"""
        try:
            portfolio_value = self.get_portfolio_value(user_id)
            if portfolio_value is None:
                return None

            # Get current price and volatility
            current_price_data = self.get_current_price(symbol)
            volatility = self.calculate_volatility(symbol)
            
            if current_price_data is None or volatility is None:
                return None

            current_price = current_price_data['price']
            
            # Base position size
            base_risk_amount = portfolio_value * risk_per_trade
            
            # Adjust for volatility (lower volatility = larger position)
            volatility_adjustment = max(0.5, min(2.0, 1.0 / (volatility + 0.01)))
            
            # Adjust for correlation with existing positions
            correlation_penalty = 1.0
            if self.check_correlation_risk(user_id, symbol):
                correlation_penalty = 0.5
            
            # Calculate final position size
            adjusted_risk_amount = base_risk_amount * volatility_adjustment * correlation_penalty
            position_size = adjusted_risk_amount / current_price
            
            return position_size
            
        except Exception as e:
            logger.error(f"Error calculating advanced position size: {str(e)}")
            return None

    def get_portfolio_risk_metrics(self, user_id: int) -> Dict:
        """Get comprehensive portfolio risk metrics"""
        try:
            portfolio_value = self.get_portfolio_value(user_id)
            if not portfolio_value:
                return {}
            
            # Get all positions
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT symbol, quantity, current_price 
                FROM positions 
                WHERE user_id = ? AND quantity > 0
            ''', (user_id,))
            
            positions = cursor.fetchall()
            conn.close()
            
            # Calculate metrics
            total_exposure = sum(quantity * price for _, quantity, price in positions)
            concentration_risk = max((quantity * price) / portfolio_value for _, quantity, price in positions) if positions else 0
            
            # Calculate sector concentration
            sector_exposures = {}
            for symbol, quantity, price in positions:
                sector = self._get_symbol_sector(symbol)
                if sector not in sector_exposures:
                    sector_exposures[sector] = 0
                sector_exposures[sector] += quantity * price
            
            max_sector_exposure = max(sector_exposures.values()) / portfolio_value if sector_exposures else 0
            
            return {
                'portfolio_value': portfolio_value,
                'total_exposure': total_exposure,
                'cash_ratio': (portfolio_value - total_exposure) / portfolio_value,
                'concentration_risk': concentration_risk,
                'max_sector_exposure': max_sector_exposure,
                'active_positions': len(positions),
                'daily_pnl': self.get_daily_pnl(user_id),
                'drawdown': self.calculate_drawdown(user_id)
            }
            
        except Exception as e:
            logger.error(f"Error calculating portfolio risk metrics: {str(e)}")
            return {}

    def _get_symbol_sector(self, symbol: str) -> str:
        """Get sector for a symbol"""
        sector_map = {
            'RELIANCE': 'Energy',
            'TCS': 'Technology',
            'HDFCBANK': 'Banking',
            'ICICIBANK': 'Banking',
            'SBIN': 'Banking',
            'KOTAKBANK': 'Banking',
            'INFY': 'Technology',
            'BHARTIARTL': 'Telecom',
            'HINDUNILVR': 'FMCG',
            'BAJFINANCE': 'Financial Services',
            'NIFTY50': 'Index',
            'BANKNIFTY': 'Index',
            'SENSEX': 'Index'
        }
        return sector_map.get(symbol, 'Other')

    # Mock price generation disabled