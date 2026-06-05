import os
from dotenv import load_dotenv
from angel_one_api import AngelOneAPI

def test_angel_historical():
    load_dotenv()
    api_key = os.getenv("ANGEL_ONE_API_KEY")
    client_id = os.getenv("ANGEL_ONE_CLIENT_CODE")
    password = os.getenv("ANGEL_ONE_PASSWORD")
    totp_secret = os.getenv("ANGEL_ONE_TOTP_SECRET")
    
    print("Initializing Angel One API...")
    api = AngelOneAPI(api_key, client_id, password, totp_secret)
    
    if api.generate_session():
        print("Session generated successfully!")
        
        # Test historical data fetch for SBIN
        print("Fetching historical data for SBIN...")
        df = api.get_historical_data("SBIN", interval="ONE_DAY")
        
        if not df.empty:
            print("Historical data fetched successfully!")
            print(df.head())
        else:
            print("Failed to fetch historical data. Check if Historical API is enabled in your Angel One dashboard.")
    else:
        print("Failed to generate session.")

if __name__ == "__main__":
    test_angel_historical()
