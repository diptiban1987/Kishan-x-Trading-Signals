"""
Configuration settings for the trading application.
"""

# API Configuration
#ALPHA_VANTAGE_API_KEY = "XKXHZXU8QXQX6LB9"  # Original Alpha Vantage API key
ALPHA_VANTAGE_BACKUP_KEY = "XKXHZXU8QXQX6LB9"  # Original backup API key
#OPENEXCHANGERATES_API_KEY = "YOUR_OPENEXCHANGERATES_API_KEY"
#CURRENCYLAYER_API_KEY = "YOUR_CURRENCYLAYER_API_KEY"

# API Configuration
ALPHA_VANTAGE_API_KEY = "YTEHGJP4RCYRYW7G"   #"35BDZ47V6D5T4B8G"
OPENEXCHANGERATES_API_KEY = "d16db1e03711417581ce5a2dda273830"
CURRENCYLAYER_API_KEY = "9e46ca5a5edd08e5592cb1779e9dc05d"
FIXER_API_KEY = "9e46ca5a5edd08e5592cb1779e9dc05d"

# API Settings
API_TIMEOUT = 10  # seconds
CACHE_DURATION = 1  # 1 second - reduced from 5 minutes for more frequent updates
PREMIUM_API_ENABLED = False
MAX_RETRIES = 3  # Maximum number of retries for failed API calls

# Rate Limiting (Updated for free tier)
ALPHA_VANTAGE_RATE_LIMIT = 5  # 5 calls per minute for free tier
ALPHA_VANTAGE_DAILY_LIMIT = 25  # 25 calls per day for free tier
EXCHANGERATE_API_RATE_LIMIT = 5  # Reduced to match Alpha Vantage limit
FIXER_RATE_LIMIT = 5  # Reduced to match Alpha Vantage limit
OPENEXCHANGERATES_RATE_LIMIT = 5  # Reduced to match Alpha Vantage limit
CURRENCYLAYER_RATE_LIMIT = 5  # Reduced to match Alpha Vantage limit

# Fallback Strategy
USE_BACKUP_SOURCES = True  # Enable fallback to backup data sources
BACKUP_SOURCE_ORDER = ['ExchangeRate-API', 'Fixer.io', 'Open Exchange Rates', 'Currency Layer']
MAX_SOURCE_RETRIES = 2  # Maximum number of alternative sources to try

# Cache Settings
PRICE_CACHE_DURATION = 300  # 5 minutes - increased from 1 minute
HISTORICAL_CACHE_DURATION = 3600  # 1 hour

# Error Handling
MAX_CONSECUTIVE_ERRORS = 3  # Maximum number of consecutive errors before switching source
ERROR_RETRY_DELAY = 5  # Seconds to wait between retries
ENABLE_ERROR_LOGGING = True

# Data Source Priorities (1 is highest)
DATA_SOURCE_PRIORITIES = {
    'Alpha Vantage': 1,
    'ExchangeRate-API': 2,
    'Fixer.io': 3,
    'Open Exchange Rates': 4,
    'Currency Layer': 5
}

# Validation Settings
MIN_PRICE = 0.000001
MAX_PRICE = 1000000
PRICE_VALIDATION_ENABLED = True

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = "trading_app.log"

# Database
DATABASE_URL = "sqlite:///trading.db"

# WebSocket
WEBSOCKET_HOST = "localhost"
WEBSOCKET_PORT = 8765

# Trading Settings
DEFAULT_TIMEFRAME = "1m"
DEFAULT_VOLUME_THRESHOLD = 100000
DEFAULT_SPREAD_THRESHOLD = 1.5

# Risk Management
MAX_POSITION_SIZE = 0.02  # 2% of account
MAX_DAILY_TRADES = 10
MAX_DAILY_LOSS = 0.05  # 5% of account
STOP_LOSS_PERCENTAGE = 0.02  # 2%
TAKE_PROFIT_PERCENTAGE = 0.04  # 4%

# Signal Generation
SIGNAL_CONFIDENCE_THRESHOLD = 0.75
MIN_VOLUME_THRESHOLD = 100000
MAX_SPREAD_THRESHOLD = 1.5
REQUIRED_CONFIRMATIONS = 2

# OTC Specific Settings
OTC_VOLUME_THRESHOLD = 150000
OTC_SPREAD_THRESHOLD = 1.0
OTC_MIN_ACCURACY = 0.75
OTC_REQUIRED_CONFIRMATIONS = 3