# Indian-Only Angel One App

A minimal Flask app focused only on Indian markets via Angel One SmartAPI.

## Prerequisites
- Python 3.9+
- `pip install -r requirements.txt` (root project requirements already include smartapi, pyotp, etc.)
- Angel One SmartAPI credentials

## Environment
Create/update `.env` in project root:

```
ANGEL_ONE_API_KEY=your_api_key
ANGEL_ONE_CLIENT_CODE=your_client_id
ANGEL_ONE_PASSWORD=your_mpin_or_password
ANGEL_ONE_TOTP_SECRET=your_totp_secret

# Ensure other systems are off
DISABLE_OTC=1
DISABLE_FOREX=1
INDIAN_AUTOTRADE_ENABLED=0
```

## Run
From project root:

```
python indian_only/app.py
```

The app will start on port 5001 by default.

## Endpoints
- GET `/status` → connection status and available pairs
- GET `/market_data/<pair>?interval=1d&period=30d` → historical candles

Pairs include: `NIFTY50`, `BANKNIFTY`, `SENSEX`, `FINNIFTY`, `MIDCPNIFTY`, sector indices, and large-cap stocks.

## Notes
- NIFTY50 uses `NSE_INDICES` and a wider 30-day window to avoid empty responses.
- If you see empty results, try `interval=1m&period=1d` or retry after a short delay.
