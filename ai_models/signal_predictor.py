"""
AI-Powered Trading Signal Predictor — Production Version
Uses XGBoost ensemble with multi-indicator fusion for BUY/SELL/HOLD signals.
Auto-trains on real market data via yfinance when no saved model exists.
"""

import os
import pickle
import logging
import hashlib
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Lazy imports for ML libs (they're heavy)
_xgb = None
_sklearn_split = None
_sklearn_report = None
_sklearn_accuracy = None


def _ensure_ml_imports():
    global _xgb, _sklearn_split, _sklearn_report, _sklearn_accuracy
    if _xgb is None:
        import xgboost as xgb_mod
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report, accuracy_score
        _xgb = xgb_mod
        _sklearn_split = train_test_split
        _sklearn_report = classification_report
        _sklearn_accuracy = accuracy_score


class AISignalPredictor:
    """
    Production AI signal predictor using XGBoost.
    - Fetches real data via yfinance
    - Engineers 20+ technical features
    - Generates BUY/SELL/HOLD with confidence scores
    - Detects market regime (trending / ranging / volatile)
    - Auto-trains when no saved model exists
    """

    SIGNAL_CLASSES = ['SELL', 'HOLD', 'BUY']
    MODEL_VERSION = "2.0.0"

    # Indian market symbol mappings for yfinance
    INDIAN_YF_MAP = {
        'NIFTY50': '^NSEI', 'BANKNIFTY': '^NSEBANK', 'SENSEX': '^BSESN',
        'RELIANCE': 'RELIANCE.NS', 'TCS': 'TCS.NS', 'HDFCBANK': 'HDFCBANK.NS',
        'INFY': 'INFY.NS', 'ICICIBANK': 'ICICIBANK.NS', 'SBIN': 'SBIN.NS',
        'BHARTIARTL': 'BHARTIARTL.NS', 'KOTAKBANK': 'KOTAKBANK.NS',
        'BAJFINANCE': 'BAJFINANCE.NS', 'HINDUNILVR': 'HINDUNILVR.NS',
        'ITC': 'ITC.NS', 'LT': 'LT.NS', 'AXISBANK': 'AXISBANK.NS',
        'MARUTI': 'MARUTI.NS', 'TATAMOTORS': 'TATAMOTORS.NS',
        'WIPRO': 'WIPRO.NS', 'SUNPHARMA': 'SUNPHARMA.NS',
    }

    CACHE_TTL_SECONDS = 180  # 3-minute cache — predictions refresh when new candle data arrives

    def __init__(self, model_dir: str = None):
        self.model = None
        self.model_dir = model_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'saved_models'
        )
        self.model_path = os.path.join(self.model_dir, 'signal_predictor_v2.pkl')
        self.feature_columns = [
            'rsi', 'rsi_slope', 'macd', 'macd_signal', 'macd_hist',
            'bb_position', 'bb_width', 'sma_20_cross', 'sma_50_cross',
            'price_above_sma200', 'volume_ratio', 'volume_trend',
            'price_momentum_5', 'price_momentum_10', 'price_momentum_20',
            'volatility_20', 'atr_ratio', 'stoch_k', 'stoch_d',
            'adx_proxy', 'obv_slope',
            'hour_sin', 'hour_cos', 'overnight_gap',
        ]
        self._trained_at = None
        self._accuracy = None
        self._prediction_cache = {}  # {symbol: {'signal': ..., 'data_hash': ..., 'timestamp': ...}}

        if os.path.exists(self.model_path):
            try:
                self.load_model()
            except Exception as e:
                logger.warning(f"Could not load saved model: {e}")

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------
    def _resolve_yf_symbol(self, symbol: str) -> str:
        """Map internal symbol names to yfinance tickers."""
        clean = symbol.replace('.NS', '').replace('.BO', '').upper()
        if clean in self.INDIAN_YF_MAP:
            return self.INDIAN_YF_MAP[clean]
        if not ('.' in symbol or '^' in symbol):
            return f"{symbol}.NS"
        return symbol

    def fetch_market_data(self, symbol: str, period: str = '1y',
                          interval: str = '1d') -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from yfinance."""
        try:
            import yfinance as yf
            yf_sym = self._resolve_yf_symbol(symbol)
            ticker = yf.Ticker(yf_sym)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                logger.warning(f"No yfinance data for {yf_sym}")
                return None
            # Normalise column names to lowercase
            df.columns = [c.lower() for c in df.columns]
            for col in ['close', 'high', 'low', 'open', 'volume']:
                if col not in df.columns:
                    logger.warning(f"Missing column {col} in data for {symbol}")
                    return None
            return df
        except Exception as e:
            logger.error(f"yfinance fetch failed for {symbol}: {e}")
            return None

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Engineer 21 features from raw OHLCV data."""
        f = pd.DataFrame(index=df.index)
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        # RSI-14
        delta = close.diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        f['rsi'] = rsi
        f['rsi_slope'] = rsi.diff(3)

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        f['macd'] = macd
        f['macd_signal'] = macd_signal
        f['macd_hist'] = macd - macd_signal

        # Bollinger Bands
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20
        f['bb_position'] = (close - bb_lower) / (bb_upper - bb_lower + 1e-10)
        f['bb_width'] = (bb_upper - bb_lower) / (sma20 + 1e-10)

        # Moving average cross signals
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        f['sma_20_cross'] = (close > sma20).astype(float)
        f['sma_50_cross'] = (close > sma50).astype(float)
        f['price_above_sma200'] = (close > sma200).astype(float)

        # Volume features
        vol_sma = volume.rolling(20).mean()
        f['volume_ratio'] = volume / (vol_sma + 1e-10)
        f['volume_trend'] = (volume > vol_sma).astype(float)

        # Momentum
        f['price_momentum_5'] = close.pct_change(5)
        f['price_momentum_10'] = close.pct_change(10)
        f['price_momentum_20'] = close.pct_change(20)

        # Volatility
        f['volatility_20'] = close.pct_change().rolling(20).std()

        # ATR ratio
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        f['atr_ratio'] = atr / (close + 1e-10)

        # Stochastic
        low14 = low.rolling(14).min()
        high14 = high.rolling(14).max()
        f['stoch_k'] = 100 * (close - low14) / (high14 - low14 + 1e-10)
        f['stoch_d'] = f['stoch_k'].rolling(3).mean()

        # ADX proxy (using directional movement)
        plus_dm = high.diff().clip(lower=0)
        minus_dm = (-low.diff()).clip(lower=0)
        f['adx_proxy'] = (plus_dm.rolling(14).mean() - minus_dm.rolling(14).mean()).abs()

        # OBV slope
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        f['obv_slope'] = obv.diff(5)

        # Intraday time-of-day features (encode hour as cyclic sin/cos)
        if hasattr(df.index, 'hour'):
            f['hour_sin'] = np.sin(2 * np.pi * df.index.hour / 24)
            f['hour_cos'] = np.cos(2 * np.pi * df.index.hour / 24)
        else:
            f['hour_sin'] = 0.0
            f['hour_cos'] = 0.0

        # Overnight gap (open vs previous close)
        f['overnight_gap'] = (df['open'] - close.shift(1)) / (close.shift(1) + 1e-10)

        return f.fillna(0)

    # ------------------------------------------------------------------
    # Label creation
    # ------------------------------------------------------------------
    def create_labels(self, df: pd.DataFrame, forward_window: int = 3,
                       profit_threshold: float = 0.005) -> pd.Series:
        """Label data: BUY if future return > threshold, SELL if < -threshold."""
        future_ret = df['close'].shift(-forward_window) / df['close'] - 1
        labels = pd.Series(1, index=df.index)  # 1 = HOLD
        labels[future_ret > profit_threshold] = 2   # BUY
        labels[future_ret < -profit_threshold] = 0  # SELL
        labels.iloc[-forward_window:] = np.nan
        return labels

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    def train(self, df: pd.DataFrame, validation_split: float = 0.2) -> Dict:
        """Train XGBoost model on prepared data."""
        _ensure_ml_imports()

        X = self.prepare_features(df)
        y = self.create_labels(df)

        valid = y.notna()
        X = X[valid]
        y = y[valid].astype(int)

        if len(X) < 100:
            return {"error": "Insufficient data for training", "rows": len(X)}

        split = int(len(X) * (1 - validation_split))
        X_train, X_val = X.iloc[:split], X.iloc[split:]
        y_train, y_val = y.iloc[:split], y.iloc[split:]

        self.model = _xgb.XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.08,
            objective='multi:softprob', num_class=3,
            eval_metric='mlogloss', random_state=42,
            subsample=0.8, colsample_bytree=0.8,
            min_child_weight=3, reg_alpha=0.1, reg_lambda=1.0,
        )
        self.model.fit(X_train, y_train,
                       eval_set=[(X_val, y_val)], verbose=False)

        y_pred = self.model.predict(X_val)
        accuracy = float(_sklearn_accuracy(y_val, y_pred))
        report = _sklearn_report(y_val, y_pred,
                                 target_names=self.SIGNAL_CLASSES,
                                 output_dict=True, zero_division=0)

        self._accuracy = accuracy
        self._trained_at = datetime.now().isoformat()
        self.save_model()

        importance = dict(zip(self.feature_columns,
                              self.model.feature_importances_.tolist()))

        logger.info(f"Model trained — accuracy: {accuracy:.4f}")
        return {
            "accuracy": accuracy,
            "classification_report": report,
            "feature_importance": importance,
            "training_samples": len(X_train),
            "validation_samples": len(X_val),
            "model_version": self.MODEL_VERSION,
            "trained_at": self._trained_at,
        }

    def _train_from_Xy(self, X: pd.DataFrame, y: pd.Series,
                       validation_split: float = 0.2) -> Dict:
        """Train XGBoost model from pre-computed features and labels.
        
        Used by auto_train() which generates labels per-symbol to avoid
        cross-symbol data leakage from shift() in create_labels().
        """
        _ensure_ml_imports()

        if len(X) < 100:
            return {"error": "Insufficient data for training", "rows": len(X)}

        split = int(len(X) * (1 - validation_split))
        X_train, X_val = X.iloc[:split], X.iloc[split:]
        y_train, y_val = y.iloc[:split], y.iloc[split:]

        self.model = _xgb.XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.08,
            objective='multi:softprob', num_class=3,
            eval_metric='mlogloss', random_state=42,
            subsample=0.8, colsample_bytree=0.8,
            min_child_weight=3, reg_alpha=0.1, reg_lambda=1.0,
        )
        self.model.fit(X_train, y_train,
                       eval_set=[(X_val, y_val)], verbose=False)

        y_pred = self.model.predict(X_val)
        accuracy = float(_sklearn_accuracy(y_val, y_pred))
        report = _sklearn_report(y_val, y_pred,
                                 target_names=self.SIGNAL_CLASSES,
                                 output_dict=True, zero_division=0)

        self._accuracy = accuracy
        self._trained_at = datetime.now().isoformat()
        self.save_model()

        importance = dict(zip(self.feature_columns,
                              self.model.feature_importances_.tolist()))

        logger.info(f"Model trained (per-symbol labels) — accuracy: {accuracy:.4f}")
        return {
            "accuracy": accuracy,
            "classification_report": report,
            "feature_importance": importance,
            "training_samples": len(X_train),
            "validation_samples": len(X_val),
            "model_version": self.MODEL_VERSION,
            "trained_at": self._trained_at,
        }

    def auto_train(self, symbols: List[str] = None) -> Dict:
        """Auto-train on a basket of Indian + global symbols.
        
        Labels are generated PER-SYMBOL before concatenation to prevent
        cross-symbol data leakage from shift(-forward_window) in create_labels().
        """
        if symbols is None:
            symbols = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'SBIN',
                        'NIFTY50', 'BANKNIFTY']

        all_X = []
        all_y = []
        for sym in symbols:
            df = self.fetch_market_data(sym, period='2y')
            if df is not None and len(df) > 50:
                # Generate features and labels PER-SYMBOL so shift(-3) in
                # create_labels() never leaks across symbol boundaries
                X_sym = self.prepare_features(df)
                y_sym = self.create_labels(df)
                valid = y_sym.notna()
                X_sym = X_sym[valid]
                y_sym = y_sym[valid].astype(int)
                if len(X_sym) > 20:
                    all_X.append(X_sym)
                    all_y.append(y_sym)

        if not all_X:
            return {"error": "Could not fetch training data for any symbol"}

        combined_X = pd.concat(all_X).sort_index()
        combined_y = pd.concat(all_y).sort_index()
        return self._train_from_Xy(combined_X, combined_y)
    # Temperature for probability calibration — raw softmax is overconfident.
    # T > 1 softens probabilities (e.g. raw 0.95 → ~0.75 at T=2.0).
    TEMPERATURE = 2.0

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------
    def predict(self, df: pd.DataFrame) -> Dict:
        """Generate signal from latest data row with temperature-calibrated confidence."""
        if self.model is None:
            raise ValueError("Model not trained or loaded")

        features = self.prepare_features(df)
        latest = features.iloc[-1:]
        raw_proba = self.model.predict_proba(latest)[0]

        # Temperature scaling: apply to log-probabilities then re-normalize
        # This calibrates overconfident softmax outputs (e.g. 0.99 → 0.82)
        log_proba = np.log(raw_proba + 1e-10)
        scaled = np.exp(log_proba / self.TEMPERATURE)
        calibrated_proba = scaled / scaled.sum()

        idx = int(np.argmax(calibrated_proba))
        confidence = float(np.max(calibrated_proba))

        return {
            'signal': self.SIGNAL_CLASSES[idx],
            'confidence': round(confidence, 4),
            'raw_confidence': round(float(np.max(raw_proba)), 4),
            'probabilities': {
                cls: round(float(p), 4)
                for cls, p in zip(self.SIGNAL_CLASSES, calibrated_proba)
            },
            'model_version': self.MODEL_VERSION,
            'timestamp': datetime.now().isoformat(),
        }

    def predict_symbol(self, symbol: str) -> Dict:
        """End-to-end: fetch data → predict → return enriched signal."""
        df = self.fetch_market_data(symbol, period='6mo')
        if df is None or len(df) < 30:
            return self._fallback_signal(symbol)

        # If no model trained yet, auto-train
        if self.model is None:
            logger.info("No model found — running auto-train…")
            result = self.auto_train()
            if 'error' in result:
                return self._fallback_signal(symbol)

        try:
            signal = self.predict(df)
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return self._fallback_signal(symbol)

        # Enrich with market context
        signal['symbol'] = symbol
        signal['current_price'] = round(float(df['close'].iloc[-1]), 2)
        signal['market_regime'] = self._detect_regime(df)
        signal['support'] = round(float(df['low'].rolling(20).min().iloc[-1]), 2)
        signal['resistance'] = round(float(df['high'].rolling(20).max().iloc[-1]), 2)
        
        signal['signal_strength'] = self._classify_strength(signal['confidence'])

        return signal

    def predict_with_data(self, symbol: str, df: pd.DataFrame) -> Dict:
        """Predict using pre-fetched live data (e.g. 5-min intraday candles).

        This avoids the stale-daily-data problem in predict_symbol() by accepting
        the DataFrame that the caller already obtained from the broker API.
        Results are cached for CACHE_TTL_SECONDS with a data-hash key so that
        predictions refresh automatically when new candle data arrives.
        """
        if df is None or len(df) < 30:
            logger.warning(f"predict_with_data: insufficient rows ({0 if df is None else len(df)}) for {symbol}, falling back")
            return self.predict_symbol(symbol)

        # Normalise column names to lowercase (Dhan / Angel One use capitalised)
        col_map = {c: c.lower() for c in df.columns if not c.islower()}
        if col_map:
            df = df.rename(columns=col_map)

        # Ensure required columns exist
        for col in ('close', 'high', 'low', 'open', 'volume'):
            if col not in df.columns:
                logger.warning(f"predict_with_data: missing column '{col}' for {symbol}, falling back")
                return self.predict_symbol(symbol)

        # ---- Cache check (keyed on symbol + hash of last 10 close prices) ----
        try:
            last_closes = df['close'].iloc[-10:].values
            data_hash = hashlib.md5(last_closes.tobytes()).hexdigest()[:12]
        except Exception:
            data_hash = 'nohash'

        cached = self._prediction_cache.get(symbol)
        if cached:
            age = (datetime.now() - cached['timestamp']).total_seconds()
            if age < self.CACHE_TTL_SECONDS and cached.get('data_hash') == data_hash:
                logger.debug(f"predict_with_data cache HIT for {symbol} (age {age:.0f}s)")
                return cached['signal']

        # ---- Run prediction on live data ----
        if self.model is None:
            logger.info("No model found — running auto-train…")
            result = self.auto_train()
            if 'error' in result:
                return self._fallback_signal(symbol)

        try:
            signal = self.predict(df)
        except Exception as e:
            logger.error(f"predict_with_data failed for {symbol}: {e}")
            return self._fallback_signal(symbol)

        # Enrich with market context from live data
        signal['symbol'] = symbol
        signal['current_price'] = round(float(df['close'].iloc[-1]), 2)
        signal['market_regime'] = self._detect_regime(df)
        signal['support'] = round(float(df['low'].rolling(20).min().iloc[-1]), 2)
        signal['resistance'] = round(float(df['high'].rolling(20).max().iloc[-1]), 2)
        signal['signal_strength'] = self._classify_strength(signal['confidence'])
        signal['data_source'] = 'live_intraday'

        # Store in cache
        self._prediction_cache[symbol] = {
            'signal': signal,
            'data_hash': data_hash,
            'timestamp': datetime.now(),
        }
        logger.info(f"predict_with_data: {symbol} => {signal['signal']} conf={signal['confidence']:.4f} (live, hash={data_hash})")
        return signal

    def _fallback_signal(self, symbol: str) -> Dict:
        """Technical-indicator-only fallback when ML model unavailable."""
        df = self.fetch_market_data(symbol, period='3mo')
        if df is None or len(df) < 30:
            return {
                'symbol': symbol, 'signal': 'HOLD', 'confidence': 0.50,
                'probabilities': {'SELL': 0.25, 'HOLD': 0.50, 'BUY': 0.25},
                'model_version': 'fallback', 'signal_strength': 'Weak',
                'timestamp': datetime.now().isoformat(),
                'note': 'Insufficient data — defaulting to HOLD'
            }

        features = self.prepare_features(df)
        row = features.iloc[-1]
        score = 0.0
        # Simple rule-based scoring
        if row['rsi'] < 30: score += 0.3
        elif row['rsi'] > 70: score -= 0.3
        if row['macd_hist'] > 0: score += 0.2
        else: score -= 0.2
        if row['sma_20_cross'] > 0.5: score += 0.15
        if row['volume_ratio'] > 1.2: score += 0.1

        if score > 0.2:
            sig, conf = 'BUY', round(0.5 + score, 4)
        elif score < -0.2:
            sig, conf = 'SELL', round(0.5 + abs(score), 4)
        else:
            sig, conf = 'HOLD', 0.5

        return {
            'symbol': symbol, 'signal': sig,
            'confidence': round(conf, 4),
            'probabilities': {'SELL': 0.33, 'HOLD': 0.34, 'BUY': 0.33},
            'current_price': round(float(df['close'].iloc[-1]), 2),
            'model_version': 'fallback-rules',
            'signal_strength': self._classify_strength(conf),
            'market_regime': self._detect_regime(df),
            'timestamp': datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _detect_regime(self, df: pd.DataFrame) -> str:
        """Detect market regime: trending / ranging / volatile."""
        close = df['close']
        vol = close.pct_change().rolling(20).std().iloc[-1]
        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else sma20
        trend_strength = abs(sma20 - sma50) / (sma50 + 1e-10)

        if vol > 0.025:
            return 'volatile'
        elif trend_strength > 0.02:
            return 'trending'
        else:
            return 'ranging'

    @staticmethod
    def _classify_strength(confidence: float) -> str:
        if confidence >= 0.75:
            return 'Strong'
        elif confidence >= 0.60:
            return 'Medium'
        return 'Weak'

    def save_model(self):
        os.makedirs(self.model_dir, exist_ok=True)
        payload = {
            'model': self.model,
            'version': self.MODEL_VERSION,
            'trained_at': self._trained_at,
            'accuracy': self._accuracy,
            'features': self.feature_columns,
        }
        with open(self.model_path, 'wb') as f:
            pickle.dump(payload, f)
        logger.info(f"Model saved to {self.model_path}")

    def load_model(self):
        with open(self.model_path, 'rb') as f:
            payload = pickle.load(f)
        self.model = payload['model']
        self._trained_at = payload.get('trained_at')
        self._accuracy = payload.get('accuracy')
        logger.info(f"Model loaded (v{payload.get('version', '?')})")

    def get_model_info(self) -> Dict:
        return {
            'model_version': self.MODEL_VERSION,
            'trained_at': self._trained_at,
            'accuracy': self._accuracy if self._accuracy else 0.0,
            'model_loaded': self.model is not None,
            'features': self.feature_columns,
        }
