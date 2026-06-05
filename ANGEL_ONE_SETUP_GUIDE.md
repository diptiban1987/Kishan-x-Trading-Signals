# Angel One SmartAPI Integration Setup Guide

This guide explains how to set up and use the Angel One SmartAPI integration in the Kishan-x Trading Signals application.

## Overview

The Angel One integration has been updated to use the official SmartAPI Python library from [https://github.com/angel-one/smartapi-python](https://github.com/angel-one/smartapi-python). This provides better reliability, official support, and access to all Angel One API features.

## Prerequisites

1. **Angel One Account**: You need an active Angel One trading account
2. **API Credentials**: Obtain your API credentials from Angel One
3. **Python Environment**: Python 3.7+ with required packages

## Installation

### 1. Install Required Packages

The required packages are already added to `requirements.txt`. Install them using:

```bash
pip install -r requirements.txt
```

Or install individually:

```bash
pip install smartapi-python pyotp logzero websocket-client pycryptodome
```

### 2. Get Angel One API Credentials

1. Log in to your Angel One account
2. Go to Settings → API Settings
3. Generate API Key and get your credentials:
   - **API Key**: Your unique API key
   - **Client Code**: Your Angel One client ID
   - **Password**: Your trading password
   - **TOTP Secret**: Your 2FA secret key (QR code value)

## Configuration

### Method 1: .env File (Recommended)

The easiest way is to use the `.env` file. A template has already been created for you:

1. **Edit the `.env` file** in your project root directory
2. **Replace the placeholder values** with your actual Angel One credentials:

```bash
# Angel One API Credentials
ANGEL_ONE_API_KEY=your_actual_api_key_here
ANGEL_ONE_CLIENT_CODE=your_actual_client_code_here
ANGEL_ONE_PASSWORD=your_actual_password_here
ANGEL_ONE_TOTP_SECRET=your_actual_totp_secret_here
```

3. **Save the file** - the application will automatically load these credentials on startup

### Method 2: Environment Variables

Alternatively, you can set environment variables:

```bash
# Windows (PowerShell)
$env:ANGEL_ONE_API_KEY="your_api_key_here"
$env:ANGEL_ONE_CLIENT_CODE="your_client_code_here"
$env:ANGEL_ONE_PASSWORD="your_password_here"
$env:ANGEL_ONE_TOTP_SECRET="your_totp_secret_here"

# Windows (Command Prompt)
set ANGEL_ONE_API_KEY=your_api_key_here
set ANGEL_ONE_CLIENT_CODE=your_client_code_here
set ANGEL_ONE_PASSWORD=your_password_here
set ANGEL_ONE_TOTP_SECRET=your_totp_secret_here

# Linux/Mac
export ANGEL_ONE_API_KEY="your_api_key_here"
export ANGEL_ONE_CLIENT_CODE="your_client_code_here"
export ANGEL_ONE_PASSWORD="your_password_here"
export ANGEL_ONE_TOTP_SECRET="your_totp_secret_here"
```

### Method 3: Web Interface

1. Start the application: `python app.py`
2. Go to the Angel One configuration page
3. Enter your credentials in the web form
4. Click "Configure Angel One API"

## Features

### 1. Real-time Market Data
- Live price quotes for Indian stocks and indices
- Historical data with multiple timeframes
- Market status and indices information

### 2. Trading Operations
- Place buy/sell orders
- Modify existing orders
- Cancel orders
- View order book and trade book

### 3. Portfolio Management
- View current holdings
- Check available funds
- Monitor positions
- Get user profile information

### 4. WebSocket Support
- Real-time data streaming
- Order update notifications
- Live market feeds

## Usage Examples

### Basic API Usage

```python
from angel_one_api import AngelOneAPI, AngelOneDataProvider

# Initialize API
api = AngelOneAPI(
    api_key="your_api_key",
    client_id="your_client_code", 
    password="your_password",
    totp_secret="your_totp_secret"
)

# Generate session
if api.generate_session():
    print("Connected to Angel One API")
    
    # Get real-time quote
    quote = api.get_quote(["NIFTY50", "RELIANCE"])
    print(f"Quotes: {quote}")
    
    # Get historical data
    hist_data = api.get_historical_data(
        symbol="NIFTY50",
        interval="ONE_MINUTE",
        from_date="2024-01-01 09:15",
        to_date="2024-01-01 15:30"
    )
    print(f"Historical data: {len(hist_data)} records")
    
    # Place an order
    order_result = api.place_order(
        symbol="RELIANCE",
        quantity=1,
        order_type="BUY",
        product_type="INTRADAY",
        price=2500.0
    )
    print(f"Order result: {order_result}")
    
    # Terminate session
    api.terminate_session()
```

### Data Provider Usage

```python
from angel_one_api import AngelOneDataProvider

# Initialize data provider
data_provider = AngelOneDataProvider(api)

# Get real-time price
price_data = data_provider.get_real_time_price("NIFTY50")
print(f"Current price: {price_data['price']}")

# Get historical data
hist_data = data_provider.get_historical_data(
    symbol="NIFTY50",
    interval="1d",
    period="1mo"
)
print(f"Historical data: {len(hist_data)} records")

# Check market status
is_open = data_provider.is_market_open()
print(f"Market is {'open' if is_open else 'closed'}")
```

### WebSocket Usage

```python
from angel_one_api import AngelOneWebSocket

# Initialize WebSocket
ws = AngelOneWebSocket(api)

# Define callbacks
def on_data(wsapp, message):
    print(f"Received data: {message}")

def on_open(wsapp):
    print("WebSocket connected")
    
    # Subscribe to NIFTY50
    token_list = [{"exchangeType": 1, "tokens": ["26000"]}]
    ws.subscribe_to_tokens("test_123", 1, token_list)

def on_error(wsapp, error):
    print(f"WebSocket error: {error}")

def on_close(wsapp):
    print("WebSocket closed")

# Connect WebSocket
ws.connect_websocket(on_data, on_open, on_error, on_close)
```

## API Methods

### AngelOneAPI Class

| Method | Description | Parameters |
|--------|-------------|------------|
| `generate_session()` | Authenticate and generate session | None |
| `get_profile()` | Get user profile | None |
| `get_funds()` | Get available funds | None |
| `get_holdings()` | Get current holdings | None |
| `get_positions()` | Get current positions | None |
| `get_historical_data()` | Get historical price data | symbol, interval, from_date, to_date |
| `get_quote()` | Get real-time quotes | symbols list |
| `place_order()` | Place a trading order | symbol, quantity, order_type, product_type, price, trigger_price |
| `modify_order()` | Modify existing order | order_id, quantity, price, order_type |
| `cancel_order()` | Cancel an order | order_id |
| `get_order_book()` | Get order book | None |
| `get_trade_book()` | Get trade book | None |
| `get_market_status()` | Get market status | None |
| `get_indices()` | Get market indices | None |
| `terminate_session()` | End session | None |

### AngelOneDataProvider Class

| Method | Description | Parameters |
|--------|-------------|------------|
| `get_real_time_price()` | Get real-time price for symbol | symbol |
| `get_historical_data()` | Get historical data with caching | symbol, interval, period |
| `is_market_open()` | Check if market is open | None |

## Error Handling

The API includes comprehensive error handling:

```python
try:
    api = AngelOneAPI(api_key, client_id, password, totp_secret)
    if api.generate_session():
        # API operations
        pass
    else:
        print("Failed to connect to Angel One API")
except Exception as e:
    print(f"Error: {e}")
```

## Testing

The integration includes a mock API for testing without real credentials:

```python
from angel_one_api import MockAngelOneAPI

# Use mock API for testing
mock_api = MockAngelOneAPI()
mock_api.generate_session()

# All methods work the same way
quote = mock_api.get_quote(["NIFTY50"])
```

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Check your API credentials
   - Ensure TOTP secret is correct
   - Verify your account is active

2. **Connection Errors**
   - Check internet connection
   - Verify API endpoints are accessible
   - Check for firewall restrictions

3. **Order Placement Errors**
   - Ensure sufficient funds
   - Check market hours
   - Verify symbol tokens

4. **WebSocket Connection Issues**
   - Check feed token validity
   - Ensure proper authentication
   - Verify network connectivity

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Notes

1. **Never commit credentials** to version control
2. **Use environment variables** for production
3. **Rotate API keys** regularly
4. **Monitor API usage** for unusual activity
5. **Use HTTPS** for all API communications

## Support

- **Official Documentation**: [Angel One SmartAPI Docs](https://smartapi.angelbroking.com/)
- **GitHub Repository**: [smartapi-python](https://github.com/angel-one/smartapi-python)
- **API Support**: Contact Angel One support for API-related issues

## Changelog

### Version 2.0.0
- Updated to use official SmartAPI Python library
- Added WebSocket support for real-time data
- Improved error handling and logging
- Added comprehensive documentation
- Enhanced mock API for testing

### Previous Version
- Custom API implementation
- Limited functionality
- Basic error handling
