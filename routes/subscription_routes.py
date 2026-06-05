"""
Subscription Management API Routes — Production Version
Handles subscription CRUD, Stripe + Razorpay payments, and webhooks.
"""

from flask import Blueprint, request, jsonify, session, redirect
import os
import json
import logging
from datetime import datetime

from models.subscription import SubscriptionManager, SubscriptionStatus
from payments.stripe_client import StripePaymentClient
from payments.razorpay_client import RazorpayPaymentClient
from auth.decorators import require_login

logger = logging.getLogger(__name__)

def _get_sub_db_path():
    """Get database path from branding config, fallback to hardcoded path."""
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), _get_sub_db_path())

subscription_bp = Blueprint('subscription', __name__,
                            url_prefix='/api/subscriptions')

# Singletons
_sub_manager = None
_stripe_client = None
_razorpay_client = None


def _get_sub_manager():
    global _sub_manager
    if _sub_manager is None:
        _sub_manager = SubscriptionManager()
    return _sub_manager


def _get_stripe():
    global _stripe_client
    if _stripe_client is None:
        _stripe_client = StripePaymentClient()
    return _stripe_client


def _get_razorpay():
    global _razorpay_client
    if _razorpay_client is None:
        _razorpay_client = RazorpayPaymentClient()
    return _razorpay_client


# ------------------------------------------------------------------
# Plan information
# ------------------------------------------------------------------
@subscription_bp.route('/plans', methods=['GET'])
def get_plans():
    """Get available subscription plans and pricing."""
    sub_mgr = _get_sub_manager()
    pricing = sub_mgr.get_pricing()

    plans = {
        "free": {
            "name": "Free", "price_usd": 0, "price_inr": 0,
            "features": [
                "5 signals per day", "Basic technical indicators",
                "Email support", "Portfolio tracking",
            ],
        },
        "premium": {
            "name": "Premium",
            "price_usd": pricing.get("premium", {}).get("monthly", 49),
            "price_inr": 3999,
            "yearly_usd": pricing.get("premium", {}).get("yearly"),
            "yearly_inr": 38399,
            "features": [
                "Unlimited AI signals", "Auto-trading (1 strategy)",
                "Real-time data", "Advanced analytics",
                "Priority support", "Market regime detection",
            ],
        },
        "pro": {
            "name": "Pro",
            "price_usd": pricing.get("pro", {}).get("monthly", 99),
            "price_inr": 7999,
            "yearly_usd": pricing.get("pro", {}).get("yearly"),
            "yearly_inr": 76799,
            "features": [
                "Everything in Premium", "Multiple strategies",
                "API access", "Custom model training",
                "24/7 support", "Up to 5 team members",
            ],
        },
        "enterprise": {
            "name": "Enterprise",
            "price_usd": "Custom",
            "price_inr": "Custom",
            "yearly_usd": "Custom",
            "yearly_inr": "Custom",
            "features": [
                "Everything in Pro",
                "Custom white-label solutions",
                "Unlimited team members",
                "Dedicated institutional servers",
                "SLA uptime guarantee (99.99%)",
                "Direct developer API integrations",
                "24/7 dedicated support team",
            ],
        },
    }

    return jsonify({"status": "success", "plans": plans})


# ------------------------------------------------------------------
# Current subscription
# ------------------------------------------------------------------
@subscription_bp.route('/current', methods=['GET'])
@require_login
def get_current_subscription():
    """Get current user's subscription details."""
    sub_mgr = _get_sub_manager()
    user_id = session['user_id']
    subscription = sub_mgr.get_subscription(user_id)

    if not subscription:
        try:
            from app import get_user_plan
            legacy_plan = get_user_plan(user_id)
        except Exception:
            legacy_plan = "free"
            
        return jsonify({
            "status": "success",
            "subscription": {
                "plan_type": legacy_plan, "status": "active",
                "features": sub_mgr.get_plan_limits(legacy_plan),
            }
        })

    return jsonify({
        "status": "success",
        "subscription": {
            "plan_type": subscription["plan_type"],
            "status": subscription["status"],
            "current_period_start": subscription["current_period_start"],
            "current_period_end": subscription["current_period_end"],
            "trial_end": subscription.get("trial_end"),
            "features": sub_mgr.get_plan_limits(subscription["plan_type"]),
        }
    })


# ------------------------------------------------------------------
# Razorpay checkout (Indian market)
# ------------------------------------------------------------------
@subscription_bp.route('/razorpay/create-order', methods=['POST'])
@require_login
def razorpay_create_order():
    """Create a Razorpay order for subscription payment."""
    data = request.get_json() or {}
    plan_type = data.get('plan_type', 'premium')
    billing_cycle = data.get('billing_cycle', 'monthly')
    plan_key = f"{plan_type}_{billing_cycle}"

    rz = _get_razorpay()
    if not rz.is_configured:
        # Demo fallback
        sub_mgr = _get_sub_manager()
        sub_mgr.create_subscription(
            user_id=session['user_id'], plan_type=plan_type,
            provider='demo', trial_days=7,
        )
        return jsonify({
            "status": "demo_mode",
            "message": "Razorpay not configured. Demo subscription activated.",
            "plan_type": plan_type,
        })

    user_id = session['user_id']
    result = rz.create_order(plan_key, user_id)

    if 'error' in result:
        return jsonify({"status": "error", "message": result['error']}), 400

    return jsonify({"status": "success", **result})


@subscription_bp.route('/razorpay/verify', methods=['POST'])
@require_login
def razorpay_verify():
    """Verify Razorpay payment and activate subscription."""
    data = request.get_json() or {}
    order_id = data.get('razorpay_order_id')
    payment_id = data.get('razorpay_payment_id')
    signature = data.get('razorpay_signature')
    plan_type = data.get('plan_type', 'premium')

    if not all([order_id, payment_id, signature]):
        return jsonify({"error": "Missing payment details"}), 400

    rz = _get_razorpay()
    if not rz.verify_payment(order_id, payment_id, signature):
        return jsonify({"error": "Payment verification failed"}), 400

    # Activate subscription
    sub_mgr = _get_sub_manager()
    user_id = session['user_id']
    sub_mgr.create_subscription(
        user_id=user_id, plan_type=plan_type,
        provider='razorpay',
        provider_subscription_id=payment_id,
        provider_customer_id=order_id,
        trial_days=0,
    )

    # Record payment
    sub_mgr.record_payment(
        user_id=user_id, provider='razorpay',
        provider_payment_id=payment_id,
        amount=data.get('amount', 0) / 100,  # paise → rupees
        currency='INR', status='succeeded',
    )

    logger.info(f"Razorpay payment verified — user {user_id} → {plan_type}")
    return jsonify({
        "status": "success",
        "message": f"Welcome to {plan_type.title()}! Your subscription is now active.",
        "plan_type": plan_type,
    })


# ------------------------------------------------------------------
# Stripe checkout (global)
# ------------------------------------------------------------------
@subscription_bp.route('/create-checkout', methods=['POST'])
@require_login
def create_checkout():
    """Create Stripe checkout session for subscription."""
    data = request.get_json() or {}
    plan_type = data.get('plan_type', 'premium')
    billing_cycle = data.get('billing_cycle', 'monthly')

    price_key = f"{plan_type}_{billing_cycle}"
    stripe_cl = _get_stripe()
    price_id = stripe_cl.PLAN_PRICES.get(price_key)

    if not price_id or price_id.startswith("price_") and "_" in price_id:
        # Demo fallback
        sub_mgr = _get_sub_manager()
        sub_mgr.create_subscription(
            user_id=session['user_id'], plan_type=plan_type,
            provider='demo', trial_days=7,
        )
        return jsonify({
            "status": "demo_mode",
            "message": "Stripe not configured. Demo subscription activated.",
            "plan_type": plan_type,
        })

    # Real Stripe flow
    user_id = session['user_id']
    sub_mgr = _get_sub_manager()
    subscription = sub_mgr.get_subscription(user_id)

    if subscription and subscription.get("provider_customer_id"):
        customer_id = subscription["provider_customer_id"]
    else:
        import sqlite3
        conn = sqlite3.connect(_get_sub_db_path())
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        conn.close()
        email = f"user{user_id}@tradingplatform.local"
        name = user['username'] if user else f"User {user_id}"
        customer = stripe_cl.create_customer(email, name, user_id)
        customer_id = customer["customer_id"]

    success_url = request.host_url + "subscription?success=true"
    cancel_url = request.host_url + "subscription?cancelled=true"

    checkout = stripe_cl.create_checkout_session(
        customer_id=customer_id, price_id=price_id,
        success_url=success_url, cancel_url=cancel_url, trial_days=7,
    )
    return jsonify({
        "status": "success",
        "session_id": checkout["session_id"],
        "url": checkout["url"],
    })


# ------------------------------------------------------------------
# Cancel / Upgrade
# ------------------------------------------------------------------
@subscription_bp.route('/cancel', methods=['POST'])
@require_login
def cancel_subscription():
    """Cancel user's subscription."""
    sub_mgr = _get_sub_manager()
    user_id = session['user_id']
    data = request.get_json() or {}
    reason = data.get('reason', 'User requested')

    subscription = sub_mgr.get_subscription(user_id)
    if not subscription or subscription["plan_type"] == "free":
        return jsonify({"status": "error",
                        "message": "No active paid subscription found"}), 400

    if subscription.get("provider_subscription_id"):
        provider = subscription.get("provider", "")
        if provider == "stripe":
            try:
                _get_stripe().cancel_subscription(
                    subscription["provider_subscription_id"])
            except Exception as e:
                logger.error(f"Stripe cancel failed: {e}")

    sub_mgr.update_subscription_status(
        user_id, SubscriptionStatus.CANCELLED.value, reason)

    return jsonify({
        "status": "success",
        "message": "Subscription cancelled. Access continues until billing period ends.",
    })


@subscription_bp.route('/upgrade', methods=['POST'])
@require_login
def upgrade_subscription():
    """Upgrade subscription plan."""
    data = request.get_json() or {}
    new_plan = data.get('plan_type')
    if not new_plan:
        return jsonify({"error": "Plan type required"}), 400

    sub_mgr = _get_sub_manager()
    result = sub_mgr.upgrade_plan(session['user_id'], new_plan)
    return jsonify({
        "status": "success",
        "message": f"Upgraded to {new_plan} plan",
        "subscription": result,
    })


# ------------------------------------------------------------------
# Invoices & Usage
# ------------------------------------------------------------------
@subscription_bp.route('/invoices', methods=['GET'])
@require_login
def get_invoices():
    """Get payment history."""
    import sqlite3
    conn = sqlite3.connect(_get_sub_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC",
                (session['user_id'],))
    invoices = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"status": "success", "invoices": invoices})


@subscription_bp.route('/usage', methods=['GET'])
@require_login
def get_usage():
    """Get feature usage stats."""
    import sqlite3
    sub_mgr = _get_sub_manager()
    user_id = session['user_id']

    conn = sqlite3.connect(_get_sub_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""SELECT feature_name, usage_count FROM feature_usage
                   WHERE user_id = ? AND usage_date = DATE('now')""",
                (user_id,))
    today_usage = {r['feature_name']: r['usage_count'] for r in cur.fetchall()}
    conn.close()

    subscription = sub_mgr.get_subscription(user_id)
    plan_type = subscription["plan_type"] if subscription else "free"
    limits = sub_mgr.get_plan_limits(plan_type)

    return jsonify({
        "status": "success", "today_usage": today_usage,
        "plan_limits": limits, "plan_type": plan_type,
    })


# ------------------------------------------------------------------
# Webhooks
# ------------------------------------------------------------------
@subscription_bp.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events."""
    payload = request.get_data()
    sig = request.headers.get('Stripe-Signature')
    stripe_cl = _get_stripe()
    sub_mgr = _get_sub_manager()

    try:
        result = stripe_cl.handle_webhook(payload, sig)
        event = result.get("event", "")

        if event == "checkout.session.completed":
            cust_id = result.get("customer_id")
            _activate_by_customer(sub_mgr, cust_id, "stripe",
                                  result.get("subscription_id"))

        elif event == "invoice.payment_succeeded":
            sub_id = result.get("subscription_id")
            logger.info(f"Payment succeeded for subscription {sub_id}")

        elif event == "invoice.payment_failed":
            sub_id = result.get("subscription_id")
            _mark_past_due_by_provider(sub_mgr, "stripe", sub_id)

        elif event == "customer.subscription.deleted":
            sub_id = result.get("subscription_id")
            _cancel_by_provider(sub_mgr, "stripe", sub_id)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return jsonify({"error": "Webhook processing failed"}), 400


@subscription_bp.route('/webhook/razorpay', methods=['POST'])
def razorpay_webhook():
    """Handle Razorpay webhook events."""
    rz = _get_razorpay()
    sub_mgr = _get_sub_manager()

    body = request.get_data()
    sig = request.headers.get('X-Razorpay-Signature', '')

    if not rz.verify_webhook_signature(body, sig):
        return jsonify({"error": "Invalid signature"}), 400

    try:
        payload = json.loads(body)
        event = payload.get("event", "")
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})

        if event == "payment.captured":
            notes = entity.get("notes", {})
            user_id = notes.get("user_id")
            plan = notes.get("plan", "premium").split("_")[0]
            if user_id:
                sub_mgr.create_subscription(
                    user_id=int(user_id), plan_type=plan,
                    provider='razorpay',
                    provider_subscription_id=entity.get("id"),
                    trial_days=0,
                )
                logger.info(f"Razorpay webhook: activated {plan} for user {user_id}")

        elif event == "payment.failed":
            logger.warning(f"Razorpay payment failed: {entity.get('id')}")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Razorpay webhook error: {e}")
        return jsonify({"error": str(e)}), 400


# ------------------------------------------------------------------
# Webhook helpers
# ------------------------------------------------------------------
def _activate_by_customer(sub_mgr, customer_id, provider, sub_id):
    """Activate subscription by provider customer ID."""
    import sqlite3
    conn = sqlite3.connect(_get_sub_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM subscriptions WHERE provider_customer_id = ?",
                (customer_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        sub_mgr.update_subscription_status(
            row['user_id'], SubscriptionStatus.ACTIVE.value)
        logger.info(f"Activated subscription for user {row['user_id']}")


def _mark_past_due_by_provider(sub_mgr, provider, sub_id):
    import sqlite3
    conn = sqlite3.connect(_get_sub_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM subscriptions WHERE provider_subscription_id = ?",
                (sub_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        sub_mgr.update_subscription_status(
            row['user_id'], SubscriptionStatus.PAST_DUE.value)


def _cancel_by_provider(sub_mgr, provider, sub_id):
    import sqlite3
    conn = sqlite3.connect(_get_sub_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM subscriptions WHERE provider_subscription_id = ?",
                (sub_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        sub_mgr.update_subscription_status(
            row['user_id'], SubscriptionStatus.CANCELLED.value,
            "Payment provider cancelled")
