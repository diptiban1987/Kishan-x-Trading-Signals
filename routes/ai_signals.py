"""
AI Signal Generation API Routes — Production Version
Provides real AI-powered trading signals with subscription-based access control.
"""

from flask import Blueprint, request, jsonify, session
import logging
from datetime import datetime

from auth.decorators import require_login, require_plan, check_signal_quota
from ai_models.signal_predictor import AISignalPredictor
from models.subscription import SubscriptionManager
from ai_models.gemini_explainer import gemini_client

logger = logging.getLogger(__name__)

ai_signals_bp = Blueprint('ai_signals', __name__, url_prefix='/api/ai-signals')

# Singleton predictor — loads/trains once
_predictor = None
_sub_manager = None


def _get_predictor() -> AISignalPredictor:
    global _predictor
    if _predictor is None:
        _predictor = AISignalPredictor()
    return _predictor


def _get_sub_manager() -> SubscriptionManager:
    global _sub_manager
    if _sub_manager is None:
        _sub_manager = SubscriptionManager()
    return _sub_manager


@ai_signals_bp.route('/predict', methods=['POST'])
@require_login
@require_plan('premium')
def predict_signal():
    """Generate real AI-powered trading signal for a symbol."""
    data = request.get_json() or {}
    symbol = data.get('symbol', '').strip().upper()

    if not symbol:
        return jsonify({"error": "Symbol required"}), 400

    try:
        predictor = _get_predictor()
        signal = predictor.predict_symbol(symbol)

        # Generate Gemini AI commentary if signal is BUY or SELL
        if signal and signal.get('signal') in ('BUY', 'SELL'):
            try:
                indicators_context = {
                    "support": signal.get("support"),
                    "resistance": signal.get("resistance"),
                    "market_regime": signal.get("market_regime")
                }
                commentary = gemini_client.explain_signal(
                    symbol=symbol,
                    direction=signal.get('signal'),
                    confidence=signal.get('confidence', 0.5),
                    current_price=signal.get('current_price', 0.0),
                    indicators=indicators_context
                )
                signal['ai_commentary'] = commentary
            except Exception as gem_e:
                logger.warning(f"Failed to generate Gemini commentary for {symbol}: {gem_e}")
                signal['ai_commentary'] = gemini_client._get_rule_based_signal_fallback(
                    symbol=symbol,
                    direction=signal.get('signal'),
                    confidence=signal.get('confidence', 0.5),
                    current_price=signal.get('current_price', 0.0),
                    indicators={}
                )

        # Record feature usage
        sub_mgr = _get_sub_manager()
        sub_mgr.record_feature_usage(session['user_id'], 'ai_signal')

        return jsonify({"status": "success", "signal": signal})

    except Exception as e:
        logger.error(f"AI prediction error for {symbol}: {e}")
        return jsonify({"error": f"Failed to generate signal: {str(e)}"}), 500


@ai_signals_bp.route('/batch', methods=['POST'])
@require_login
@require_plan('premium')
def batch_predict():
    """Generate AI signals for multiple symbols."""
    data = request.get_json() or {}
    symbols = data.get('symbols', [])

    if not symbols:
        return jsonify({"error": "Symbols list required"}), 400

    if len(symbols) > 20:
        return jsonify({"error": "Maximum 20 symbols per batch"}), 400

    predictor = _get_predictor()
    sub_mgr = _get_sub_manager()
    signals = []

    for sym in symbols:
        try:
            signal = predictor.predict_symbol(sym.strip().upper())
            
            # Generate Gemini AI commentary for batch symbols if active
            if signal and signal.get('signal') in ('BUY', 'SELL') and gemini_client.is_active():
                try:
                    commentary = gemini_client.explain_signal(
                        symbol=sym,
                        direction=signal.get('signal'),
                        confidence=signal.get('confidence', 0.5),
                        current_price=signal.get('current_price', 0.0),
                        indicators={}
                    )
                    signal['ai_commentary'] = commentary
                except Exception:
                    pass
                    
            signals.append(signal)
            sub_mgr.record_feature_usage(session['user_id'], 'ai_signal')
        except Exception as e:
            logger.warning(f"Batch prediction failed for {sym}: {e}")
            signals.append({
                "symbol": sym, "signal": "HOLD", "confidence": 0.0,
                "error": str(e)
            })

    return jsonify({"status": "success", "signals": signals,
                     "count": len(signals)})


@ai_signals_bp.route('/performance', methods=['GET'])
@require_login
@require_plan('premium')
def get_performance():
    """Get real AI model performance metrics."""
    predictor = _get_predictor()
    info = predictor.get_model_info()

    return jsonify({
        "status": "success",
        "performance": {
            "model_version": info['model_version'],
            "accuracy": info.get('accuracy', 0.0),
            "model_loaded": info['model_loaded'],
            "trained_at": info.get('trained_at'),
            "features_used": len(info['features']),
            "feature_names": info['features'],
        }
    })


@ai_signals_bp.route('/train', methods=['POST'])
@require_login
@require_plan('pro')
def train_model():
    """Trigger real AI model training (Pro only)."""
    data = request.get_json() or {}
    symbols = data.get('symbols', None)

    try:
        predictor = _get_predictor()
        result = predictor.auto_train(symbols)

        if 'error' in result:
            return jsonify({"status": "error", "message": result['error']}), 400

        return jsonify({
            "status": "success",
            "message": "Model trained successfully",
            "accuracy": result.get('accuracy'),
            "training_samples": result.get('training_samples'),
            "validation_samples": result.get('validation_samples'),
            "model_version": result.get('model_version'),
        })

    except Exception as e:
        logger.error(f"Training error: {e}")
        return jsonify({"error": f"Training failed: {str(e)}"}), 500


@ai_signals_bp.route('/model-info', methods=['GET'])
@require_login
def get_model_info():
    """Get model info (available to all logged-in users)."""
    predictor = _get_predictor()
    info = predictor.get_model_info()
    return jsonify({"status": "success", "model": info})


@ai_signals_bp.route('/quick-scan', methods=['GET'])
@require_login
def quick_scan():
    """Quick market scan — free tier gets limited results, premium gets full."""
    default_symbols = ['NIFTY50', 'BANKNIFTY', 'RELIANCE', 'TCS',
                       'HDFCBANK', 'INFY']

    sub_mgr = _get_sub_manager()
    subscription = sub_mgr.get_subscription(session.get('user_id'))
    plan = subscription['plan_type'] if subscription else 'free'

    if plan == 'free':
        scan_symbols = default_symbols[:2]  # Free: only 2 symbols
    else:
        scan_symbols = default_symbols  # Premium+: all

    predictor = _get_predictor()
    results = []

    for sym in scan_symbols:
        try:
            signal = predictor.predict_symbol(sym)
            results.append(signal)
        except Exception as e:
            logger.warning(f"Quick scan failed for {sym}: {e}")

    return jsonify({
        "status": "success",
        "plan": plan,
        "symbols_scanned": len(results),
        "total_available": len(default_symbols),
        "signals": results,
        "upgrade_message": "Upgrade to Premium for full market scan"
                           if plan == 'free' else None,
    })
