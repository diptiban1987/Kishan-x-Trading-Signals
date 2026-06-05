"""
Razorpay Payment Integration
Indian market payment processing: order creation, verification, webhooks.
"""

import os
import hmac
import hashlib
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Lazy import — razorpay may not be installed
_razorpay = None


def _ensure_razorpay():
    global _razorpay
    if _razorpay is None:
        try:
            import razorpay
            _razorpay = razorpay
        except ImportError:
            logger.warning("razorpay package not installed. Run: pip install razorpay")
            raise ImportError("razorpay package not installed")


class RazorpayPaymentClient:
    """Razorpay payment processing for Indian subscriptions (INR)."""

    PLAN_PRICES_INR = {
        "premium_monthly": 399900,   # ₹3,999/month (in paise)
        "premium_yearly": 3839900,   # ₹38,399/year (20% off)
        "pro_monthly": 799900,       # ₹7,999/month
        "pro_yearly": 7679900,       # ₹76,799/year (20% off)
    }

    PLAN_NAMES = {
        "premium_monthly": "Premium Plan — Monthly",
        "premium_yearly": "Premium Plan — Annual (Save 20%)",
        "pro_monthly": "Pro Plan — Monthly",
        "pro_yearly": "Pro Plan — Annual (Save 20%)",
    }

    def __init__(self):
        self.key_id = os.getenv("RAZORPAY_KEY_ID", "")
        self.key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
        self.webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
        self.client = None

        if self.key_id and self.key_secret:
            try:
                _ensure_razorpay()
                self.client = _razorpay.Client(
                    auth=(self.key_id, self.key_secret)
                )
                logger.info("Razorpay client initialized")
            except Exception as e:
                logger.warning(f"Razorpay init failed: {e}")
        else:
            logger.warning("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set")

    @property
    def is_configured(self) -> bool:
        return self.client is not None

    def create_order(self, plan_key: str, user_id: int,
                     receipt: str = None) -> Dict:
        """Create a Razorpay order for the given plan."""
        if not self.is_configured:
            return {"error": "Razorpay not configured", "demo_mode": True}

        amount = self.PLAN_PRICES_INR.get(plan_key)
        if not amount:
            return {"error": f"Unknown plan: {plan_key}"}

        receipt = receipt or f"order_user{user_id}_{plan_key}"

        try:
            order = self.client.order.create({
                "amount": amount,
                "currency": "INR",
                "receipt": receipt[:40],
                "notes": {
                    "user_id": str(user_id),
                    "plan": plan_key,
                },
            })
            logger.info(f"Razorpay order created: {order['id']}")
            return {
                "order_id": order["id"],
                "amount": order["amount"],
                "currency": order["currency"],
                "key_id": self.key_id,
                "plan_name": self.PLAN_NAMES.get(plan_key, plan_key),
                "status": "created",
            }
        except Exception as e:
            logger.error(f"Razorpay order creation failed: {e}")
            return {"error": str(e)}

    def verify_payment(self, razorpay_order_id: str,
                       razorpay_payment_id: str,
                       razorpay_signature: str) -> bool:
        """Verify payment signature (server-side verification)."""
        if not self.key_secret:
            logger.error("Cannot verify — key_secret not set")
            return False

        message = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected = hmac.new(
            self.key_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, razorpay_signature)

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify webhook payload signature."""
        if not self.webhook_secret:
            logger.warning("Webhook secret not set — skipping verification")
            return True

        expected = hmac.new(
            self.webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def fetch_payment(self, payment_id: str) -> Optional[Dict]:
        """Fetch payment details from Razorpay."""
        if not self.is_configured:
            return None
        try:
            return self.client.payment.fetch(payment_id)
        except Exception as e:
            logger.error(f"Failed to fetch payment {payment_id}: {e}")
            return None
