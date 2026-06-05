symbol_map = {
    # Major US ETFs (these work reliably)
    "SPY": "SPY",  # S&P 500 ETF
    "QQQ": "QQQ",  # NASDAQ-100 ETF
    "IWM": "IWM",  # Russell 2000 ETF
    "DIA": "DIA",  # Dow Jones ETF
    "VTI": "VTI",  # Vanguard Total Stock Market ETF
    
    # Major US Stocks (these work reliably)
    "AAPL": "AAPL",  # Apple
    "MSFT": "MSFT",  # Microsoft
    "GOOGL": "GOOGL",  # Alphabet
    "AMZN": "AMZN",  # Amazon
    "TSLA": "TSLA",  # Tesla
    "META": "META",  # Meta
    "NVDA": "NVDA",  # NVIDIA
    "JPM": "JPM",  # JPMorgan Chase
    "V": "V",  # Visa
    
    # Major Forex Pairs (these work reliably)
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    
    # Major Commodities (these work reliably)
    "GOLD": "GC=F",  # Gold Futures
    "OIL": "CL=F",  # Crude Oil Futures
}

def get_all_symbols() -> list:
    """Returns a list of all supported symbols."""
    return list(symbol_map.keys())

def get_symbol_yahoo(symbol: str) -> str:
    """Returns the Yahoo Finance symbol for a given symbol."""
    return symbol_map.get(symbol, symbol)

def get_working_symbols() -> list:
    """Returns a list of symbols that are known to work reliably."""
    reliable_symbols = [
        "SPY", "QQQ", "IWM", "DIA", "VTI",
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
        "META", "NVDA", "JPM", "V",
        "EURUSD", "GBPUSD", "USDJPY",
        "GOLD", "OIL"
    ]
    return reliable_symbols