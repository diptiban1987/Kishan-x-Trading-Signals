import sys
import io

# Fix Issue 1: Force UTF-8 encoding for stdout/stderr to prevent UnicodeEncodeError on emoji/log chars
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, jsonify, request, render_template, redirect, url_for
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd

# Ensure we can import from project root
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
	sys.path.insert(0, str(ROOT_DIR))

from angel_one_api import AngelOneAPI, AngelOneDataProvider
from branding_config import get_platform_setting

load_dotenv()

# Use root templates/static to reuse UI
app = Flask(__name__, template_folder=str(ROOT_DIR / 'templates'), static_folder=str(ROOT_DIR / 'static'))

# Provide static_url and get_setting used by base.html
@app.context_processor
def utility_processor():
	def static_url(filename: str):
		return url_for('static', filename=filename)
	return dict(
		static_url=static_url,
		get_setting=get_platform_setting,
		platform_name=get_platform_setting('platform_name'),
		short_name=get_platform_setting('short_name'),
		support_email=get_platform_setting('support_email')
	)

# Only Indian focus: set disable flags for other systems (best-effort)
os.environ.setdefault('DISABLE_OTC', '1')
os.environ.setdefault('DISABLE_FOREX', '1')
os.environ.setdefault('INDIAN_AUTOTRADE_ENABLED', '0')

# Angel One credentials
API_KEY = os.getenv('ANGEL_ONE_API_KEY')
CLIENT_ID = os.getenv('ANGEL_ONE_CLIENT_CODE')
PASSWORD = os.getenv('ANGEL_ONE_PASSWORD')
TOTP_SECRET = os.getenv('ANGEL_ONE_TOTP_SECRET')

angel = None
provider = None

if API_KEY and CLIENT_ID and PASSWORD and TOTP_SECRET:
	angel = AngelOneAPI(API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET)
	if angel.generate_session():
		print('[OK] Angel One session connected (indian_only)')
		provider = AngelOneDataProvider(angel)
	else:
		print('[FAIL] Angel One session failed (indian_only)')
else:
	print('[WARN] Missing Angel One creds in .env for indian_only')

# Routes
@app.route('/')
def root():
	return redirect(url_for('indian_page'))

@app.route('/indian')
def indian_page():
	return render_template('indian.html')

@app.route('/status')
def status():
	return jsonify({
		'status': 'connected' if angel and angel.is_connected else 'disconnected',
		'has_provider': bool(provider),
		'pairs': [
			'NIFTY50','BANKNIFTY','FINNIFTY','SENSEX','RELIANCE','TCS','HDFCBANK','INFY','ICICIBANK','SBIN','BHARTIARTL','KOTAKBANK','BAJFINANCE'
		]
	})

@app.route('/market_data/<pair>')
def market_data(pair: str):
	if not provider:
		return jsonify({'error': 'Angel One not connected'}), 503
	interval = request.args.get('interval', '1d')
	period = request.args.get('period', '30d')
	try:
		data = provider.get_historical_data(pair.upper(), interval=interval, period=period)
		if data is None or data.empty:
			return jsonify({
				'pair': pair,
				'historical': {'dates': [], 'prices': {'open': [], 'high': [], 'low': [], 'close': [], 'volume': []}},
				'current_price': 0.0,
				'hint': 'No data yet from Angel One'
			})
		dates = [d.strftime('%Y-%m-%d %H:%M:%S') for d in data.index.to_pydatetime()]
		chart = {
			'dates': dates,
			'prices': {
				'open': [float(x) for x in data['Open'].tolist()],
				'high': [float(x) for x in data['High'].tolist()],
				'low': [float(x) for x in data['Low'].tolist()],
				'close': [float(x) for x in data['Close'].tolist()],
				'volume': [int(x) for x in (data['Volume'].tolist() if 'Volume' in data.columns else [0]*len(dates))]
			}
		}
		return jsonify({'pair': pair, 'historical': chart, 'current_price': chart['prices']['close'][-1] if dates else 0.0})
	except Exception as e:
		return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
	port = int(os.getenv('PORT', '5001'))
	app.run(host='0.0.0.0', port=port)
