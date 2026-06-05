"""
AI Client - Production Version with OpenRouter Fallback
Primary: Google Gemini API (gemini-2.5-flash)
Fallback: OpenRouter API (free tier models)
Falls back gracefully to local rule-based templates if both APIs fail.
"""

import os
import logging
import requests
import json
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class GeminiAPIClient:
    """Lightweight multi-provider AI client for trading insights.
    
    Tries Gemini first, falls back to OpenRouter if configured,
    then falls back to local rule-based templates.
    """
    
    def __init__(self):
        # Gemini configuration
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        
        # OpenRouter configuration (fallback)
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct:free")
        self.openrouter_site_url = os.getenv("OPENROUTER_SITE_URL", "http://localhost:4000")
        self.openrouter_app_name = os.getenv("OPENROUTER_APP_NAME", "KishanX Trading Signals")
        
        if not self.api_key and not self.openrouter_api_key:
            logger.warning("No AI API keys configured (GEMINI_API_KEY or OPENROUTER_API_KEY). Running in fallback mode.")
        elif not self.api_key:
            logger.info("GEMINI_API_KEY not set — will use OpenRouter as primary AI provider.")
        elif not self.openrouter_api_key:
            logger.info("OPENROUTER_API_KEY not set — will use Gemini as sole AI provider.")
        else:
            logger.info("Both Gemini and OpenRouter configured — Gemini primary, OpenRouter fallback.")
            
    def is_active(self) -> bool:
        """Check if any AI API client is configured"""
        return bool(self.api_key) or bool(self.openrouter_api_key)

    def _call_ai_api(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        """Try Gemini first, fall back to OpenRouter, return None if both fail."""
        # Try Gemini
        if self.api_key:
            result = self._call_gemini_api(prompt, system_instruction)
            if result:
                return result
            logger.info("Gemini failed or unavailable — trying OpenRouter fallback.")
        else:
            logger.info("Gemini not configured — trying OpenRouter.")
        
        # Fallback: try OpenRouter
        if self.openrouter_api_key:
            result = self._call_openrouter_api(prompt, system_instruction)
            if result:
                return result
            logger.info("OpenRouter fallback also failed.")
        else:
            logger.info("OpenRouter not configured — skipping fallback.")
        
        return None

    def _call_gemini_api(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        """Core Gemini REST endpoint caller"""
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.4,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 800,
            }
        }
        
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [
                    {
                        "text": system_instruction
                    }
                ]
            }
            
        try:
            response = requests.post(
                self.url,
                headers=headers,
                params={"key": self.api_key},
                json=payload,
                timeout=5.0
            )
            
            if response.status_code == 200:
                res_data = response.json()
                candidates = res_data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
            else:
                logger.error(f"Gemini API call failed with status {response.status_code}: {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            logger.warning("Gemini API call timed out.")
        except Exception as e:
            logger.error(f"Gemini API unexpected error: {str(e)}")
            
        return None

    def _call_openrouter_api(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        """Fallback to OpenRouter API using OpenAI-compatible chat completions"""
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.openrouter_site_url,
            "X-Title": self.openrouter_app_name,
        }
        
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.openrouter_model,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 800,
            "top_p": 0.95,
        }
        
        try:
            response = requests.post(
                self.openrouter_url,
                headers=headers,
                json=payload,
                timeout=10.0
            )
            
            if response.status_code == 200:
                res_data = response.json()
                choices = res_data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
            else:
                logger.error(f"OpenRouter API call failed with status {response.status_code}: {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            logger.warning("OpenRouter API call timed out.")
        except Exception as e:
            logger.error(f"OpenRouter API unexpected error: {str(e)}")
            
        return None

    def explain_signal(self, symbol: str, direction: str, confidence: float, current_price: float, indicators: Dict) -> str:
        """Generate high-value conversational technical commentary for a generated trade signal"""
        if not self.is_active():
            return self._get_rule_based_signal_fallback(symbol, direction, confidence, current_price, indicators)
            
        system_instruction = (
            "You are a professional quantitative financial analyst specialized in Indian stock markets (NSE/BSE). "
            "Explain technical analysis trading signals clearly, concisely, and actionable in 3 short paragraphs. "
            "Highlight support and resistance levels, relevant indicators, and key risk/reward parameters. "
            "Always include a disclaimer: 'Trading involves high risk. This is not financial advice.'"
        )
        
        prompt = (
            f"Analyze this generated trading signal:\n"
            f"- Ticker/Symbol: {symbol}\n"
            f"- Direction: {direction} (BUY/SELL/HOLD)\n"
            f"- Current Market Price: {current_price}\n"
            f"- Signal Confidence Score: {confidence*100:.1f}%\n"
            f"- indicators: {json.dumps(indicators, default=str)}\n\n"
            f"Please explain why this signal occurred based on indicators like RSI, MACD, and Bollinger Bands. "
            f"Suggest entry trigger conditions, logical stop-loss (SL) level, and target/take-profit (TP) levels based on ATR or nearest key structures."
        )
        
        response = self._call_ai_api(prompt, system_instruction)
        if response:
            return response
            
        return self._get_rule_based_signal_fallback(symbol, direction, confidence, current_price, indicators)

    def chat_response(self, user_query: str, portfolio_context: Optional[str] = None) -> str:
        """Process custom conversational queries about trading, strategies, and portfolio status"""
        if not self.is_active():
            return ("I am running in local fallback mode. Please ask me about RSI, MACD, Bollinger Bands, "
                    "Risk management or your Portfolio Summary, or configure GEMINI_API_KEY or "
                    "OPENROUTER_API_KEY in your .env file.")
            
        system_instruction = (
            "You are a helpful, professional AI Trading Assistant on the KishanX Trading Signals platform. "
            "You help users learn about trading concepts (pips, leverage, margins, support/resistance), "
            "explain technical indicators (RSI, MACD, Bollinger Bands), and interpret their current portfolio metrics. "
            "Be precise, clean in your markdown formatting, and always remind the user about proper risk control."
        )
        
        prompt = user_query
        if portfolio_context:
            prompt = f"User Portfolio Context:\n{portfolio_context}\n\nUser Question: {user_query}"
            
        response = self._call_ai_api(prompt, system_instruction)
        if response:
            return response
            
        return "I am currently unable to reach my AI brain. Please check your internet connection or ask basic terms like 'What is RSI?' or 'Explain MACD' to trigger local answers."

    def _get_rule_based_signal_fallback(self, symbol: str, direction: str, confidence: float, current_price: float, indicators: Dict) -> str:
        """Highly structured, professional local text generator when Gemini is offline"""
        rsi = indicators.get('rsi', 50)
        macd = indicators.get('macd', 0)
        macd_sig = indicators.get('macd_signal', 0)
        
        levels = []
        if direction == 'BUY':
            levels.append(f"• **Entry Trigger**: Market buy above {current_price:.2f}")
            levels.append(f"• **Stop Loss**: {current_price * 0.985:.2f} (1.5% stop)")
            levels.append(f"• **Take Profit**: {current_price * 1.03:.2f} (3.0% target)")
        elif direction == 'SELL':
            levels.append(f"• **Entry Trigger**: Market short below {current_price:.2f}")
            levels.append(f"• **Stop Loss**: {current_price * 1.015:.2f} (1.5% stop)")
            levels.append(f"• **Take Profit**: {current_price * 0.97:.2f} (3.0% target)")
            
        bullet_levels = "\n".join(levels)
        
        return (
            f"**Technical Analysis Summary for {symbol} ({direction})**\n\n"
            f"The quantitative model generated a **{direction}** signal for **{symbol}** at **{current_price:.2f}** "
            f"with a confidence score of **{confidence*100:.1f}%**.\n\n"
            f"**Technical Highlights**:\n"
            f"- **Relative Strength (RSI)**: The 14-period RSI is hovering at **{rsi:.2f}**, indicating "
            f"{'oversold conditions (oversold trigger)' if rsi < 35 else ('overbought conditions (overbought warning)' if rsi > 65 else 'neutral momentum')}.\n"
            f"- **MACD Trend**: The MACD line ({macd:.4f}) is running "
            f"{'above' if macd > macd_sig else 'below'} its signal line ({macd_sig:.4f}), indicating "
            f"{'bullish crossover momentum' if macd > macd_sig else 'bearish distribution momentum'}.\n\n"
            f"**Suggested Execution Levels**:\n"
            f"{bullet_levels if direction != 'HOLD' else '• Maintain current cash positions. No immediate triggers.'}\n\n"
            f"*Disclaimer: Financial trading involves high capital risk. Past performance does not guarantee future results.*"
        )

# Global singleton client
gemini_client = GeminiAPIClient()
