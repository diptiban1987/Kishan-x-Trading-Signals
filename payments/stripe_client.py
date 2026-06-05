"""
Stripe Payment Integration
Handles checkout sessions, subscriptions, and webhooks
"""

import os
import stripe
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class StripePaymentClient:
    """Stripe payment processing client"""

    # Plan price IDs (to be configured in Stripe Dashboard)
    PLAN_PRICES = {
        "premium_monthly": "price_premium_monthly",  # Replace with actual Stripe price ID
        "premium_yearly": "price_premium_yearly",
        "pro_monthly": "price_pro_monthly",
        "pro_yearly": "price_pro_yearly",
    }

    def __init__(self):
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

        if not stripe.api_key:
            logger.warning("STRIPE_SECRET_KEY not set. Payment processing will not work.")

    def create_customer(self, email: str, name: str, user_id: int) -> Dict:
        """Create a Stripe customer"""
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"user_id": user_id},
            )
            logger.info(f"Stripe customer created: {customer.id} for user {user_id}")
            return {
                "customer_id": customer.id,
                "email": customer.email,
                "status": "created",
            }
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise

    def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        trial_days: int = 7,
    ) -> Dict:
        """Create a Stripe Checkout session for subscription"""
        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                subscription_data={
                    "trial_period_days": trial_days,
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )

            logger.info(f"Checkout session created: {session.id}")
            return {
                "session_id": session.id,
                "url": session.url,
                "status": "created",
            }
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create checkout session: {e}")
            raise

    def create_subscription(
        self, customer_id: str, price_id: str, trial_days: int = 7
    ) -> Dict:
        """Create a subscription directly (for backend use)"""
        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
                trial_period_days=trial_days,
                payment_behavior="default_incomplete",
                expand=["latest_invoice.payment_intent"],
            )

            logger.info(f"Subscription created: {subscription.id}")
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "client_secret": subscription.latest_invoice.payment_intent.client_secret
                if hasattr(subscription.latest_invoice, "payment_intent")
                else None,
            }
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create subscription: {e}")
            raise

    def cancel_subscription(self, subscription_id: str) -> Dict:
        """Cancel a subscription at period end"""
        try:
            subscription = stripe.Subscription.modify(
                subscription_id, cancel_at_period_end=True
            )

            logger.info(f"Subscription cancelled: {subscription_id}")
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
            }
        except stripe.error.StripeError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            raise

    def get_subscription(self, subscription_id: str) -> Dict:
        """Get subscription details"""
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return {
                "id": subscription.id,
                "status": subscription.status,
                "current_period_end": subscription.current_period_end,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "plan": subscription.plan.id if subscription.plan else None,
            }
        except stripe.error.StripeError as e:
            logger.error(f"Failed to get subscription: {e}")
            raise

    def create_customer_portal_session(self, customer_id: str, return_url: str) -> Dict:
        """Create a customer portal session for billing management"""
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )

            return {
                "url": session.url,
                "status": "created",
            }
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create portal session: {e}")
            raise

    def handle_webhook(self, payload: bytes, sig_header: str) -> Dict:
        """Handle Stripe webhook events"""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )

            logger.info(f"Webhook received: {event['type']}")

            if event["type"] == "checkout.session.completed":
                return self._handle_checkout_completed(event["data"]["object"])

            elif event["type"] == "invoice.payment_succeeded":
                return self._handle_payment_succeeded(event["data"]["object"])

            elif event["type"] == "invoice.payment_failed":
                return self._handle_payment_failed(event["data"]["object"])

            elif event["type"] == "customer.subscription.deleted":
                return self._handle_subscription_deleted(event["data"]["object"])

            elif event["type"] == "customer.subscription.updated":
                return self._handle_subscription_updated(event["data"]["object"])

            return {"status": "unhandled", "event": event["type"]}

        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Webhook handling error: {e}")
            raise

    def _handle_checkout_completed(self, session) -> Dict:
        """Handle checkout.session.completed"""
        logger.info(f"Checkout completed for customer: {session.customer}")
        return {
            "event": "checkout.session.completed",
            "customer_id": session.customer,
            "subscription_id": session.subscription,
            "status": "success",
        }

    def _handle_payment_succeeded(self, invoice) -> Dict:
        """Handle invoice.payment.succeeded"""
        logger.info(f"Payment succeeded for subscription: {invoice.subscription}")
        return {
            "event": "invoice.payment_succeeded",
            "subscription_id": invoice.subscription,
            "amount_paid": invoice.amount_paid,
            "status": "success",
        }

    def _handle_payment_failed(self, invoice) -> Dict:
        """Handle invoice.payment_failed"""
        logger.warning(f"Payment failed for subscription: {invoice.subscription}")
        return {
            "event": "invoice.payment_failed",
            "subscription_id": invoice.subscription,
            "status": "failed",
        }

    def _handle_subscription_deleted(self, subscription) -> Dict:
        """Handle customer.subscription.deleted"""
        logger.info(f"Subscription deleted: {subscription.id}")
        return {
            "event": "customer.subscription.deleted",
            "subscription_id": subscription.id,
            "status": "cancelled",
        }

    def _handle_subscription_updated(self, subscription) -> Dict:
        """Handle customer.subscription.updated"""
        logger.info(f"Subscription updated: {subscription.id}")
        return {
            "event": "customer.subscription.updated",
            "subscription_id": subscription.id,
            "status": subscription.status,
        }
