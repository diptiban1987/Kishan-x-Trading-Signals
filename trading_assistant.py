"""
Trading Assistant — Intent-based conversational AI for trading questions.
Uses the existing AISignalPredictor for signal-related queries and
provides rule-based responses for strategy, risk, and educational questions.
"""
import os
import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from ai_models.gemini_explainer import gemini_client

logger = logging.getLogger(__name__)

_predictor = None
_portfolio_analytics = None
_risk_manager = None

def _get_predictor():
    global _predictor
    if _predictor is None:
        try:
            from ai_models.signal_predictor import AISignalPredictor
            _predictor = AISignalPredictor()
        except Exception as e:
            logger.error(f"Failed to load AI predictor: {e}")
    return _predictor

INTENTS = {
    'signal': ['signal', 'predict', 'buy', 'sell', 'hold', 'recommend', 'analysis', 'outlook'],
    'strategy': ['strategy', 'rsi', 'macd', 'bollinger', 'moving average', 'indicator', 'technical'],
    'market': ['market', 'nifty', 'sensex', 'index', 'sector', 'overview', 'sentiment'],
    'risk': ['risk', 'stop loss', 'take profit', 'position size', 'drawdown', 'exposure'],
    'portfolio': ['portfolio', 'pnl', 'profit', 'loss', 'performance', 'balance', 'win rate'],
    'help': ['help', 'what can you', 'commands', 'guide', 'tutorial', 'how to'],
    'education': ['what is', 'explain', 'how does', 'define', 'meaning', 'difference'],
}

STRATEGY_INFO = {
    'rsi': {
        'name': 'RSI (Relative Strength Index)',
        'description': 'Measures the speed and magnitude of recent price changes. RSI above 70 suggests overbought (potential SELL), below 30 suggests oversold (potential BUY).',
        'settings': 'Default period: 14. Overbought threshold: 70. Oversold threshold: 30.',
    },
    'macd': {
        'name': 'MACD (Moving Average Convergence Divergence)',
        'description': 'Shows the relationship between two moving averages. A bullish signal occurs when the MACD line crosses above the signal line. A bearish signal when it crosses below.',
        'settings': 'Fast EMA: 12. Slow EMA: 26. Signal line: 9-period EMA.',
    },
    'bollinger': {
        'name': 'Bollinger Bands',
        'description': 'A volatility indicator consisting of a middle SMA band with upper and lower bands at 2 standard deviations. Price touching the lower band suggests oversold; touching the upper band suggests overbought.',
        'settings': 'Period: 20. Standard deviations: 2.',
    },
    'moving_average': {
        'name': 'Moving Average Crossovers',
        'description': 'Uses SMA-20 and SMA-50 crossings. A bullish signal occurs when SMA-20 crosses above SMA-50 (golden cross). A bearish signal when SMA-20 crosses below SMA-50 (death cross).',
        'settings': 'Short: SMA-20. Long: SMA-50. Additional: SMA-200 for long-term trend.',
    },
}

RISK_GUIDELINES = (
    "**Position Sizing:** Never risk more than 1-2% of your capital on a single trade.\n\n"
    "**Stop Loss:** Always use a stop loss. A common guideline is 2% below entry for long positions.\n\n"
    "**Risk/Reward Ratio:** Aim for a minimum 1:2 risk/reward ratio.\n\n"
    "**Maximum Drawdown:** Stop trading if your portfolio drops 15% from peak.\n\n"
    "**Diversification:** Don't put more than 5% of capital in a single position.\n\n"
    "**Leverage Warning:** Leverage amplifies both gains AND losses. Use cautiously."
)

WELCOME_MESSAGE = (
    "Hello! I'm your **AI Trading Assistant**. I can help with:\n\n"
    "📊 **Signal Analysis** — \"Analyze NIFTY50\"\n"
    "📈 **Market Overview** — \"Market sentiment\"\n"
    "💡 **Strategy Explanations** — \"Explain RSI\"\n"
    "🛡️ **Risk Guidelines** — \"Risk management tips\"\n"
    "📋 **Portfolio Insights** — \"My portfolio summary\"\n"
    "Type a question or use the quick action buttons below."
)


def get_response(message: str, user_id: int = None) -> Dict:
    message_lower = message.lower().strip()

    if not message_lower:
        return _text_response("Please ask me a question about trading, signals, or strategies.", 'help')

    intent, symbol = _classify_intent(message_lower)

    # If Gemini is active and it's a general or educational/unknown query, delegate to Gemini
    if gemini_client.is_active() and intent in ('unknown', 'education'):
        try:
            portfolio_context = None
            if user_id:
                try:
                    portfolio_data = _handle_portfolio_query(user_id)
                    if portfolio_data and portfolio_data.get('type') == 'portfolio':
                        portfolio_context = portfolio_data.get('text')
                except Exception:
                    pass
            
            ai_text = gemini_client.chat_response(message, portfolio_context)
            if ai_text:
                return _text_response(ai_text, 'assistant_ai')
        except Exception as e:
            logger.warning(f"Failed to get Gemini chat response: {e}")

    if intent == 'signal' and symbol:
        return _handle_signal_query(symbol)
    elif intent == 'signal' and not symbol:
        return _handle_generic_signal()
    elif intent == 'strategy' and symbol:
        return _handle_strategy_explain(symbol)
    elif intent == 'market':
        return _handle_market_overview()
    elif intent == 'risk':
        return _risk_response()
    elif intent == 'portfolio':
        return _handle_portfolio_query(user_id)
    elif intent == 'help':
        return _text_response(WELCOME_MESSAGE, 'help')
    elif intent == 'education':
        return _handle_education(message_lower)

    return _text_response(
        "I'm not sure I understand. I can help with:\n\n"
        "• **Signal analysis** — Try \"Analyze EURUSD\" or \"NIFTY50 signal\"\n"
        "• **Strategy help** — Try \"Explain MACD\" or \"What is RSI?\"\n"
        "• **Market overview** — Try \"Market sentiment\"\n"
        "• **Risk management** — Try \"Risk guidelines\"\n"
        "• **Portfolio** — Try \"Portfolio summary\"",
        'help'
    )


def _classify_intent(message: str) -> tuple:
    symbol = _extract_symbol(message)
    for intent, keywords in INTENTS.items():
        for kw in keywords:
            if kw in message:
                if symbol:
                    return intent, symbol
                if intent == 'strategy':
                    for strat in STRATEGY_INFO:
                        if strat in message or STRATEGY_INFO[strat]['name'].lower() in message:
                            return intent, strat
                return intent, None
    return 'unknown', symbol


_SYMBOL_PATTERNS = [
    (r'\b(NIFTY50|NIFTY|NSE)\b', 'NIFTY50'),
    (r'\b(BANKNIFTY|BANK NIFTY)\b', 'BANKNIFTY'),
    (r'\bSENSEX\b', 'SENSEX'),
    (r'\b(AUDUSD|EURUSD|GBPUSD|USDJPY|USDCAD|USDCHF|NZDUSD)\b', lambda m: m.group(1)),
    (r'\b(RELIANCE|TCS|HDFCBANK|INFY|ICICIBANK|SBIN|BHARTIARTL)\b', lambda m: m.group(1)),
]

def _extract_symbol(message: str) -> Optional[str]:
    for pattern, result in _SYMBOL_PATTERNS:
        m = re.search(pattern, message, re.IGNORECASE)
        if m:
            return result(m) if callable(result) else result

    pair_match = re.search(r'\b([A-Z]{2,6}/[A-Z]{2,6})\b', message, re.IGNORECASE)
    if pair_match:
        return pair_match.group(1).upper()

    single_match = re.search(r'\b[A-Z]{2,6}\b', message, re.IGNORECASE)
    if single_match:
        return single_match.group(0).upper()
    return None


def _handle_signal_query(symbol: str) -> Dict:
    predictor = _get_predictor()
    if not predictor:
        return _text_response("AI prediction engine is not available right now.", 'error')

    try:
        result = predictor.predict_symbol(symbol)
        if not result or 'signal' not in result:
            return _text_response(f"Could not generate signal for {symbol}. Try a major index like NIFTY50 or a forex pair.", 'error')

        signal = result['signal']
        confidence = result.get('confidence', 0)
        strength = result.get('signal_strength', 'Medium')
        price = result.get('current_price', 'N/A')
        regime = result.get('market_regime', 'unknown')
        support = result.get('support', 'N/A')
        resistance = result.get('resistance', 'N/A')

        signal_emoji = '🟢' if signal == 'BUY' else ('🔴' if signal == 'SELL' else '⚪')
        response = (
            f"{signal_emoji} **{symbol}** — **{signal}** ({strength}, {confidence*100:.1f}% confidence)\n\n"
            f"**Current Price**: {price}\n"
            f"**Market Regime**: {regime.capitalize()}\n"
            f"**Support**: {support} | **Resistance**: {resistance}\n\n"
        )

        if strength == 'Strong':
            response += "This signal has high confidence. "
        elif strength == 'Medium':
            response += "This signal has moderate confidence. "
        else:
            response += "This signal is weak. "

        if signal == 'BUY':
            if regime == 'trending':
                response += "The trend is your friend — consider entering with a stop loss below recent support."
            elif regime == 'volatile':
                response += "High volatility — consider a wider stop loss and smaller position size."
            else:
                response += "Consider entering with proper risk management."
        elif signal == 'SELL':
            if regime == 'trending':
                response += "The downtrend is intact — consider short positions or staying out."
            elif regime == 'volatile':
                response += "High volatility could lead to reversals — wait for confirmation."
            else:
                response += "Consider taking profits or tightening stops."
        else:
            response += "The market is uncertain — wait for a clearer setup before trading."

        return {
            'type': 'signal',
            'text': response,
            'data': result,
        }
    except Exception as e:
        logger.error(f"Signal query error for {symbol}: {e}")
        return _text_response(f"Error analyzing {symbol}: {str(e)}", 'error')


def _handle_generic_signal() -> Dict:
    return _text_response(
        "Which symbol would you like me to analyze?\n\n"
        "Try: \"Analyze NIFTY50\", \"EURUSD signal\", \"Check RELIANCE\", "
        "or \"Market sentiment\" for an overview.",
        'help'
    )


def _handle_strategy_explain(strategy_key: str) -> Dict:
    info = STRATEGY_INFO.get(strategy_key)
    if not info:
        return _text_response(
            "I can explain: RSI, MACD, Bollinger Bands, or Moving Average strategies.\n"
            "Try: \"Explain RSI\" or \"What is MACD?\"",
            'help'
        )
    return _text_response(
        f"**{info['name']}**\n\n{info['description']}\n\n**Settings**: {info['settings']}",
        'strategy'
    )


def _handle_market_overview() -> Dict:
    predictor = _get_predictor()
    if not predictor:
        return _text_response("Market analysis engine is not available.", 'error')

    symbols = ['NIFTY50', 'BANKNIFTY', 'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'EURUSD']
    signals = []
    for sym in symbols:
        try:
            result = predictor.predict_symbol(sym)
            if result and 'signal' in result:
                signals.append(result)
        except Exception:
            pass

    if not signals:
        return _text_response("Could not fetch market data. Please try again later.", 'error')

    buy_count = sum(1 for s in signals if s['signal'] == 'BUY')
    sell_count = sum(1 for s in signals if s['signal'] == 'SELL')
    hold_count = sum(1 for s in signals if s['signal'] == 'HOLD')

    lines = [f"**Market Overview** — {len(signals)} assets scanned\n"]
    lines.append(f"🟢 BUY: {buy_count} | 🔴 SELL: {sell_count} | ⚪ HOLD: {hold_count}\n")

    if buy_count > sell_count + hold_count:
        lines.append("📈 **Overall sentiment is bullish** — more assets showing buy signals.\n")
    elif sell_count > buy_count + hold_count:
        lines.append("📉 **Overall sentiment is bearish** — more assets showing sell signals.\n")
    else:
        lines.append("➡️ **Overall sentiment is neutral** — mixed signals across assets.\n")

    lines.append("\n**Individual Signals:**")
    for s in sorted(signals, key=lambda x: x.get('confidence', 0), reverse=True):
        emoji = '🟢' if s['signal'] == 'BUY' else ('🔴' if s['signal'] == 'SELL' else '⚪')
        conf = s.get('confidence', 0) * 100
        price = s.get('current_price', 'N/A')
        lines.append(f"{emoji} {s['symbol']}: {s['signal']} ({conf:.0f}%) @ {price}")

    return {
        'type': 'market',
        'text': '\n'.join(lines),
        'data': {'signals': signals, 'buy': buy_count, 'sell': sell_count, 'hold': hold_count},
    }


def _handle_portfolio_query(user_id: int = None) -> Dict:
    if not user_id:
        return _text_response("Please log in to check your portfolio.", 'error')

    try:
        from app import get_db
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT balance FROM users WHERE id=?", (user_id,))
        user_row = cur.fetchone()
        balance = float(user_row['balance']) if user_row else 0

        cur.execute("SELECT COUNT(*) as cnt FROM trades WHERE user_id=? AND status='ACTIVE'", (user_id,))
        active = cur.fetchone()['cnt']

        cur.execute("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(profit_loss),0) as total_pnl
            FROM trades WHERE user_id=? AND status='CLOSED'
        """, (user_id,))
        closed_row = cur.fetchone()
        closed_count = closed_row['cnt']
        total_pnl = float(closed_row['total_pnl'])

        cur.execute("""
            SELECT COUNT(*) as wins FROM trades
            WHERE user_id=? AND status='CLOSED' AND profit_loss > 0
        """, (user_id,))
        wins = cur.fetchone()['wins']

        win_rate = (wins / closed_count * 100) if closed_count > 0 else 0

        response = (
            f"**Portfolio Summary**\n\n"
            f"💰 **Balance**: ${balance:,.2f}\n"
            f"📊 **Active Trades**: {active}\n"
            f"✅ **Closed Trades**: {closed_count}\n"
            f"📈 **Total P&L**: {'+' if total_pnl >= 0 else ''}${total_pnl:,.2f}\n"
            f"🎯 **Win Rate**: {win_rate:.1f}%\n"
        )
        if total_pnl > 0:
            response += "\nYour trading is profitable! Keep following your strategy."
        elif total_pnl < 0:
            response += "\nYou're in a drawdown. Consider reviewing your strategy and reducing position sizes."
        else:
            response += "\nNo closed trades yet. Start trading to see performance."

        return {'type': 'portfolio', 'text': response, 'data': {
            'balance': balance, 'active_trades': active, 'closed_trades': closed_count,
            'total_pnl': total_pnl, 'win_rate': win_rate,
        }}
    except Exception as e:
        logger.error(f"Portfolio query error: {e}")
        return _text_response("Could not fetch portfolio data.", 'error')


def _handle_education(message: str) -> Dict:
    topics = {
        'pip': 'A **pip** (percentage in point) is the smallest price move in forex. For most pairs, 1 pip = 0.0001.',
        'spread': 'The **spread** is the difference between the bid (sell) and ask (buy) price. It represents the cost of the trade.',
        'leverage': '**Leverage** allows you to control a larger position with less capital. For example, 1:100 leverage means $1 controls $100.',
        'margin': '**Margin** is the amount of capital required to open a leveraged position. It\'s a security deposit, not a cost.',
        'volatility': '**Volatility** measures how much an asset\'s price fluctuates. High volatility = higher risk and potential reward.',
        'liquidity': '**Liquidity** refers to how easily an asset can be bought or sold without affecting its price.',
        'hedging': '**Hedging** involves opening opposite positions to reduce risk. For example, buying a put option to protect a long stock position.',
    }

    for topic, explanation in topics.items():
        if topic in message:
            return _text_response(f"**{topic.capitalize()}**\n\n{explanation}", 'education')

    for term in ['support', 'resistance']:
        if term in message:
            return _text_response(
                f"**{term.capitalize()}**\n\n"
                f"{'Support' if term == 'support' else 'Resistance'} is a price level where an asset "
                f"{'stops falling and may bounce up' if term == 'support' else 'stops rising and may reverse down'}. "
                f"It acts as a {'floor' if term == 'support' else 'ceiling'} in the market.",
                'education'
            )

    return _text_response(
        "I can explain trading concepts like: pips, spread, leverage, margin, volatility, "
        "liquidity, hedging, support, and resistance. Try: \"What is leverage?\"",
        'help'
    )


def _risk_response() -> Dict:
    return {'type': 'risk', 'text': f"**Risk Management Guidelines**\n\n{RISK_GUIDELINES}"}


def _text_response(text: str, response_type: str = 'text') -> Dict:
    return {'type': response_type, 'text': text}
