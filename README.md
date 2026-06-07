# 🚀 Auto Trading Platform Signals - Complete Trading Platform

## 📋 Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Admin Panel](#admin-panel)
- [Trading Systems](#trading-systems)
- [Security](#security)
- [Deployment](#deployment)
- [Support](#support)

## 🎯 Overview

KishanX Trading Signals is a comprehensive, production-ready auto-trading platform designed for both Indian and global markets. The system provides real-time market analysis, automated trading strategies, risk management, and advanced portfolio analytics.

### Key Highlights
- **Multi-Market Support**: Indian (NSE/BSE) and Global markets
- **Auto-Trading**: Fully automated trading with multiple strategies
- **Real-Time Data**: Live market data from multiple sources
- **Risk Management**: Advanced position sizing and risk controls
- **Admin Panel**: Complete system management interface
- **Mobile Responsive**: Works on all devices
- **Production Ready**: Enterprise-level security and reliability

## ✨ Features

### 🏪 Trading Systems
- **Indian Trading System**: Specialized for NIFTY, BANKNIFTY, and Indian stocks
- **Global Trading System**: Support for US stocks, ETFs, and forex
- **Auto-Trading**: Automated trade execution with multiple strategies
- **Manual Trading**: Manual trade execution with real-time analysis

### 📊 Market Analysis
- **Technical Indicators**: RSI, MACD, Bollinger Bands, Moving Averages
- **Real-Time Data**: Live market data from Angel One, Yahoo Finance, Alpha Vantage
- **Signal Generation**: AI-powered trading signals with confidence scores
- **Portfolio Analytics**: Comprehensive P&L tracking and performance metrics

### 🛡️ Risk Management
- **Position Sizing**: Automatic position sizing based on risk parameters
- **Stop Loss/Take Profit**: Automated trade management
- **Portfolio Limits**: Maximum exposure and drawdown controls
- **Real-Time Monitoring**: Live risk metrics and alerts

### 🔧 System Features
- **Caching System**: Intelligent data caching for performance
- **Rate Limiting**: API call optimization and protection
- **Backup System**: Automated backups and recovery
- **Notification System**: Multi-channel alerts and notifications
- **Performance Monitoring**: Real-time system health monitoring

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Windows/Linux/macOS
- Internet connection for market data

### 1. Clone the Repository
```bash
git clone <repository-url>
cd KishanX-Trading-Signals
```

### 2. Install Dependencies
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Initialize Database
```bash
python database_setup.py
```

### 4. Run the Application
```bash
python app.py
```

### 5. Access the Platform
- **Main Dashboard**: http://localhost:5000
- **Admin Panel**: http://localhost:5000/admin_panel
- **Default Login**: admin / admin123

## 📦 Installation

### Detailed Installation Steps

1. **System Requirements**
   - Python 3.8+
   - 4GB RAM minimum
   - 2GB free disk space
   - Internet connection

2. **Environment Setup**
   ```bash
   # Create project directory
   mkdir kishanx-trading
   cd kishanx-trading
   
   # Clone repository
   git clone <repository-url> .
   
   # Create virtual environment
   python -m venv venv
   
   # Activate virtual environment
   # Windows:
   venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Database Setup**
   ```bash
   python database_setup.py
   ```

5. **Configuration**
   ```bash
   # Copy environment template
   cp .env.example .env
   
   # Edit configuration
   notepad .env  # Windows
   nano .env     # Linux/macOS
   ```

## ⚙️ Configuration

### Environment Variables (.env)
```env
# Database Configuration
DATABASE_URL=sqlite:///kishanx.db

# API Keys
ANGEL_ONE_API_KEY=your_angel_one_key
ANGEL_ONE_CLIENT_ID=your_client_id
ANGEL_ONE_PIN=your_pin
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key

# Trading Configuration
DEFAULT_BALANCE=100000
MAX_RISK_PER_TRADE=2.0
DEFAULT_STOP_LOSS=1.0
DEFAULT_TAKE_PROFIT=2.0

# System Configuration
DEBUG=False
SECRET_KEY=your_secret_key
CACHE_DURATION=300
RATE_LIMIT_REQUESTS=100
```

### Trading Parameters
- **Default Balance**: ₹100,000 (configurable)
- **Max Risk Per Trade**: 2% of portfolio
- **Default Stop Loss**: 1% below entry
- **Default Take Profit**: 2% above entry
- **Max Concurrent Trades**: 5 positions

## 🎮 Usage

### 1. Dashboard Overview
The main dashboard provides:
- **Portfolio Summary**: Current balance, P&L, win rate
- **Active Trades**: Open positions and their status
- **Recent Signals**: Latest trading signals
- **Performance Charts**: Portfolio performance over time

### 2. Trading Modes

#### Demo Mode (Default)
- Paper trading with virtual money
- Real market data with simulated trades
- Perfect for learning and testing strategies
- No real money at risk

#### Live Mode
- Real money trading (requires broker integration)
- Angel One API integration for Indian markets
- Real-time order execution
- Actual P&L and portfolio tracking

### 3. Trading Strategies

#### RSI Strategy
- Relative Strength Index based signals
- Buy when RSI < 30 (oversold)
- Sell when RSI > 70 (overbought)
- Timeframe: 15m, 1h, 4h, 1d

#### MACD Strategy
- Moving Average Convergence Divergence
- Buy when MACD line crosses above signal line
- Sell when MACD line crosses below signal line
- Timeframe: 1h, 4h, 1d

#### Bollinger Bands Strategy
- Price-based mean reversion strategy
- Buy when price touches lower band
- Sell when price touches upper band
- Timeframe: 15m, 1h, 4h, 1d

#### Moving Average Strategy
- Trend-following strategy
- Buy when short MA crosses above long MA
- Sell when short MA crosses below long MA
- Timeframe: 1h, 4h, 1d

### 4. Risk Management

#### Position Sizing
- Automatic calculation based on risk parameters
- Maximum 2% risk per trade (configurable)
- Portfolio-based position sizing
- Volatility-adjusted sizing

#### Stop Loss & Take Profit
- Automatic stop loss placement
- Take profit targets
- Trailing stops (advanced)
- Risk-reward ratio optimization

## 📚 API Documentation

### Authentication
All API endpoints require authentication. Include the session token in requests.

### Trading Endpoints

#### Start Auto-Trading
```http
POST /api/indian/start-auto-trading
Content-Type: application/json

{
    "strategy": "rsi",
    "symbols": ["NIFTY50", "BANKNIFTY"],
    "risk_per_trade": 2.0,
    "max_trades": 5
}
```

#### Stop Auto-Trading
```http
POST /api/indian/stop-auto-trading
```

#### Get Trading Status
```http
GET /api/indian/status
```

#### Portfolio Summary
```http
GET /api/portfolio/summary
```

### Data Endpoints

#### Market Data
```http
GET /api/market-data?symbol=NIFTY50&interval=1d&period=1y
```

#### Trading Signals
```http
GET /api/signals?symbol=NIFTY50&limit=10
```

#### Historical Trades
```http
GET /api/trades?limit=50&status=completed
```

### Admin Endpoints

#### System Status
```http
GET /api/admin/system-status
```

#### Performance Metrics
```http
GET /api/admin/performance-metrics
```

#### Cache Management
```http
POST /api/admin/clear-cache
```

## 🎛️ Admin Panel

### Access
- URL: http://localhost:5000/admin_panel
- Login: admin / admin123
- Requires admin privileges

### Features

#### System Monitoring
- **Real-Time Metrics**: CPU, Memory, Disk usage
- **Trading Status**: Active trades, P&L, win rate
- **Performance Charts**: System performance over time
- **Error Logs**: System errors and warnings

#### Data Management
- **Data Injection**: Start/stop real-time data feeds
- **Cache Management**: Clear and manage data cache
- **Backup/Restore**: System backup and recovery
- **Database Tools**: Database management and optimization

#### Trading Control
- **Auto-Trading**: Start/stop automated trading
- **Strategy Selection**: Choose trading strategies
- **Risk Parameters**: Adjust risk management settings
- **Symbol Management**: Add/remove trading symbols

#### User Management
- **User Accounts**: Manage user accounts
- **Permissions**: Set user permissions and roles
- **Security**: Monitor security events and login attempts
- **Notifications**: Configure notification settings

## 🏪 Trading Systems

### Indian Trading System
Specialized for Indian markets with focus on:
- **NIFTY50**: India's benchmark index
- **BANKNIFTY**: Banking sector index
- **Major Stocks**: RELIANCE, TCS, HDFC, etc.
- **Options Trading**: Call and Put options
- **Angel One Integration**: Real-time Indian market data

### Global Trading System
Support for international markets:
- **US Stocks**: AAPL, GOOGL, MSFT, etc.
- **ETFs**: SPY, QQQ, VTI, etc.
- **Forex**: EUR/USD, GBP/USD, USD/JPY
- **Commodities**: Gold, Silver, Oil
- **Crypto**: Bitcoin, Ethereum (if available)

### Auto-Trading Features
- **Strategy Execution**: Multiple trading strategies
- **Risk Management**: Automatic position sizing
- **Trade Management**: Stop loss and take profit
- **Portfolio Rebalancing**: Dynamic portfolio adjustment
- **Performance Tracking**: Real-time P&L monitoring

## 🔒 Security

### Authentication & Authorization
- **Secure Login**: PBKDF2 password hashing
- **Session Management**: Secure session tokens
- **Role-Based Access**: Admin and user permissions
- **Brute Force Protection**: Login attempt limiting

### Data Protection
- **Input Validation**: Comprehensive input sanitization
- **SQL Injection Prevention**: Parameterized queries
- **XSS Protection**: Output encoding and CSP headers
- **CSRF Protection**: Token-based request validation

### Security Monitoring
- **Audit Logging**: Complete security event tracking
- **Failed Login Tracking**: IP and user-based monitoring
- **Rate Limiting**: API abuse prevention
- **Security Alerts**: Real-time security notifications

## 🚀 Deployment

### Production Deployment

#### 1. Server Requirements
- **OS**: Ubuntu 20.04+ or Windows Server 2019+
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 50GB SSD minimum
- **CPU**: 4 cores minimum
- **Network**: Stable internet connection

#### 2. Environment Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install python3 python3-pip python3-venv nginx -y

# Create application user
sudo useradd -m -s /bin/bash kishanx
sudo su - kishanx

# Clone and setup application
git clone <repository-url> kishanx-trading
cd kishanx-trading
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 3. Database Setup
```bash
# Initialize database
python database_setup.py

# Set proper permissions
chmod 600 kishanx.db
chown kishanx:kishanx kishanx.db
```

#### 4. Nginx Configuration
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

#### 5. Systemd Service
```ini
[Unit]
Description=KishanX Trading Signals
After=network.target

[Service]
Type=simple
User=kishanx
WorkingDirectory=/home/kishanx/kishanx-trading
Environment=PATH=/home/kishanx/kishanx-trading/venv/bin
ExecStart=/home/kishanx/kishanx-trading/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

#### 6. SSL Certificate (Let's Encrypt)
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

### Docker Deployment

#### Dockerfile
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN python database_setup.py

EXPOSE 5000
CMD ["python", "app.py"]
```

#### Docker Compose
```yaml
version: '3.8'
services:
  kishanx-trading:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite:///data/kishanx.db
    restart: unless-stopped
```

## 📞 Support

### Getting Help
1. **Documentation**: Check this README and other documentation files
2. **Admin Panel**: Use the built-in system monitoring
3. **Logs**: Check application logs for error details
4. **Community**: Join our community forum
5. **Support**: Contact support team

### Troubleshooting

#### Common Issues
1. **Database Connection Errors**
   - Check database file permissions
   - Verify database path in configuration
   - Run database setup script

2. **API Connection Issues**
   - Verify API keys in configuration
   - Check internet connectivity
   - Review rate limiting settings

3. **Trading System Not Starting**
   - Check system logs for errors
   - Verify trading parameters
   - Ensure data feed is active

4. **Performance Issues**
   - Monitor system resources
   - Clear cache if needed
   - Check database performance

### Contact Information
- **Email**: support@kishanx.com
- **Documentation**: https://docs.kishanx.com
- **GitHub**: https://github.com/kishanx/trading-signals
- **Discord**: https://discord.gg/kishanx

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

## 🙏 Acknowledgments

- Angel One for Indian market data API
- Yahoo Finance for global market data
- Alpha Vantage for additional market data
- The open-source community for various libraries

---

**⚠️ Disclaimer**: Trading involves substantial risk of loss and is not suitable for all investors. Past performance is not indicative of future results. Please trade responsibly and only invest what you can afford to lose.
