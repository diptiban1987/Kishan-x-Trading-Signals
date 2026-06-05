"""
Dhan API Client Integration
Provides real-time market data, historical data, and order execution.
Maintains a structural design mirroring AngelOneAPI to enable seamless failover.
Official API documentation: https://api.dhan.co/
"""

import logging
import requests
import json
import os
import re
import threading
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class DhanAPI:
    """Dhan API Client supporting retail portfolio tracking and historical charting"""
    
    def __init__(self):
        self.api_token = os.getenv("DHAN_API_TOKEN")
        self.client_id = os.getenv("DHAN_CLIENT_ID")
        self.base_url = "https://api.dhan.co"
        self.is_connected = False
        self.demo_mode = False
        
        # Dhan security IDs from official instrument master (api-scrip-master.csv)
        # Key: symbol name, Value: (securityId, exchangeSegment, instrument_type)
        # exchangeSegment: IDX_I=Index, NSE_EQ=NSE Equity, BSE_EQ=BSE Equity, NSE_FNO=F&O, etc.
        # instrument_type: INDEX, EQUITY, FUTIDX, OPTIDX, etc.
        self._symbol_info = {
            # Indices (NSE - use IDX_I segment)
            "NIFTY50":      ("13",     "IDX_I", "INDEX"),
            "BANKNIFTY":    ("25",     "IDX_I", "INDEX"),
            "FINNIFTY":     ("27",     "IDX_I", "INDEX"),
            "MIDCPNIFTY":  ("442",    "IDX_I", "INDEX"),
            "NIFTYREALTY":  ("34",     "IDX_I", "INDEX"),
            "NIFTYPVTBANK":("15",     "IDX_I", "INDEX"),
            "NIFTYPSUBANK":("33",     "IDX_I", "INDEX"),
            "NIFTYFIN":     ("27",     "IDX_I", "INDEX"),
            "NIFTYMEDIA":   ("30",    "IDX_I", "INDEX"),
            # Indices (BSE - also use IDX_I segment)
            "SENSEX":       ("51",     "IDX_I", "INDEX"),
            # Equities (NSE)
            "RELIANCE":     ("2885",  "NSE_EQ", "EQUITY"),
            "TCS":          ("11536", "NSE_EQ", "EQUITY"),
            "HDFCBANK":     ("1333",  "NSE_EQ", "EQUITY"),
            "INFY":         ("1594",  "NSE_EQ", "EQUITY"),
            "ICICIBANK":    ("4963",  "NSE_EQ", "EQUITY"),
            "SBIN":         ("3045",  "NSE_EQ", "EQUITY"),
            "BHARTIARTL":   ("10604", "NSE_EQ", "EQUITY"),
            "KOTAKBANK":    ("1922",  "NSE_EQ", "EQUITY"),
            "BAJFINANCE":   ("317",   "NSE_EQ", "EQUITY"),
            "HINDUNILVR":   ("1394",  "NSE_EQ", "EQUITY"),
        }
        # Keep backward compat token map for any code referencing it directly
        self._symbol_token_map = {k: v[0] for k, v in self._symbol_info.items()}
        
        self.pin = os.getenv("DHAN_PIN")
        self.totp_secret = os.getenv("DHAN_TOTP_SECRET")
        self._renewal_thread = None
        self.token_expires_at = None
        self.env_path = None

        if self.api_token and self.client_id:
            self.is_connected = True
            logger.info("Dhan API initialized successfully from environment variables")
            # Parse token expiry from JWT
            self._parse_token_expiry()
            # Start token renewal if PIN+TOTP are configured
            if self.pin and self.totp_secret:
                self.start_token_renewal_background()
            elif self.api_token:
                logger.info("DHAN_PIN and DHAN_TOTP_SECRET not set — token will not auto-renew. Set them in .env for auto-renewal.")
        else:
            logger.warning("Dhan API credentials (DHAN_API_TOKEN or DHAN_CLIENT_ID) not found. running in fallback/inactive state.")

    def _parse_token_expiry(self):
        """Extract token expiry from JWT payload"""
        try:
            parts = self.api_token.split('.')
            if len(parts) >= 2:
                payload = parts[1]
                padding = 4 - (len(payload) % 4)
                if padding != 4:
                    payload += '=' * padding
                import base64
                decoded = json.loads(base64.b64decode(payload))
                exp = decoded.get('exp')
                if exp:
                    self.token_expires_at = datetime.fromtimestamp(exp)
                    remaining = (self.token_expires_at - datetime.now()).total_seconds()
                    logger.info(f"Dhan token expires at {self.token_expires_at} ({remaining/3600:.1f}h remaining)")
        except Exception as e:
            logger.warning(f"Could not parse Dhan token expiry: {e}")

    def renew_token(self) -> bool:
        """Renew Dhan API token using PIN + TOTP flow. Returns True if successful."""
        if not self.pin or not self.totp_secret:
            logger.error("Cannot renew Dhan token: DHAN_PIN and DHAN_TOTP_SECRET not set")
            return False
        try:
            import pyotp
            totp = pyotp.TOTP(self.totp_secret).now()
            url = f"https://auth.dhan.co/app/generateAccessToken?dhanClientId={self.client_id}&pin={self.pin}&totp={totp}"
            response = requests.post(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                new_token = data.get("accessToken")
                if new_token:
                    old_token = self.api_token
                    self.api_token = new_token
                    self._parse_token_expiry()
                    logger.info(f"Dhan token renewed successfully — expires at {self.token_expires_at}")
                    # Update .env with new token
                    self._update_env_token(new_token)
                    return True
                else:
                    logger.error(f"Dhan token renewal: no accessToken in response: {data}")
            else:
                logger.error(f"Dhan token renewal failed: {response.status_code} {response.text[:200]}")
        except Exception as e:
            logger.error(f"Dhan token renewal exception: {e}")
        return False

    def _update_env_token(self, new_token: str):
        """Persist the new token in .env file"""
        try:
            # Find .env file
            if not self.env_path:
                candidates = [Path.cwd() / '.env', Path(__file__).parent / '.env', Path(__file__).parent.parent / '.env']
                for c in candidates:
                    if c.exists():
                        self.env_path = c
                        break
            if not self.env_path:
                return
            content = self.env_path.read_text(encoding='utf-8')
            if 'DHAN_API_TOKEN=' in content:
                content = re.sub(r'^DHAN_API_TOKEN=.*$', f'DHAN_API_TOKEN={new_token}', content, flags=re.MULTILINE)
            else:
                content += f'\nDHAN_API_TOKEN={new_token}\n'
            self.env_path.write_text(content, encoding='utf-8')
            logger.info(f"Updated DHAN_API_TOKEN in {self.env_path}")
        except Exception as e:
            logger.warning(f"Failed to update .env with new token: {e}")

    def start_token_renewal_background(self):
        """Start a background thread that renews the token every 23 hours (1h before expiry)"""
        if self._renewal_thread and self._renewal_thread.is_alive():
            return

        def renewal_loop():
            while self.is_connected:
                try:
                    if self.token_expires_at:
                        remaining = (self.token_expires_at - datetime.now()).total_seconds()
                        # Renew 1 hour before expiry or every 23 hours
                        wait = max(60, min(remaining - 3600, 23 * 3600))
                    else:
                        wait = 23 * 3600
                    
                    if wait > 0:
                        logger.info(f"Dhan token renewal sleeping for {wait/3600:.1f}h")
                        time.sleep(wait)
                    
                    if self.is_connected:
                        self.renew_token()
                except Exception as e:
                    logger.error(f"Dhan token renewal loop error: {e}")
                    time.sleep(300)

        self._renewal_thread = threading.Thread(target=renewal_loop, daemon=True, name="dhan-token-renewal")
        self._renewal_thread.start()
        logger.info("Dhan token auto-renewal background thread started")

    def is_active(self) -> bool:
        """Check if Dhan API client is fully configured and connected"""
        if not self.is_connected:
            return False
        # Verify with a lightweight profile check (once at startup)
        if not hasattr(self, '_verified'):
            self._verified = True
            try:
                profile = self.get_profile()
                if profile and ("dhanClientId" in profile or "clientName" in profile or profile.get("status") == "success"):
                    logger.info(f"Dhan API connection verified successfully — client: {profile.get('dhanClientId', '?')}, valid until: {profile.get('tokenValidity', '?')}")
                else:
                    logger.warning(f"Dhan API credentials present but profile response invalid: {str(profile)[:200]} — disabling")
                    self.is_connected = False
            except Exception as e:
                logger.warning(f"Dhan API verification failed: {e} — disabling")
                self.is_connected = False
        return self.is_connected

    def set_demo_mode(self, enabled: bool):
        """Switch between demo (paper) and live mode"""
        self.demo_mode = enabled
        logger.info(f"DhanAPI demo_mode set to: {enabled}")

    def generate_session(self) -> bool:
        """Verify session by making a light profile request"""
        if not self.is_connected or not self.api_token:
            return False
        try:
            profile = self.get_profile()
            if profile and "status" in profile and profile["status"] == "success":
                logger.info("Dhan API Session validated successfully")
                return True
            # Also accept if we get valid keys/data dictionary
            if profile and ("clientName" in profile or "data" in profile):
                logger.info("Dhan API Session validated successfully")
                return True
        except Exception as e:
            logger.error(f"Error generating Dhan session: {str(e)}")
        return False

    def _get_headers(self) -> Dict[str, str]:
        return {
            "access-token": self.api_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def get_profile(self) -> Dict:
        """Retrieve user profile from Dhan API"""
        if not self.is_connected:
            return {}
        try:
            url = f"{self.base_url}/v2/profile"
            response = requests.get(url, headers=self._get_headers(), timeout=5.0)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Dhan get_profile failed: {response.text}")
        except Exception as e:
            logger.error(f"Dhan get_profile exception: {str(e)}")
        return {}

    def get_funds(self) -> Dict:
        """Get account margins and funds"""
        if self.demo_mode:
            return {
                "status": "success",
                "availableLimit": 100000.00,
                "utilizedLimit": 0.00
            }
        if not self.is_connected:
            return {}
        try:
            url = f"{self.base_url}/v2/fundlimit"
            response = requests.get(url, headers=self._get_headers(), timeout=5.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Dhan get_funds exception: {str(e)}")
        return {}

    def get_holdings(self) -> List:
        """Get retail stock holdings"""
        if self.demo_mode:
            return []
        if not self.is_connected:
            return []
        try:
            url = f"{self.base_url}/v2/holdings"
            response = requests.get(url, headers=self._get_headers(), timeout=5.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Dhan get_holdings exception: {str(e)}")
        return []

    def get_positions(self) -> List:
        """Get net open positions"""
        if self.demo_mode:
            return []
        if not self.is_connected:
            return []
        try:
            url = f"{self.base_url}/v2/positions"
            response = requests.get(url, headers=self._get_headers(), timeout=5.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Dhan get_positions exception: {str(e)}")
        return []

    def get_historical_data(self, symbol: str, interval: str = "1D", days_back: int = 30) -> pd.DataFrame:
        """Fetch historical chart candles from Dhan Charts API"""
        if not self.is_connected:
            return pd.DataFrame()
            
        clean_symbol = symbol.replace('.NS', '').upper()
        
        # Look up symbol info; default to NIFTY50 if not found
        info = self._symbol_info.get(clean_symbol, ("13", "NSE_INDICES", "INDEX"))
        security_id, exchange_segment, instrument_type = info
        
        # Dhan Charts API Endpoint
        url = f"{self.base_url}/v2/charts/historical"
        
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days_back)
        
        # Map interval to Dhan format
        interval_map = {
            "1": "1", "1m": "1", "1MIN": "1",
            "5": "5", "5m": "5", "5MIN": "5",
            "15": "15", "15m": "15", "15MIN": "15",
            "30": "30", "30m": "30", "30MIN": "30",
            "60": "60", "1H": "60", "60MIN": "60",
            "1D": "1D", "DAY": "1D", "1DAY": "1D",
        }
        dhan_interval = interval_map.get(interval.upper(), "1D")
        
        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "instrument": instrument_type,
            "expiryCode": 0,
            "fromDate": from_date.strftime("%Y-%m-%d"),
            "toDate": to_date.strftime("%Y-%m-%d")
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=5.0)
            if response.status_code == 200:
                res_data = response.json()
                candles = res_data.get("data", {})
                if candles and "t" in candles:
                    df = pd.DataFrame({
                        "timestamp": pd.to_datetime(candles["t"], unit='s'),
                        "Open": candles["o"],
                        "High": candles["h"],
                        "Low": candles["l"],
                        "Close": candles["c"],
                        "Volume": candles["v"]
                    })
                    df.set_index("timestamp", inplace=True)
                    logger.info(f"Successfully retrieved {len(df)} candles from Dhan for {symbol}")
                    return df
                else:
                    logger.warning(f"Dhan returned empty candle data for {symbol}: {str(res_data)[:200]}")
            else:
                logger.warning(f"Dhan historical chart API failed for {symbol}: {response.text[:200]}")
        except Exception as e:
            logger.error(f"Dhan get_historical_data exception for {symbol}: {str(e)}")
            
        return pd.DataFrame()

    def get_quote(self, symbols: List[str]) -> Dict:
        """Get current market quote prices"""
        if not self.is_connected:
            return {}
        try:
            url = f"{self.base_url}/v2/marketfeed/ltp"
            token_list = []
            for s in symbols:
                clean = s.replace('.NS', '').upper()
                info = self._symbol_info.get(clean, ("500325", "NSE_EQ", "EQUITY"))
                security_id, exchange_segment, _ = info
                token_list.append({
                    "exchangeSegment": exchange_segment,
                    "securityId": security_id
                })
            
            payload = {"instruments": token_list}
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=3.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Dhan get_quote exception: {str(e)}")
        return {}

    def place_order(self, symbol: str, quantity: int, transaction_type: str, 
                    product_type: str = "INTRADAY", price: float = None) -> Dict:
        """Place trading order at Dhan"""
        if self.demo_mode:
            logger.info(f"[DEMO] Simulated Dhan Order placed for {symbol}: {transaction_type} {quantity} shares")
            return {
                "status": "success",
                "data": {"orderId": f"DHAN_DEMO_{int(datetime.now().timestamp())}"}
            }
            
        if not self.is_connected:
            return {"status": "failure", "error": "Dhan API is not connected"}
            
        clean_symbol = symbol.replace('.NS', '').upper()
        info = self._symbol_info.get(clean_symbol, ("500325", "NSE_EQ", "EQUITY"))
        security_id, exchange_segment, _ = info
        
        url = f"{self.base_url}/v2/orders"
        
        payload = {
            "dhanClientId": self.client_id,
            "correlationId": f"auto_{int(datetime.now().timestamp())}",
            "transactionType": "BUY" if transaction_type.upper() in ["BUY", "CALL"] else "SELL",
            "exchangeSegment": exchange_segment,
            "productType": "INTRADAY" if product_type == "INTRADAY" else "CNC",
            "orderType": "MARKET" if not price else "LIMIT",
            "validity": "DAY",
            "securityId": security_id,
            "quantity": int(quantity),
            "price": float(price) if price else 0.0
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=5.0)
            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "failure", "error": response.text}
        except Exception as e:
            logger.error(f"Dhan place_order exception: {str(e)}")
            return {"status": "failure", "error": str(e)}

    def cancel_order(self, order_id: str) -> Dict:
        """Cancel a pending order"""
        if not self.is_connected:
            return {}
        try:
            url = f"{self.base_url}/v2/orders/{order_id}"
            response = requests.delete(url, headers=self._get_headers(), timeout=5.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Dhan cancel_order exception: {str(e)}")
        return {}

# Global singleton client
dhan_client = DhanAPI()
