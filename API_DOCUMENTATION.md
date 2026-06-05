# 📡 API Documentation - KishanX Trading Signals

## 📋 Table of Contents
- [Overview](#overview)
- [Authentication](#authentication)
- [Base URL](#base-url)
- [Response Format](#response-format)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [Trading Endpoints](#trading-endpoints)
- [Data Endpoints](#data-endpoints)
- [Portfolio Endpoints](#portfolio-endpoints)
- [Admin Endpoints](#admin-endpoints)
- [WebSocket Events](#websocket-events)
- [Code Examples](#code-examples)
- [SDK Examples](#sdk-examples)

## 🎯 Overview

The KishanX Trading Signals API provides comprehensive access to trading functionality, market data, portfolio management, and system administration. The API is RESTful and supports both JSON and WebSocket connections for real-time data.

### Key Features
- **RESTful API**: Standard HTTP methods and status codes
- **Real-Time Data**: WebSocket support for live updates
- **Authentication**: Secure token-based authentication
- **Rate Limiting**: Built-in rate limiting protection
- **Comprehensive**: Full trading system functionality
- **Well Documented**: Detailed endpoint documentation

## 🔐 Authentication

### Authentication Methods

#### Session-Based Authentication (Default)
```http
POST /login
Content-Type: application/json

{
    "username": "your_username",
    "password": "your_password"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Login successful",
    "user": {
        "id": 1,
        "username": "admin",
        "role": "admin",
        "balance": 100000.00
    },
    "session_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

#### API Key Authentication (Optional)
```http
GET /api/data
Authorization: Bearer your_api_key
```

### Session Management
- **Session Duration**: 24 hours (configurable)
- **Auto-Renewal**: Sessions auto-renew on activity
- **Logout**: Explicit logout invalidates session
- **Security**: IP binding and secure cookies

## 🌐 Base URL

### Development
```
http://localhost:5000
```

### Production
```
https://your-domain.com
```

### API Versioning
All API endpoints are prefixed with `/api/v1/` (version 1 is current)

## 📊 Response Format

### Success Response
```json
{
    "success": true,
    "data": {
        // Response data
    },
    "message": "Operation successful",
    "timestamp": "2024-01-01T12:00:00Z"
}
```

### Error Response
```json
{
    "success": false,
    "error": {
        "code": "ERROR_CODE",
        "message": "Error description",
        "details": "Additional error details"
    },
    "timestamp": "2024-01-01T12:00:00Z"
}
```

### Pagination
```json
{
    "success": true,
    "data": [...],
    "pagination": {
        "page": 1,
        "per_page": 50,
        "total": 150,
        "pages": 3,
        "has_next": true,
        "has_prev": false
    }
}
```

## ⚠️ Error Handling

### HTTP Status Codes
- **200**: Success
- **201**: Created
- **400**: Bad Request
- **401**: Unauthorized
- **403**: Forbidden
- **404**: Not Found
- **429**: Rate Limited
- **500**: Internal Server Error

### Error Codes
- **AUTH_REQUIRED**: Authentication required
- **INVALID_CREDENTIALS**: Invalid username/password
- **INSUFFICIENT_BALANCE**: Insufficient account balance
- **INVALID_SYMBOL**: Invalid trading symbol
- **RATE_LIMITED**: Rate limit exceeded
- **SYSTEM_ERROR**: Internal system error

## 🚦 Rate Limiting

### Rate Limits
- **General API**: 100 requests per hour per IP
- **Trading API**: 50 requests per hour per user
- **Data API**: 200 requests per hour per user
- **Admin API**: 500 requests per hour per admin

### Rate Limit Headers
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

### Rate Limit Exceeded
```json
{
    "success": false,
    "error": {
        "code": "RATE_LIMITED",
        "message": "Rate limit exceeded",
        "retry_after": 3600
    }
}
```

## 🏪 Trading Endpoints

### Auto-Trading Management

#### Start Auto-Trading
```http
POST /api/indian/start-auto-trading
Content-Type: application/json
```

**Request Body:**
```json
{
    "strategy": "rsi",
    "symbols": ["NIFTY50", "BANKNIFTY", "RELIANCE"],
    "risk_per_trade": 2.0,
    "max_trades": 5,
    "stop_loss": 1.0,
    "take_profit": 2.0
}
```

**Response:**
```json
{
    "success": true,
    "message": "Auto-trading started successfully",
    "data": {
        "strategy": "rsi",
        "symbols": ["NIFTY50", "BANKNIFTY", "RELIANCE"],
        "risk_per_trade": 2.0,
        "max_trades": 5,
        "status": "running"
    }
}
```

#### Stop Auto-Trading
```http
POST /api/indian/stop-auto-trading
```

**Response:**
```json
{
    "success": true,
    "message": "Auto-trading stopped successfully",
    "data": {
        "status": "stopped",
        "active_trades": 0
    }
}
```

#### Get Trading Status
```http
GET /api/indian/status
```

**Response:**
```json
{
    "success": true,
    "data": {
        "status": "running",
        "strategy": "rsi",
        "active_trades": 3,
        "total_pnl": 1250.50,
        "win_rate": 75.5,
        "started_at": "2024-01-01T10:00:00Z"
    }
}
```

### Manual Trading

#### Execute Trade
```http
POST /api/trading/execute
Content-Type: application/json
```

**Request Body:**
```json
{
    "symbol": "NIFTY50",
    "side": "BUY",
    "quantity": 50,
    "price": 19500.00,
    "stop_loss": 19300.00,
    "take_profit": 19700.00,
    "strategy": "manual"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Trade executed successfully",
    "data": {
        "trade_id": "T123456",
        "symbol": "NIFTY50",
        "side": "BUY",
        "quantity": 50,
        "price": 19500.00,
        "status": "filled",
        "executed_at": "2024-01-01T12:00:00Z"
    }
}
```

#### Close Trade
```http
POST /api/trading/close/{trade_id}
```

**Response:**
```json
{
    "success": true,
    "message": "Trade closed successfully",
    "data": {
        "trade_id": "T123456",
        "close_price": 19650.00,
        "pnl": 7500.00,
        "closed_at": "2024-01-01T14:00:00Z"
    }
}
```

#### Get Active Trades
```http
GET /api/trading/active
```

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "trade_id": "T123456",
            "symbol": "NIFTY50",
            "side": "BUY",
            "quantity": 50,
            "entry_price": 19500.00,
            "current_price": 19650.00,
            "pnl": 7500.00,
            "stop_loss": 19300.00,
            "take_profit": 19700.00,
            "opened_at": "2024-01-01T12:00:00Z"
        }
    ]
}
```

### Trading Signals

#### Get Trading Signals
```http
GET /api/signals?symbol=NIFTY50&limit=10&strategy=rsi
```

**Query Parameters:**
- `symbol`: Trading symbol (optional)
- `strategy`: Strategy filter (optional)
- `limit`: Number of signals (default: 50)
- `offset`: Pagination offset (default: 0)

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "signal_id": "S123456",
            "symbol": "NIFTY50",
            "signal_type": "BUY",
            "confidence": 0.85,
            "entry_price": 19500.00,
            "target_price": 19700.00,
            "stop_loss": 19300.00,
            "strategy": "rsi",
            "timeframe": "1h",
            "created_at": "2024-01-01T12:00:00Z"
        }
    ],
    "pagination": {
        "page": 1,
        "per_page": 10,
        "total": 25,
        "pages": 3
    }
}
```

#### Create Custom Signal
```http
POST /api/signals
Content-Type: application/json
```

**Request Body:**
```json
{
    "symbol": "NIFTY50",
    "signal_type": "BUY",
    "confidence": 0.80,
    "entry_price": 19500.00,
    "target_price": 19700.00,
    "stop_loss": 19300.00,
    "strategy": "custom",
    "timeframe": "1h",
    "notes": "Custom analysis signal"
}
```

## 📊 Data Endpoints

### Market Data

#### Get Historical Data
```http
GET /api/market-data?symbol=NIFTY50&interval=1d&period=1y
```

**Query Parameters:**
- `symbol`: Trading symbol (required)
- `interval`: Data interval (1m, 5m, 15m, 1h, 4h, 1d)
- `period`: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
- `start_date`: Start date (YYYY-MM-DD)
- `end_date`: End date (YYYY-MM-DD)

**Response:**
```json
{
    "success": true,
    "data": {
        "symbol": "NIFTY50",
        "interval": "1d",
        "period": "1y",
        "candles": [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "open": 19500.00,
                "high": 19600.00,
                "low": 19450.00,
                "close": 19550.00,
                "volume": 1000000
            }
        ]
    }
}
```

#### Get Real-Time Data
```http
GET /api/market-data/realtime?symbols=NIFTY50,BANKNIFTY,RELIANCE
```

**Response:**
```json
{
    "success": true,
    "data": {
        "NIFTY50": {
            "price": 19550.00,
            "change": 50.00,
            "change_percent": 0.26,
            "volume": 1000000,
            "timestamp": "2024-01-01T12:00:00Z"
        },
        "BANKNIFTY": {
            "price": 44500.00,
            "change": 200.00,
            "change_percent": 0.45,
            "volume": 500000,
            "timestamp": "2024-01-01T12:00:00Z"
        }
    }
}
```

#### Get Technical Indicators
```http
GET /api/indicators?symbol=NIFTY50&indicators=rsi,macd,bollinger&period=20
```

**Response:**
```json
{
    "success": true,
    "data": {
        "symbol": "NIFTY50",
        "indicators": {
            "rsi": {
                "value": 65.5,
                "signal": "NEUTRAL",
                "overbought": false,
                "oversold": false
            },
            "macd": {
                "macd_line": 15.2,
                "signal_line": 12.8,
                "histogram": 2.4,
                "signal": "BULLISH"
            },
            "bollinger": {
                "upper_band": 19700.00,
                "middle_band": 19500.00,
                "lower_band": 19300.00,
                "price_position": "MIDDLE"
            }
        }
    }
}
```

### Symbol Management

#### Get Available Symbols
```http
GET /api/symbols?market=indian&category=stocks
```

**Query Parameters:**
- `market`: Market type (indian, global, forex)
- `category`: Symbol category (stocks, indices, options, forex)
- `search`: Search term (optional)

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "symbol": "NIFTY50",
            "name": "NIFTY 50",
            "market": "indian",
            "category": "indices",
            "exchange": "NSE",
            "currency": "INR"
        },
        {
            "symbol": "RELIANCE",
            "name": "Reliance Industries",
            "market": "indian",
            "category": "stocks",
            "exchange": "NSE",
            "currency": "INR"
        }
    ]
}
```

## 💼 Portfolio Endpoints

### Portfolio Summary
```http
GET /api/portfolio/summary
```

**Response:**
```json
{
    "success": true,
    "data": {
        "total_balance": 100000.00,
        "available_balance": 75000.00,
        "invested_amount": 25000.00,
        "total_pnl": 2500.00,
        "today_pnl": 500.00,
        "win_rate": 75.5,
        "total_trades": 20,
        "winning_trades": 15,
        "losing_trades": 5,
        "max_drawdown": -1500.00,
        "sharpe_ratio": 1.25
    }
}
```

### Portfolio History
```http
GET /api/portfolio/history?period=1y&interval=daily
```

**Query Parameters:**
- `period`: Time period (1d, 1w, 1m, 3m, 6m, 1y, all)
- `interval`: Data interval (hourly, daily, weekly, monthly)

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "date": "2024-01-01",
            "balance": 100000.00,
            "pnl": 0.00,
            "pnl_percent": 0.00,
            "trades": 0
        },
        {
            "date": "2024-01-02",
            "balance": 101250.00,
            "pnl": 1250.00,
            "pnl_percent": 1.25,
            "trades": 2
        }
    ]
}
```

### Trade History
```http
GET /api/trades?status=completed&limit=50&offset=0
```

**Query Parameters:**
- `status`: Trade status (active, completed, cancelled)
- `symbol`: Filter by symbol
- `strategy`: Filter by strategy
- `start_date`: Start date filter
- `end_date`: End date filter
- `limit`: Number of trades (default: 50)
- `offset`: Pagination offset (default: 0)

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "trade_id": "T123456",
            "symbol": "NIFTY50",
            "side": "BUY",
            "quantity": 50,
            "entry_price": 19500.00,
            "exit_price": 19650.00,
            "pnl": 7500.00,
            "pnl_percent": 0.77,
            "strategy": "rsi",
            "opened_at": "2024-01-01T12:00:00Z",
            "closed_at": "2024-01-01T14:00:00Z",
            "status": "completed"
        }
    ],
    "pagination": {
        "page": 1,
        "per_page": 50,
        "total": 150,
        "pages": 3
    }
}
```

## 🎛️ Admin Endpoints

### System Status
```http
GET /api/admin/system-status
```

**Response:**
```json
{
    "success": true,
    "data": {
        "system_health": "healthy",
        "uptime": 86400,
        "cpu_usage": 45.2,
        "memory_usage": 67.8,
        "disk_usage": 23.5,
        "active_users": 15,
        "active_trades": 3,
        "data_feed_status": "active",
        "last_backup": "2024-01-01T02:00:00Z"
    }
}
```

### Performance Metrics
```http
GET /api/admin/performance-metrics
```

**Response:**
```json
{
    "success": true,
    "data": {
        "response_time_avg": 150.5,
        "response_time_p95": 300.2,
        "requests_per_minute": 45.8,
        "error_rate": 0.02,
        "cache_hit_rate": 85.3,
        "database_connections": 5,
        "memory_usage": {
            "current": 512.5,
            "peak": 768.2,
            "limit": 1024.0
        }
    }
}
```

### Cache Management
```http
POST /api/admin/clear-cache
Content-Type: application/json
```

**Request Body:**
```json
{
    "cache_type": "all",
    "symbols": ["NIFTY50", "BANKNIFTY"]
}
```

**Response:**
```json
{
    "success": true,
    "message": "Cache cleared successfully",
    "data": {
        "cleared_files": 25,
        "freed_space": "15.2 MB"
    }
}
```

### User Management
```http
GET /api/admin/users?role=user&status=active
```

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "user_id": 1,
            "username": "user1",
            "email": "user1@example.com",
            "role": "user",
            "status": "active",
            "balance": 50000.00,
            "last_login": "2024-01-01T10:00:00Z",
            "created_at": "2023-12-01T00:00:00Z"
        }
    ]
}
```

## 🔌 WebSocket Events

### Connection
```javascript
const socket = io('http://localhost:5000');

socket.on('connect', () => {
    console.log('Connected to WebSocket');
});
```

### Real-Time Data
```javascript
// Subscribe to market data
socket.emit('subscribe', {
    type: 'market_data',
    symbols: ['NIFTY50', 'BANKNIFTY']
});

// Listen for market data updates
socket.on('market_data_update', (data) => {
    console.log('Market data:', data);
});
```

### Trading Events
```javascript
// Listen for trade updates
socket.on('trade_update', (data) => {
    console.log('Trade update:', data);
});

// Listen for signal updates
socket.on('signal_update', (data) => {
    console.log('New signal:', data);
});
```

### Portfolio Updates
```javascript
// Listen for portfolio updates
socket.on('portfolio_update', (data) => {
    console.log('Portfolio update:', data);
});
```

## 💻 Code Examples

### Python Example
```python
import requests
import json

# Base URL
BASE_URL = "http://localhost:5000"

# Login
login_data = {
    "username": "admin",
    "password": "admin123"
}

response = requests.post(f"{BASE_URL}/login", json=login_data)
session_token = response.json()["session_token"]

# Set up session
session = requests.Session()
session.cookies.set("session", session_token)

# Get portfolio summary
response = session.get(f"{BASE_URL}/api/portfolio/summary")
portfolio = response.json()
print(f"Total Balance: {portfolio['data']['total_balance']}")

# Start auto-trading
trading_data = {
    "strategy": "rsi",
    "symbols": ["NIFTY50", "BANKNIFTY"],
    "risk_per_trade": 2.0,
    "max_trades": 5
}

response = session.post(f"{BASE_URL}/api/indian/start-auto-trading", json=trading_data)
print(response.json()["message"])
```

### JavaScript Example
```javascript
// Login
async function login(username, password) {
    const response = await fetch('/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
    });
    
    const data = await response.json();
    return data.session_token;
}

// Get market data
async function getMarketData(symbol) {
    const response = await fetch(`/api/market-data?symbol=${symbol}&interval=1d&period=1y`);
    const data = await response.json();
    return data.data;
}

// Start auto-trading
async function startAutoTrading(strategy, symbols) {
    const response = await fetch('/api/indian/start-auto-trading', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            strategy,
            symbols,
            risk_per_trade: 2.0,
            max_trades: 5
        })
    });
    
    const data = await response.json();
    return data;
}

// Usage
login('admin', 'admin123').then(token => {
    console.log('Logged in successfully');
    
    getMarketData('NIFTY50').then(data => {
        console.log('Market data:', data);
    });
    
    startAutoTrading('rsi', ['NIFTY50', 'BANKNIFTY']).then(result => {
        console.log('Auto-trading started:', result.message);
    });
});
```

### cURL Examples
```bash
# Login
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Get portfolio summary
curl -X GET http://localhost:5000/api/portfolio/summary \
  -H "Cookie: session=your_session_token"

# Start auto-trading
curl -X POST http://localhost:5000/api/indian/start-auto-trading \
  -H "Content-Type: application/json" \
  -H "Cookie: session=your_session_token" \
  -d '{
    "strategy": "rsi",
    "symbols": ["NIFTY50", "BANKNIFTY"],
    "risk_per_trade": 2.0,
    "max_trades": 5
  }'

# Get market data
curl -X GET "http://localhost:5000/api/market-data?symbol=NIFTY50&interval=1d&period=1y" \
  -H "Cookie: session=your_session_token"
```

## 📚 SDK Examples

### Python SDK
```python
from kishanx_sdk import KishanXClient

# Initialize client
client = KishanXClient(
    base_url="http://localhost:5000",
    username="admin",
    password="admin123"
)

# Get portfolio summary
portfolio = client.portfolio.get_summary()
print(f"Balance: {portfolio.total_balance}")

# Start auto-trading
result = client.trading.start_auto_trading(
    strategy="rsi",
    symbols=["NIFTY50", "BANKNIFTY"],
    risk_per_trade=2.0,
    max_trades=5
)
print(result.message)

# Get market data
data = client.market.get_historical_data(
    symbol="NIFTY50",
    interval="1d",
    period="1y"
)
print(f"Data points: {len(data.candles)}")
```

### JavaScript SDK
```javascript
import { KishanXClient } from 'kishanx-sdk';

// Initialize client
const client = new KishanXClient({
    baseUrl: 'http://localhost:5000',
    username: 'admin',
    password: 'admin123'
});

// Get portfolio summary
const portfolio = await client.portfolio.getSummary();
console.log(`Balance: ${portfolio.totalBalance}`);

// Start auto-trading
const result = await client.trading.startAutoTrading({
    strategy: 'rsi',
    symbols: ['NIFTY50', 'BANKNIFTY'],
    riskPerTrade: 2.0,
    maxTrades: 5
});
console.log(result.message);

// Get market data
const data = await client.market.getHistoricalData({
    symbol: 'NIFTY50',
    interval: '1d',
    period: '1y'
});
console.log(`Data points: ${data.candles.length}`);
```

---

**📝 Note**: This API documentation covers the main endpoints and functionality. For the most up-to-date information, always refer to the live API documentation at `/api/docs` when the server is running.
