"""
Authentication and Authorization Decorators
Handles subscription-based feature access control
"""

from functools import wraps
from flask import session, jsonify, redirect, url_for, flash, request
from models.subscription import SubscriptionManager, SubscriptionTier
import logging

logger = logging.getLogger(__name__)


def require_login(f):
    """Decorator to require user login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def require_plan(min_plan='premium'):
    """Decorator to restrict access based on subscription tier"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if request.is_json:
                    return jsonify({'error': 'Authentication required'}), 401
                flash('Please log in to access this feature.', 'warning')
                return redirect(url_for('login'))
            
            user_id = session['user_id']
            
            # Initialize subscription manager
            sub_manager = SubscriptionManager()
            subscription = sub_manager.get_subscription(user_id)
            
            # Determine current tier
            if not subscription:
                current_tier = SubscriptionTier.FREE
            else:
                try:
                    current_tier = SubscriptionTier(subscription['plan_type'])
                except ValueError:
                    current_tier = SubscriptionTier.FREE
            
            # Check tier levels
            tier_levels = {
                'free': 0,
                'premium': 1,
                'pro': 2,
                'enterprise': 3
            }
            
            current_level = tier_levels.get(current_tier.value, 0)
            required_level = tier_levels.get(min_plan, 1)
            
            if current_level < required_level:
                if request.is_json:
                    return jsonify({
                        'error': 'Subscription required',
                        'required_plan': min_plan,
                        'current_plan': current_tier.value,
                        'upgrade_url': '/subscription'
                    }), 403
                flash(f'This feature requires a {min_plan.title()} subscription. Please upgrade.', 'info')
                return redirect(url_for('subscription'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_feature(feature_name):
    """Decorator to check if user can access a specific feature"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if request.is_json:
                    return jsonify({'error': 'Authentication required'}), 401
                return redirect(url_for('login'))
            
            user_id = session['user_id']
            sub_manager = SubscriptionManager()
            
            if not sub_manager.can_access_feature(user_id, feature_name):
                if request.is_json:
                    return jsonify({
                        'error': f'Feature "{feature_name}" not available on your plan',
                        'upgrade_url': '/subscription'
                    }), 403
                flash(f'This feature is not available on your current plan. Please upgrade.', 'info')
                return redirect(url_for('subscription'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def check_signal_quota(f):
    """Decorator to enforce daily signal quota"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('login'))
        
        user_id = session['user_id']
        sub_manager = SubscriptionManager()
        
        can_use, remaining = sub_manager.check_signal_quota(user_id)
        
        if not can_use:
            if request.is_json:
                return jsonify({
                    'error': 'Daily signal limit reached',
                    'message': 'Upgrade to Premium for unlimited signals.',
                    'upgrade_url': '/subscription'
                }), 429
            flash('You have reached your daily signal limit. Upgrade to Premium for unlimited signals.', 'warning')
            return redirect(url_for('subscription'))
        
        # Record usage
        sub_manager.record_feature_usage(user_id, 'signal')
        
        return f(*args, **kwargs)
    return decorated_function


# Convenience decorators for common use cases
def require_premium(f):
    """Require Premium or higher subscription"""
    return require_plan('premium')(f)


def require_pro(f):
    """Require Pro or higher subscription"""
    return require_plan('pro')(f)


def require_enterprise(f):
    """Require Enterprise subscription"""
    return require_plan('enterprise')(f)
