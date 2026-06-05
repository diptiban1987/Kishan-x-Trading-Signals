#!/usr/bin/env python3
"""
Advanced Portfolio Analytics and Performance Tracking
Provides comprehensive portfolio analysis, risk metrics, and performance reporting
"""

import pandas as pd
import numpy as np
import sqlite3
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json

logger = logging.getLogger(__name__)

def _get_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading.db')

class PortfolioAnalytics:
    """Advanced portfolio analytics and performance tracking"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path if db_path is not None else _get_db_path()
        
    def get_portfolio_summary(self, user_id: int) -> Dict:
        """Get comprehensive portfolio summary"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get current portfolio value
            portfolio_value = self._get_current_portfolio_value(user_id)
            
            # Get today's P&L
            today_pnl = self._get_daily_pnl(user_id, datetime.now().date())
            
            # Get total P&L
            total_pnl = self._get_total_pnl(user_id)
            
            # Get active positions
            active_positions = self._get_active_positions(user_id)
            
            # Get performance metrics
            performance_metrics = self._calculate_performance_metrics(user_id)
            
            # Get risk metrics
            risk_metrics = self._calculate_risk_metrics(user_id)
            
            conn.close()
            
            return {
                'portfolio_value': portfolio_value,
                'today_pnl': today_pnl,
                'total_pnl': total_pnl,
                'active_positions': len(active_positions),
                'performance_metrics': performance_metrics,
                'risk_metrics': risk_metrics,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting portfolio summary: {str(e)}")
            return {}
    
    def get_performance_analysis(self, user_id: int, days: int = 30) -> Dict:
        """Get detailed performance analysis"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get trade history
            trades_df = pd.read_sql_query('''
                SELECT * FROM trades 
                WHERE user_id = ? AND status = 'CLOSED'
                ORDER BY exit_time DESC
            ''', conn, params=(user_id,))
            
            # Get portfolio history
            portfolio_df = pd.read_sql_query('''
                SELECT * FROM portfolio_history 
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', conn, params=(user_id, days))
            
            conn.close()
            
            if trades_df.empty:
                return self._empty_performance_analysis()
            
            # Calculate performance metrics
            performance = self._calculate_detailed_performance(trades_df, portfolio_df)
            
            return performance
            
        except Exception as e:
            logger.error(f"Error getting performance analysis: {str(e)}")
            return {}
    
    def get_risk_analysis(self, user_id: int) -> Dict:
        """Get comprehensive risk analysis"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get all trades
            trades_df = pd.read_sql_query('''
                SELECT * FROM trades 
                WHERE user_id = ? AND status = 'CLOSED'
                ORDER BY exit_time DESC
            ''', conn, params=(user_id,))
            
            # Get portfolio history
            portfolio_df = pd.read_sql_query('''
                SELECT * FROM portfolio_history 
                WHERE user_id = ?
                ORDER BY timestamp DESC
            ''', conn, params=(user_id,))
            
            conn.close()
            
            if trades_df.empty or portfolio_df.empty:
                return self._empty_risk_analysis()
            
            # Calculate risk metrics
            risk_analysis = self._calculate_risk_analysis(trades_df, portfolio_df)
            
            return risk_analysis
            
        except Exception as e:
            logger.error(f"Error getting risk analysis: {str(e)}")
            return {}
    
    def get_trade_analytics(self, user_id: int, days: int = 30) -> Dict:
        """Get detailed trade analytics"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get trades for the specified period
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            trades_df = pd.read_sql_query('''
                SELECT * FROM trades 
                WHERE user_id = ? AND status = 'CLOSED'
                AND exit_time >= ? AND exit_time <= ?
                ORDER BY exit_time DESC
            ''', conn, params=(user_id, start_date.isoformat(), end_date.isoformat()))
            
            conn.close()
            
            if trades_df.empty:
                return self._empty_trade_analytics()
            
            # Calculate trade analytics
            analytics = self._calculate_trade_analytics(trades_df)
            
            return analytics
            
        except Exception as e:
            logger.error(f"Error getting trade analytics: {str(e)}")
            return {}
    
    def get_sector_analysis(self, user_id: int) -> Dict:
        """Get sector-wise portfolio analysis"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get active positions
            try:
                positions_df = pd.read_sql_query('''
                    SELECT symbol, quantity, current_price 
                    FROM positions 
                    WHERE user_id = ? AND quantity > 0
                ''', conn, params=(user_id,))
            except Exception:
                positions_df = pd.read_sql_query('''
                    SELECT symbol, quantity, average_price AS current_price
                    FROM positions 
                    WHERE user_id = ? AND quantity > 0
                ''', conn, params=(user_id,))
            
            conn.close()
            
            if positions_df.empty:
                return {'sectors': {}, 'total_value': 0}
            
            # Calculate sector allocation
            sector_analysis = self._calculate_sector_analysis(positions_df)
            
            return sector_analysis
            
        except Exception as e:
            logger.error(f"Error getting sector analysis: {str(e)}")
            return {}
    
    def _get_current_portfolio_value(self, user_id: int) -> float:
        """Get current portfolio value"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get cash balance
            cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            cash_balance = row[0] if row else 0
            
            try:
                cursor.execute('''
                    SELECT SUM(quantity * current_price) 
                    FROM positions 
                    WHERE user_id = ? AND quantity > 0
                ''', (user_id,))
            except Exception:
                cursor.execute('''
                    SELECT SUM(quantity * average_price) 
                    FROM positions 
                    WHERE user_id = ? AND quantity > 0
                ''', (user_id,))
            
            pos_row = cursor.fetchone()
            position_value = pos_row[0] if pos_row and pos_row[0] else 0
            
            conn.close()
            
            return float(cash_balance + position_value)
            
        except Exception as e:
            logger.error(f"Error getting portfolio value: {str(e)}")
            return 0.0
    
    def _get_daily_pnl(self, user_id: int, date: datetime.date) -> float:
        """Get daily P&L for a specific date"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT SUM(profit_loss) 
                FROM trades 
                WHERE user_id = ? AND DATE(exit_time) = ?
            ''', (user_id, date.isoformat()))
            
            result = cursor.fetchone()
            conn.close()
            
            return float(result[0]) if result and result[0] else 0.0
            
        except Exception as e:
            logger.error(f"Error getting daily P&L: {str(e)}")
            return 0.0
    
    def _get_total_pnl(self, user_id: int) -> float:
        """Get total P&L"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT SUM(profit_loss) 
                FROM trades 
                WHERE user_id = ? AND status = 'CLOSED'
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            return float(result[0]) if result and result[0] else 0.0
            
        except Exception as e:
            logger.error(f"Error getting total P&L: {str(e)}")
            return 0.0
    
    def _get_active_positions(self, user_id: int) -> List[Dict]:
        """Get active positions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    SELECT symbol, quantity, current_price, entry_price, entry_time
                    FROM positions 
                    WHERE user_id = ? AND quantity > 0
                ''', (user_id,))
            except Exception:
                cursor.execute('''
                    SELECT symbol, quantity, average_price AS current_price, average_price AS entry_price, last_updated AS entry_time
                    FROM positions 
                    WHERE user_id = ? AND quantity > 0
                ''', (user_id,))
            
            positions = []
            for row in cursor.fetchall():
                positions.append({
                    'symbol': row[0],
                    'quantity': row[1],
                    'current_price': row[2],
                    'entry_price': row[3],
                    'entry_time': row[4],
                    'unrealized_pnl': (row[2] - row[3]) * row[1]
                })
            
            conn.close()
            return positions
            
        except Exception as e:
            logger.error(f"Error getting active positions: {str(e)}")
            return []
    
    def _calculate_performance_metrics(self, user_id: int) -> Dict:
        """Calculate performance metrics"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get trade statistics
            trades_df = pd.read_sql_query('''
                SELECT * FROM trades 
                WHERE user_id = ? AND status = 'CLOSED'
            ''', conn, params=(user_id,))
            
            conn.close()
            
            if trades_df.empty:
                return {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0.0,
                    'average_win': 0.0,
                    'average_loss': 0.0,
                    'profit_factor': 0.0,
                    'max_drawdown': 0.0,
                    'sharpe_ratio': 0.0
                }
            
            # Calculate metrics
            total_trades = len(trades_df)
            winning_trades = trades_df[trades_df['profit_loss'] > 0]
            losing_trades = trades_df[trades_df['profit_loss'] < 0]
            
            win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
            
            avg_win = winning_trades['profit_loss'].mean() if len(winning_trades) > 0 else 0
            avg_loss = losing_trades['profit_loss'].mean() if len(losing_trades) > 0 else 0
            
            total_profit = winning_trades['profit_loss'].sum() if len(winning_trades) > 0 else 0
            total_loss = abs(losing_trades['profit_loss'].sum()) if len(losing_trades) > 0 else 0
            
            profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
            
            # Calculate drawdown
            cumulative_returns = trades_df['profit_loss'].cumsum()
            running_max = cumulative_returns.expanding().max()
            drawdown = (running_max - cumulative_returns) / running_max
            max_drawdown = drawdown.max()
            
            # Calculate Sharpe ratio (simplified)
            returns = trades_df['profit_loss']
            sharpe_ratio = returns.mean() / returns.std() if returns.std() > 0 else 0
            
            return {
                'total_trades': total_trades,
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': win_rate,
                'average_win': avg_win,
                'average_loss': avg_loss,
                'profit_factor': profit_factor,
                'max_drawdown': max_drawdown,
                'sharpe_ratio': sharpe_ratio
            }
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {str(e)}")
            return {}
    
    def _calculate_risk_metrics(self, user_id: int) -> Dict:
        """Calculate risk metrics"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get portfolio history
            portfolio_df = pd.read_sql_query('''
                SELECT portfolio_value, timestamp 
                FROM portfolio_history 
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 30
            ''', conn, params=(user_id,))
            
            conn.close()
            
            if portfolio_df.empty:
                return {
                    'volatility': 0.0,
                    'var_95': 0.0,
                    'cvar_95': 0.0,
                    'max_drawdown': 0.0,
                    'calmar_ratio': 0.0
                }
            
            # Calculate daily returns
            portfolio_df['returns'] = portfolio_df['portfolio_value'].pct_change()
            returns = portfolio_df['returns'].dropna()
            
            if len(returns) < 2:
                return {
                    'volatility': 0.0,
                    'var_95': 0.0,
                    'cvar_95': 0.0,
                    'max_drawdown': 0.0,
                    'calmar_ratio': 0.0
                }
            
            # Calculate risk metrics
            volatility = returns.std() * np.sqrt(252)  # Annualized
            
            # Value at Risk (95%)
            var_95 = np.percentile(returns, 5)
            
            # Conditional Value at Risk (95%)
            cvar_95 = returns[returns <= var_95].mean()
            
            # Maximum drawdown
            cumulative_returns = (1 + returns).cumprod()
            running_max = cumulative_returns.expanding().max()
            drawdown = (running_max - cumulative_returns) / running_max
            max_drawdown = drawdown.max()
            
            # Calmar ratio
            annual_return = returns.mean() * 252
            calmar_ratio = annual_return / max_drawdown if max_drawdown > 0 else 0
            
            return {
                'volatility': volatility,
                'var_95': var_95,
                'cvar_95': cvar_95,
                'max_drawdown': max_drawdown,
                'calmar_ratio': calmar_ratio
            }
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {str(e)}")
            return {}
    
    def _calculate_detailed_performance(self, trades_df: pd.DataFrame, portfolio_df: pd.DataFrame) -> Dict:
        """Calculate detailed performance analysis"""
        try:
            # Basic metrics
            total_trades = len(trades_df)
            winning_trades = trades_df[trades_df['profit_loss'] > 0]
            losing_trades = trades_df[trades_df['profit_loss'] < 0]
            
            win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
            
            # Monthly performance
            trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
            trades_df['month'] = trades_df['exit_time'].dt.to_period('M')
            monthly_pnl = trades_df.groupby('month')['profit_loss'].sum()
            
            # Best and worst trades
            best_trade = trades_df['profit_loss'].max()
            worst_trade = trades_df['profit_loss'].min()
            
            # Consecutive wins/losses
            consecutive_wins, consecutive_losses = self._calculate_consecutive_trades(trades_df)
            
            # Time-based analysis
            trades_df['hour'] = trades_df['exit_time'].dt.hour
            hourly_performance = trades_df.groupby('hour')['profit_loss'].mean()
            
            # Symbol performance
            symbol_performance = trades_df.groupby('symbol')['profit_loss'].agg(['count', 'sum', 'mean'])
            
            return {
                'total_trades': total_trades,
                'win_rate': win_rate,
                'monthly_performance': monthly_pnl.to_dict(),
                'best_trade': best_trade,
                'worst_trade': worst_trade,
                'consecutive_wins': consecutive_wins,
                'consecutive_losses': consecutive_losses,
                'hourly_performance': hourly_performance.to_dict(),
                'symbol_performance': symbol_performance.to_dict()
            }
            
        except Exception as e:
            logger.error(f"Error calculating detailed performance: {str(e)}")
            return {}
    
    def _calculate_risk_analysis(self, trades_df: pd.DataFrame, portfolio_df: pd.DataFrame) -> Dict:
        """Calculate comprehensive risk analysis"""
        try:
            # Portfolio volatility
            portfolio_df['returns'] = portfolio_df['portfolio_value'].pct_change()
            returns = portfolio_df['returns'].dropna()
            
            volatility = returns.std() * np.sqrt(252) if len(returns) > 1 else 0
            
            # Trade-level risk
            trade_returns = trades_df['profit_loss']
            trade_volatility = trade_returns.std()
            
            # Drawdown analysis
            cumulative_returns = (1 + returns).cumprod() if len(returns) > 0 else pd.Series([1])
            running_max = cumulative_returns.expanding().max()
            drawdown = (running_max - cumulative_returns) / running_max
            max_drawdown = drawdown.max()
            
            # Risk-adjusted returns
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
            
            # Tail risk
            var_95 = np.percentile(returns, 5) if len(returns) > 0 else 0
            cvar_95 = returns[returns <= var_95].mean() if len(returns[returns <= var_95]) > 0 else 0
            
            return {
                'portfolio_volatility': volatility,
                'trade_volatility': trade_volatility,
                'max_drawdown': max_drawdown,
                'sharpe_ratio': sharpe_ratio,
                'var_95': var_95,
                'cvar_95': cvar_95,
                'tail_risk': abs(cvar_95) if cvar_95 < 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error calculating risk analysis: {str(e)}")
            return {}
    
    def _calculate_trade_analytics(self, trades_df: pd.DataFrame) -> Dict:
        """Calculate detailed trade analytics"""
        try:
            # Time-based analytics
            trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
            trades_df['day_of_week'] = trades_df['exit_time'].dt.day_name()
            trades_df['hour'] = trades_df['exit_time'].dt.hour
            
            # Performance by time
            daily_performance = trades_df.groupby('day_of_week')['profit_loss'].agg(['count', 'sum', 'mean'])
            hourly_performance = trades_df.groupby('hour')['profit_loss'].agg(['count', 'sum', 'mean'])
            
            # Symbol analysis
            symbol_analysis = trades_df.groupby('symbol').agg({
                'profit_loss': ['count', 'sum', 'mean', 'std'],
                'entry_price': 'mean',
                'exit_price': 'mean'
            }).round(2)
            
            # Direction analysis
            direction_analysis = trades_df.groupby('direction')['profit_loss'].agg(['count', 'sum', 'mean'])
            
            # Trade duration analysis
            trades_df['entry_time'] = pd.to_datetime(trades_df['entry_time'])
            trades_df['duration'] = (trades_df['exit_time'] - trades_df['entry_time']).dt.total_seconds() / 3600  # hours
            duration_analysis = trades_df['duration'].describe()
            
            return {
                'daily_performance': daily_performance.to_dict(),
                'hourly_performance': hourly_performance.to_dict(),
                'symbol_analysis': symbol_analysis.to_dict(),
                'direction_analysis': direction_analysis.to_dict(),
                'duration_analysis': duration_analysis.to_dict(),
                'total_trades': len(trades_df),
                'total_pnl': trades_df['profit_loss'].sum(),
                'win_rate': len(trades_df[trades_df['profit_loss'] > 0]) / len(trades_df)
            }
            
        except Exception as e:
            logger.error(f"Error calculating trade analytics: {str(e)}")
            return {}
    
    def _calculate_sector_analysis(self, positions_df: pd.DataFrame) -> Dict:
        """Calculate sector-wise analysis"""
        try:
            # Map symbols to sectors
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
            
            # Calculate position values
            positions_df['position_value'] = positions_df['quantity'] * positions_df['current_price']
            positions_df['sector'] = positions_df['symbol'].map(sector_map).fillna('Other')
            
            # Sector allocation
            sector_allocation = positions_df.groupby('sector')['position_value'].sum()
            total_value = sector_allocation.sum()
            
            # Calculate percentages
            sector_percentages = (sector_allocation / total_value * 100).round(2)
            
            return {
                'sectors': sector_allocation.to_dict(),
                'percentages': sector_percentages.to_dict(),
                'total_value': total_value,
                'diversification_score': len(sector_allocation) / 10  # Simple diversification score
            }
            
        except Exception as e:
            logger.error(f"Error calculating sector analysis: {str(e)}")
            return {}
    
    def _calculate_consecutive_trades(self, trades_df: pd.DataFrame) -> Tuple[int, int]:
        """Calculate consecutive wins and losses"""
        try:
            if trades_df.empty:
                return 0, 0
            
            # Sort by exit time
            trades_df = trades_df.sort_values('exit_time')
            
            # Calculate consecutive wins and losses
            trades_df['is_win'] = trades_df['profit_loss'] > 0
            
            consecutive_wins = 0
            consecutive_losses = 0
            current_wins = 0
            current_losses = 0
            
            for is_win in trades_df['is_win']:
                if is_win:
                    current_wins += 1
                    current_losses = 0
                    consecutive_wins = max(consecutive_wins, current_wins)
                else:
                    current_losses += 1
                    current_wins = 0
                    consecutive_losses = max(consecutive_losses, current_losses)
            
            return consecutive_wins, consecutive_losses
            
        except Exception as e:
            logger.error(f"Error calculating consecutive trades: {str(e)}")
            return 0, 0
    
    def _empty_performance_analysis(self) -> Dict:
        """Return empty performance analysis"""
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'monthly_performance': {},
            'best_trade': 0.0,
            'worst_trade': 0.0,
            'consecutive_wins': 0,
            'consecutive_losses': 0,
            'hourly_performance': {},
            'symbol_performance': {}
        }
    
    def _empty_risk_analysis(self) -> Dict:
        """Return empty risk analysis"""
        return {
            'portfolio_volatility': 0.0,
            'trade_volatility': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'var_95': 0.0,
            'cvar_95': 0.0,
            'tail_risk': 0.0
        }
    
    def _empty_trade_analytics(self) -> Dict:
        """Return empty trade analytics"""
        return {
            'daily_performance': {},
            'hourly_performance': {},
            'symbol_analysis': {},
            'direction_analysis': {},
            'duration_analysis': {},
            'total_trades': 0,
            'total_pnl': 0.0,
            'win_rate': 0.0
        }
