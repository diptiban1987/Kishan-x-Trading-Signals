import yfinance as yf

symbols = ['HINDUNILVR', 'BHARTIARTL', 'BAJFINANCE']
print("Fetching latest closing prices from NSE (Yahoo Finance)...")
for s in symbols:
    try:
        ticker = yf.Ticker(s + ".NS")
        df = ticker.history(period="5d", interval="5m")
        if df.empty:
            df = ticker.history(period="5d")
        
        last_row = df.iloc[-1]
        print(f"Symbol: {s}")
        print(f"  Datetime/Date: {last_row.name}")
        print(f"  Open:  ₹{last_row['Open']:.2f}")
        print(f"  High:  ₹{last_row['High']:.2f}")
        print(f"  Low:   ₹{last_row['Low']:.2f}")
        print(f"  Close: ₹{last_row['Close']:.2f}")
        print(f"  Volume: {int(last_row['Volume'])}")
    except Exception as e:
        print(f"Error fetching {s}: {e}")