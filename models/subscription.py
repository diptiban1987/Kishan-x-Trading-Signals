"""
Subscription and Payment Models
Handles subscription tiers, payments, and feature access control
"""

import sqlite3
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


def _get_default_db_path():
    try:
        from branding_config import branding
        return branding.db_path
    except ImportError:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'trading.db')


class SubscriptionTier(Enum):
    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    UNPAID = "unpaid"


class SubscriptionManager:
    """Manages subscription lifecycle and feature access"""

    # Feature limits per tier
    TIER_LIMITS = {
        SubscriptionTier.FREE: {
            "daily_signals": 5,
            "ai_signals": False,
            "auto_trading": False,
            "real_time_data": False,
            "advanced_analytics": False,
            "api_access": False,
            "custom_strategies": False,
            "support": "email",
            "team_members": 1,
        },
        SubscriptionTier.PREMIUM: {
            "daily_signals": float("inf"),
            "ai_signals": True,
            "auto_trading": True,
            "real_time_data": True,
            "advanced_analytics": True,
            "api_access": False,
            "custom_strategies": False,
            "support": "priority",
            "team_members": 1,
        },
        SubscriptionTier.PRO: {
            "daily_signals": float("inf"),
            "ai_signals": True,
            "auto_trading": True,
            "real_time_data": True,
            "advanced_analytics": True,
            "api_access": True,
            "custom_strategies": True,
            "support": "24/7",
            "team_members": 5,
        },
        SubscriptionTier.ENTERPRISE: {
            "daily_signals": float("inf"),
            "ai_signals": True,
            "auto_trading": True,
            "real_time_data": True,
            "advanced_analytics": True,
            "api_access": True,
            "custom_strategies": True,
            "support": "dedicated",
            "team_members": 20,
        },
    }

    # Pricing (monthly in USD)
    PRICING = {
        SubscriptionTier.FREE: 0.00,
        SubscriptionTier.PREMIUM: 49.00,
        SubscriptionTier.PRO: 99.00,
        SubscriptionTier.ENTERPRISE: None,  # Contact sales
    }

    def __init__(self, db_path: str = None):
        self.db_path = db_path or _get_default_db_path()
        self._init_tables()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """Initialize subscription-related database tables"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Subscriptions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                provider VARCHAR(50),
                provider_subscription_id VARCHAR(255),
                provider_customer_id VARCHAR(255),
                plan_type VARCHAR(50) NOT NULL DEFAULT 'free',
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                billing_cycle VARCHAR(20) DEFAULT 'monthly',
                current_period_start DATETIME,
                current_period_end DATETIME,
                trial_start DATETIME,
                trial_end DATETIME,
                cancelled_at DATETIME,
                cancellation_reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """
        )

        # Payments table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subscription_id INTEGER,
                provider VARCHAR(50) NOT NULL,
                provider_payment_id VARCHAR(255),
                provider_invoice_id VARCHAR(255),
                amount DECIMAL(10,2) NOT NULL,
                currency VARCHAR(3) NOT NULL DEFAULT 'USD',
                status VARCHAR(50) NOT NULL,
                payment_method VARCHAR(50),
                payment_method_last4 VARCHAR(4),
                invoice_url VARCHAR(500),
                failure_reason TEXT,
                refunded_amount DECIMAL(10,2) DEFAULT 0.00,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
            )
        """
        )

        # Feature usage tracking
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                feature_name VARCHAR(100) NOT NULL,
                usage_count INTEGER DEFAULT 1,
                usage_date DATE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, feature_name, usage_date)
            )
        """
        )

        # Referrals table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_user_id INTEGER NOT NULL,
                referred_user_id INTEGER,
                referral_code VARCHAR(50) NOT NULL UNIQUE,
                status VARCHAR(50) DEFAULT 'pending',
                reward_amount DECIMAL(10,2) DEFAULT 0.00,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                converted_at DATETIME,
                FOREIGN KEY (referrer_user_id) REFERENCES users(id),
                FOREIGN KEY (referred_user_id) REFERENCES users(id)
            )
        """
        )

        conn.commit()
        conn.close()
        logger.info("Subscription tables initialized")

    def create_subscription(
        self,
        user_id: int,
        plan_type: str = "free",
        provider: str = None,
        provider_subscription_id: str = None,
        provider_customer_id: str = None,
        trial_days: int = 7,
    ) -> Dict:
        """Create a new subscription for a user"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now()
        trial_end = now + timedelta(days=trial_days) if trial_days > 0 and plan_type != "free" else None

        cursor.execute(
            """
            INSERT INTO subscriptions 
            (user_id, provider, provider_subscription_id, provider_customer_id, 
             plan_type, status, trial_start, trial_end, current_period_start, current_period_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan_type = excluded.plan_type,
                status = excluded.status,
                provider = excluded.provider,
                provider_subscription_id = excluded.provider_subscription_id,
                provider_customer_id = excluded.provider_customer_id,
                trial_start = excluded.trial_start,
                trial_end = excluded.trial_end,
                current_period_start = excluded.current_period_start,
                current_period_end = excluded.current_period_end,
                updated_at = CURRENT_TIMESTAMP
        """,
            (
                user_id,
                provider,
                provider_subscription_id,
                provider_customer_id,
                plan_type,
                SubscriptionStatus.TRIALING.value if trial_days > 0 else SubscriptionStatus.ACTIVE.value,
                now if trial_days > 0 else None,
                trial_end,
                now,
                now + timedelta(days=30),
            ),
        )

        conn.commit()
        conn.close()

        logger.info(f"Subscription created for user {user_id}: {plan_type}")
        return {"user_id": user_id, "plan_type": plan_type, "status": "created"}

    def get_subscription(self, user_id: int) -> Optional[Dict]:
        """Get subscription details for a user"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM subscriptions WHERE user_id = ?", (user_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def update_subscription_status(
        self, user_id: int, status: str, reason: str = None
    ) -> bool:
        """Update subscription status"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE subscriptions 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """,
            (status, user_id),
        )

        if status == SubscriptionStatus.CANCELLED.value and reason:
            cursor.execute(
                """
                UPDATE subscriptions 
                SET cancelled_at = CURRENT_TIMESTAMP, cancellation_reason = ?
                WHERE user_id = ?
            """,
                (reason, user_id),
            )

        conn.commit()
        conn.close()
        logger.info(f"Subscription status updated for user {user_id}: {status}")
        return True

    def upgrade_plan(self, user_id: int, new_plan: str) -> Dict:
        """Upgrade user to a new plan"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now()
        cursor.execute(
            """
            UPDATE subscriptions 
            SET plan_type = ?, status = ?, current_period_start = ?, 
                current_period_end = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """,
            (new_plan, SubscriptionStatus.ACTIVE.value, now, now + timedelta(days=30), user_id),
        )

        conn.commit()
        conn.close()

        logger.info(f"User {user_id} upgraded to {new_plan}")
        return {"user_id": user_id, "plan_type": new_plan, "status": "upgraded"}

    def can_access_feature(self, user_id: int, feature: str) -> bool:
        """Check if user can access a specific feature"""
        subscription = self.get_subscription(user_id)

        if not subscription:
            # No subscription record - treat as free
            tier = SubscriptionTier.FREE
        else:
            tier = SubscriptionTier(subscription["plan_type"])

        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS[SubscriptionTier.FREE])
        return limits.get(feature, False)

    def check_signal_quota(self, user_id: int) -> tuple:
        """Check if user has exceeded daily signal quota"""
        subscription = self.get_subscription(user_id)

        if not subscription:
            tier = SubscriptionTier.FREE
        else:
            tier = SubscriptionTier(subscription["plan_type"])

        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS[SubscriptionTier.FREE])
        daily_limit = limits.get("daily_signals", 5)

        if daily_limit == float("inf"):
            return True, float("inf")

        # Count signals used today
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COALESCE(SUM(usage_count), 0) 
            FROM feature_usage 
            WHERE user_id = ? AND feature_name = 'signal' AND usage_date = DATE('now')
        """,
            (user_id,),
        )

        used = cursor.fetchone()[0]
        conn.close()

        return used < daily_limit, daily_limit - used

    def record_feature_usage(self, user_id: int, feature: str):
        """Record feature usage for quota tracking"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO feature_usage (user_id, feature_name, usage_count, usage_date)
            VALUES (?, ?, 1, DATE('now'))
            ON CONFLICT(user_id, feature_name, usage_date) DO UPDATE SET
                usage_count = usage_count + 1
        """,
            (user_id, feature),
        )

        conn.commit()
        conn.close()

    def get_plan_limits(self, plan_type: str) -> Dict:
        """Get feature limits for a specific plan"""
        try:
            tier = SubscriptionTier(plan_type)
        except ValueError:
            tier = SubscriptionTier.FREE

        return self.TIER_LIMITS.get(tier, self.TIER_LIMITS[SubscriptionTier.FREE])

    def get_pricing(self) -> Dict:
        """Get pricing for all plans"""
        return {
            tier.value: {
                "monthly": price,
                "yearly": price * 12 * 0.8 if price else None,  # 20% annual discount
            }
            for tier, price in self.PRICING.items()
        }

    # INR pricing for Indian market
    PRICING_INR = {
        SubscriptionTier.FREE: 0,
        SubscriptionTier.PREMIUM: 3999,
        SubscriptionTier.PRO: 7999,
        SubscriptionTier.ENTERPRISE: None,
    }

    def get_pricing_inr(self) -> Dict:
        """Get INR pricing for all plans"""
        return {
            tier.value: {
                "monthly": price,
                "yearly": int(price * 12 * 0.8) if price else None,
            }
            for tier, price in self.PRICING_INR.items()
        }

    def record_payment(self, user_id: int, provider: str,
                       provider_payment_id: str, amount: float,
                       currency: str = 'INR', status: str = 'succeeded'):
        """Record a payment in the payments table."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO payments
            (user_id, provider, provider_payment_id, amount, currency, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, provider, provider_payment_id, amount, currency, status))
        conn.commit()
        conn.close()
        logger.info(f"Payment recorded: user={user_id} amount={amount} {currency}")

