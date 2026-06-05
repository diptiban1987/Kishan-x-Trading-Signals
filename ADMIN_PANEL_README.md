# 🎛️ Admin Panel - Complete Management Guide

## 📋 Table of Contents
- [Overview](#overview)
- [Access & Authentication](#access--authentication)
- [Dashboard Overview](#dashboard-overview)
- [System Monitoring](#system-monitoring)
- [Trading Management](#trading-management)
- [Data Management](#data-management)
- [User Management](#user-management)
- [Security Management](#security-management)
- [Backup & Recovery](#backup--recovery)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## 🎯 Overview

The Admin Panel is the central control hub for the KishanX Trading Signals platform. It provides comprehensive system management, monitoring, and control capabilities for administrators to manage all aspects of the trading system.

### Key Features
- **Real-Time Monitoring**: Live system metrics and performance data
- **Trading Control**: Start/stop auto-trading and manage strategies
- **Data Management**: Control data feeds and cache management
- **User Management**: Manage user accounts and permissions
- **Security Monitoring**: Track security events and system health
- **Backup Management**: Automated backup and recovery operations

## 🔐 Access & Authentication

### Default Access
- **URL**: `http://localhost:5000/admin_panel`
- **Username**: `admin`
- **Password**: `admin123`

### Security Features
- **Role-Based Access**: Admin-only functions
- **Session Management**: Secure session handling
- **Activity Logging**: All admin actions are logged
- **IP Restrictions**: Optional IP-based access control

### Changing Default Credentials
1. Access the admin panel
2. Go to **User Management** → **Admin Settings**
3. Update username and password
4. Save changes

## 📊 Dashboard Overview

### System Status Cards
The dashboard displays real-time system metrics:

#### Trading Status
- **Active Trades**: Number of currently open positions
- **Total P&L**: Today's profit/loss
- **Win Rate**: Percentage of winning trades
- **Trading Mode**: DEMO or LIVE mode

#### System Health
- **CPU Usage**: Current CPU utilization percentage
- **Memory Usage**: RAM usage and available memory
- **Disk Usage**: Storage space utilization
- **Network I/O**: Network activity metrics

#### Data Quality
- **Data Feed Status**: Active data sources
- **Cache Hit Rate**: Cache performance percentage
- **Last Update**: Most recent data update timestamp
- **Error Rate**: System error frequency

### Real-Time Charts
- **Portfolio Performance**: Live P&L tracking
- **System Resources**: CPU, Memory, Disk usage over time
- **Trading Activity**: Trade execution frequency
- **Error Monitoring**: System errors and warnings

## 🔧 System Monitoring

### Performance Metrics

#### CPU Monitoring
- **Current Usage**: Real-time CPU percentage
- **Peak Usage**: Highest CPU usage in the last hour
- **Average Usage**: Average CPU usage over time
- **Process Breakdown**: CPU usage by individual processes

#### Memory Monitoring
- **Total Memory**: System RAM capacity
- **Used Memory**: Currently allocated memory
- **Available Memory**: Free memory available
- **Memory Trends**: Memory usage over time

#### Disk Monitoring
- **Total Space**: Total disk capacity
- **Used Space**: Currently used disk space
- **Free Space**: Available disk space
- **I/O Operations**: Disk read/write operations

#### Network Monitoring
- **Bytes Sent/Received**: Network traffic volume
- **Packets Sent/Received**: Network packet count
- **Connection Status**: Active network connections
- **Bandwidth Usage**: Network speed utilization

### System Alerts
- **High CPU Usage**: Alert when CPU > 80%
- **Low Memory**: Alert when memory < 20% free
- **Disk Space**: Alert when disk > 85% full
- **Network Issues**: Alert on connection problems

### Log Monitoring
- **System Logs**: Application and system logs
- **Error Logs**: Error messages and stack traces
- **Security Logs**: Authentication and security events
- **Trading Logs**: Trade execution and strategy logs

## 🏪 Trading Management

### Auto-Trading Control

#### Start Auto-Trading
1. Navigate to **Trading Management** → **Auto-Trading**
2. Select trading strategy:
   - **RSI Strategy**: Relative Strength Index based
   - **MACD Strategy**: Moving Average Convergence Divergence
   - **Bollinger Bands**: Mean reversion strategy
   - **Moving Average**: Trend-following strategy
3. Choose symbols to trade
4. Set risk parameters
5. Click **Start Auto-Trading**

#### Stop Auto-Trading
1. Go to **Trading Management** → **Auto-Trading**
2. Click **Stop Auto-Trading**
3. Confirm the action
4. All active trades will be closed

#### Trading Parameters
- **Max Concurrent Trades**: Maximum open positions (1-10)
- **Risk Per Trade**: Risk percentage per trade (0.5-5%)
- **Stop Loss**: Default stop loss percentage (0.5-3%)
- **Take Profit**: Default take profit percentage (1-10%)
- **Strategy**: Active trading strategy
- **Symbols**: List of tradable symbols

### Strategy Management

#### RSI Strategy
- **Oversold Level**: RSI threshold for buy signals (default: 30)
- **Overbought Level**: RSI threshold for sell signals (default: 70)
- **Timeframe**: Analysis timeframe (15m, 1h, 4h, 1d)
- **Confidence Threshold**: Minimum confidence for signals (0.6-0.9)

#### MACD Strategy
- **Fast Period**: Fast EMA period (default: 12)
- **Slow Period**: Slow EMA period (default: 26)
- **Signal Period**: Signal line period (default: 9)
- **Timeframe**: Analysis timeframe (1h, 4h, 1d)

#### Bollinger Bands Strategy
- **Period**: Moving average period (default: 20)
- **Standard Deviations**: Band width (default: 2)
- **Timeframe**: Analysis timeframe (15m, 1h, 4h, 1d)

#### Moving Average Strategy
- **Short Period**: Short MA period (default: 10)
- **Long Period**: Long MA period (default: 50)
- **Timeframe**: Analysis timeframe (1h, 4h, 1d)

### Trade Management

#### Active Trades
- **Symbol**: Trading symbol
- **Side**: BUY or SELL
- **Quantity**: Number of shares/units
- **Entry Price**: Entry price
- **Current Price**: Current market price
- **P&L**: Current profit/loss
- **Stop Loss**: Stop loss price
- **Take Profit**: Take profit price
- **Strategy**: Trading strategy used
- **Time**: Entry time

#### Trade Actions
- **Close Trade**: Manually close a position
- **Modify Stop Loss**: Update stop loss price
- **Modify Take Profit**: Update take profit price
- **View Details**: Detailed trade information

### Portfolio Analytics

#### Portfolio Summary
- **Total Balance**: Current portfolio value
- **Available Balance**: Available for trading
- **Invested Amount**: Amount in open positions
- **Total P&L**: Overall profit/loss
- **Today's P&L**: Today's profit/loss
- **Win Rate**: Percentage of winning trades

#### Performance Metrics
- **Sharpe Ratio**: Risk-adjusted returns
- **Maximum Drawdown**: Largest peak-to-trough decline
- **Average Win**: Average winning trade amount
- **Average Loss**: Average losing trade amount
- **Profit Factor**: Gross profit / Gross loss

#### Historical Performance
- **Daily P&L**: Daily profit/loss chart
- **Monthly Returns**: Monthly performance
- **Year-to-Date**: YTD performance
- **All-Time**: Total performance since start

## 📊 Data Management

### Data Sources

#### Angel One API (Indian Markets)
- **Status**: Active/Inactive
- **API Key**: Configured API key
- **Client ID**: Angel One client ID
- **Last Update**: Most recent data fetch
- **Error Count**: Number of API errors
- **Rate Limit**: Current rate limit status

#### Yahoo Finance (Global Markets)
- **Status**: Active/Inactive
- **Last Update**: Most recent data fetch
- **Error Count**: Number of API errors
- **Rate Limit**: Current rate limit status

#### Alpha Vantage (Forex/Commodities)
- **Status**: Active/Inactive
- **API Key**: Configured API key
- **Last Update**: Most recent data fetch
- **Error Count**: Number of API errors
- **Rate Limit**: Current rate limit status

### Data Injection Control

#### Start Data Injection
1. Go to **Data Management** → **Data Injection**
2. Select data source:
   - **Angel One**: For Indian markets
   - **Yahoo Finance**: For global markets
   - **Alpha Vantage**: For forex/commodities
   - **Custom API**: For custom data sources
3. Configure parameters:
   - **Symbols**: List of symbols to fetch
   - **Update Frequency**: Seconds between updates (5-300)
   - **API Key**: Required for some sources
4. Click **Start Data Injection**

#### Stop Data Injection
1. Navigate to **Data Management** → **Data Injection**
2. Click **Stop Data Injection**
3. Confirm the action

#### Data Quality Monitoring
- **Success Rate**: Percentage of successful data fetches
- **Error Rate**: Percentage of failed data fetches
- **Last Update**: Timestamp of most recent data
- **Data Freshness**: Age of current data

### Cache Management

#### Cache Statistics
- **Total Cache Size**: Size of all cached data
- **Cache Files**: Number of cache files
- **Hit Rate**: Cache hit percentage
- **Miss Rate**: Cache miss percentage
- **Oldest Entry**: Age of oldest cached data

#### Cache Operations
- **Clear All Cache**: Remove all cached data
- **Clean Expired Cache**: Remove expired cache entries
- **Clear Symbol Cache**: Clear cache for specific symbols
- **View Cache Details**: Detailed cache information

#### Cache Configuration
- **Default Duration**: Default cache duration (minutes)
- **Max Cache Size**: Maximum cache size (MB)
- **Cleanup Frequency**: How often to clean expired cache
- **Compression**: Enable/disable cache compression

## 👥 User Management

### User Accounts

#### User List
- **Username**: User login name
- **Email**: User email address
- **Role**: Admin, User, or Guest
- **Status**: Active, Inactive, or Suspended
- **Last Login**: Most recent login time
- **Created**: Account creation date
- **Balance**: Current account balance

#### User Actions
- **Create User**: Add new user account
- **Edit User**: Modify user details
- **Suspend User**: Temporarily disable account
- **Delete User**: Permanently remove account
- **Reset Password**: Reset user password
- **View Activity**: User activity log

#### User Permissions
- **Trading**: Allow/disallow trading
- **Admin Access**: Grant admin privileges
- **Data Access**: Control data access levels
- **API Access**: Allow API usage
- **Export Data**: Allow data export

### Permission Management

#### Role-Based Permissions
- **Admin**: Full system access
- **User**: Standard trading access
- **Guest**: Limited read-only access
- **API User**: API-only access

#### Custom Permissions
- **Trading**: Execute trades
- **View Data**: Access market data
- **Export Data**: Export trading data
- **Admin Panel**: Access admin functions
- **API Access**: Use API endpoints

### Security Management

#### Login Attempts
- **Failed Logins**: Number of failed login attempts
- **IP Addresses**: IPs with failed attempts
- **Time Range**: Time period of attempts
- **Lockout Status**: Account lockout status

#### Security Events
- **Event Type**: Type of security event
- **User**: User involved (if any)
- **IP Address**: Source IP address
- **Timestamp**: When event occurred
- **Details**: Event description
- **Severity**: Low, Medium, High, Critical

#### Session Management
- **Active Sessions**: Currently active user sessions
- **Session Details**: Session information
- **Force Logout**: Terminate specific sessions
- **Session Timeout**: Configure session duration

## 💾 Backup & Recovery

### Backup Management

#### Backup Types
- **Full Backup**: Complete system backup
- **Database Backup**: Database only
- **Configuration Backup**: Settings and config files
- **Incremental Backup**: Changes since last backup

#### Create Backup
1. Go to **Backup & Recovery** → **Create Backup**
2. Select backup type
3. Choose compression (optional)
4. Set backup name
5. Click **Create Backup**

#### Backup History
- **Backup Name**: Backup identifier
- **Type**: Full, Database, or Configuration
- **Size**: Backup file size
- **Created**: Creation timestamp
- **Status**: Success, Failed, or In Progress
- **Actions**: Download, Restore, or Delete

#### Automated Backups
- **Daily Full Backup**: Complete system backup
- **Hourly Database Backup**: Database-only backup
- **Weekly Configuration Backup**: Settings backup
- **Retention Policy**: How long to keep backups

### Recovery Operations

#### Restore from Backup
1. Navigate to **Backup & Recovery** → **Restore**
2. Select backup to restore
3. Choose restore type:
   - **Full Restore**: Complete system restore
   - **Database Only**: Restore database only
   - **Configuration Only**: Restore settings only
4. Confirm restore operation

#### Recovery Options
- **Point-in-Time Recovery**: Restore to specific time
- **Selective Recovery**: Restore specific components
- **Dry Run**: Test restore without applying changes
- **Rollback**: Undo last restore operation

## ⚙️ Configuration

### System Settings

#### General Settings
- **Application Name**: System name
- **Default Language**: Interface language
- **Time Zone**: System time zone
- **Date Format**: Date display format
- **Currency**: Default currency symbol

#### Trading Settings
- **Default Balance**: Initial user balance
- **Max Risk Per Trade**: Maximum risk percentage
- **Default Stop Loss**: Default stop loss percentage
- **Default Take Profit**: Default take profit percentage
- **Max Concurrent Trades**: Maximum open positions

#### Data Settings
- **Cache Duration**: Default cache duration
- **Update Frequency**: Data update frequency
- **Rate Limits**: API rate limiting
- **Data Sources**: Available data sources
- **Symbol Lists**: Tradable symbols

#### Security Settings
- **Session Timeout**: Session duration
- **Password Policy**: Password requirements
- **Login Attempts**: Max failed login attempts
- **Lockout Duration**: Account lockout time
- **IP Restrictions**: Allowed IP addresses

### API Configuration

#### Angel One API
- **API Key**: Angel One API key
- **Client ID**: Angel One client ID
- **PIN**: Angel One PIN
- **Base URL**: API base URL
- **Timeout**: Request timeout

#### Yahoo Finance
- **Base URL**: Yahoo Finance API URL
- **Timeout**: Request timeout
- **Rate Limit**: Requests per minute

#### Alpha Vantage
- **API Key**: Alpha Vantage API key
- **Base URL**: API base URL
- **Timeout**: Request timeout
- **Rate Limit**: Requests per minute

### Notification Settings

#### Email Notifications
- **SMTP Server**: Email server
- **SMTP Port**: Email port
- **Username**: Email username
- **Password**: Email password
- **From Address**: Sender email
- **TLS**: Enable TLS encryption

#### Notification Types
- **Trade Signals**: New trading signals
- **Trade Executed**: Trade execution alerts
- **Portfolio Alerts**: Portfolio warnings
- **System Alerts**: System notifications
- **Error Notifications**: Error alerts

## 🔧 Troubleshooting

### Common Issues

#### System Performance Issues
1. **High CPU Usage**
   - Check active processes
   - Reduce update frequency
   - Clear cache
   - Restart services

2. **Memory Issues**
   - Monitor memory usage
   - Clear cache
   - Restart application
   - Increase system memory

3. **Disk Space Issues**
   - Clean old backups
   - Clear cache
   - Remove log files
   - Increase disk space

#### Trading System Issues
1. **Auto-Trading Not Starting**
   - Check data feed status
   - Verify trading parameters
   - Review error logs
   - Check permissions

2. **Data Feed Problems**
   - Verify API credentials
   - Check network connectivity
   - Review rate limits
   - Test data sources

3. **Trade Execution Errors**
   - Check broker connection
   - Verify account balance
   - Review trading parameters
   - Check market hours

#### Database Issues
1. **Connection Errors**
   - Check database file permissions
   - Verify database path
   - Restart database service
   - Check disk space

2. **Data Corruption**
   - Restore from backup
   - Run database repair
   - Check for errors
   - Contact support

### Debug Mode

#### Enable Debug Logging
1. Go to **System Settings** → **Logging**
2. Set log level to **DEBUG**
3. Enable detailed logging
4. Save settings

#### View Debug Logs
1. Navigate to **System Monitoring** → **Logs**
2. Select **Debug Logs**
3. Filter by component
4. Download logs if needed

### Support Tools

#### System Diagnostics
- **Health Check**: Complete system health check
- **Performance Test**: System performance test
- **Connectivity Test**: Network connectivity test
- **Database Test**: Database connection test

#### Export Information
- **System Info**: Export system information
- **Configuration**: Export current configuration
- **Logs**: Export system logs
- **Database**: Export database schema

### Getting Help

#### Self-Service
1. Check this documentation
2. Review system logs
3. Use built-in diagnostics
4. Check online resources

#### Contact Support
1. **Email**: admin@kishanx.com
2. **Phone**: +1-800-KISHANX
3. **Chat**: Live chat support
4. **Ticket**: Create support ticket

#### Escalation
1. **Level 1**: Basic troubleshooting
2. **Level 2**: Advanced technical support
3. **Level 3**: Development team
4. **Emergency**: Critical system issues

---

**⚠️ Important Notes**:
- Always backup before making major changes
- Test changes in demo mode first
- Monitor system performance after changes
- Keep documentation updated
- Regular security audits recommended
