# 🚀 KishanX Trading Signals — Subscription & AI Monetization Roadmap

> **Goal**: Transform the existing KishanX Trading Signals platform into a **monthly subscription-based AI trading app** that generates recurring revenue.

---

## 📋 Executive Summary

The current KishanX Trading Signals app has a **solid trading foundation** but lacks the monetization infrastructure required for a subscription business. This roadmap details exactly what needs to be built, in priority order, to create a revenue-generating platform.

**Current State**: Trading engine ✅ | Subscription layer ❌ | AI/ML ❌ | Payments ❌  
**Target State**: Fully monetized SaaS with AI-powered signals and automated billing.

---

## 🗂️ Table of Contents

1. [Current App Capabilities](#1-current-app-capabilities)
2. [Missing Components for Subscription Business](#2-missing-components-for-subscription-business)
3. [Phase 1: Payment & Subscription Infrastructure](#3-phase-1-payment--subscription-infrastructure)
4. [Phase 2: AI/ML Trading Engine](#4-phase-2-aiml-trading-engine)
5. [Phase 3: Feature Gating & Tiered Access](#5-phase-3-feature-gating--tiered-access)
6. [Phase 4: Advanced Monetization Features](#6-phase-4-advanced-monetization-features)
7. [Database Schema Changes](#7-database-schema-changes)
8. [API Endpoints Required](#8-api-endpoints-required)
9. [Technology Stack Recommendations](#9-technology-stack-recommendations)
10. [Implementation Timeline](#10-implementation-timeline)
11. [Revenue Projections](#11-revenue-projections)

---

## 1. Current App Capabilities

### ✅ What Already Works

| Module | Status | Description |
|--------|--------|-------------|
| **Trading Engine** | ✅ Production-ready | RSI, MACD, Bollinger Bands, Moving Average strategies |
| **Auto-Trading** | ✅ Active | Market-hours-aware bot with trailing stops, position management |
| **Risk Management** | ✅ Active | Position sizing, stop loss/take profit, drawdown controls |
| **User Auth** | ✅ Secure | PBKDF2 hashing, sessions, role-based access (admin/user) |
| **Database** | ✅ SQLite | users, trades, positions, portfolio_history, signals tables |
| **Admin Panel** | ✅ Full-featured | System monitoring, trading control, user management |
| **Real-time Data** | ✅ Multi-source | Angel One API (India), Yahoo Finance (global) |
| **Portfolio Analytics** | ✅ Comprehensive | P&L, win rate, Sharpe ratio, drawdown analysis |
| **Subscription UI** | 🟡 Mock only | `subscription.html` has visual plans but **no payment logic** |
| **Premium Flag** | 🟡 Exists unused | `is_premium` column in DB — not enforced anywhere |

### ❌ Critical Gaps

| Gap | Impact |
|-----|--------|
| No payment gateway | Cannot collect money |
| No subscription lifecycle | No trials, renewals, cancellations |
| No AI/ML | Rule-based strategies only — not "AI" |
| No feature gating | Premium users get same features as free |
| No webhook handling | Cannot confirm payments or handle failures |

---

## 2. Missing Components for Subscription Business

### 2.1 Payment Infrastructure
- [ ] Payment gateway integration (Stripe / Razorpay)
- [ ] Subscription plan creation and management
- [ ] Checkout flow (hosted or embedded)
- [ ] Webhook handlers for payment events
- [ ] Invoice and receipt generation
- [ ] Failed payment retry logic
- [ ] Refund processing

### 2.2 Subscription Lifecycle Management
- [ ] Trial period automation (e.g., 7-day free trial)
- [ ] Plan upgrade/downgrade logic
- [ ] Prorated billing calculations
- [ ] Cancellation and grace period handling
- [ ] Subscription status tracking (active, past_due, cancelled)

### 2.3 AI/ML Trading Engine
- [ ] Historical data pipeline for model training
- [ ] Feature engineering (technical indicators + market data)
- [ ] Model training pipeline (LSTM, XGBoost, or Transformer-based)
- [ ] Model deployment and inference API
- [ ] A/B testing framework for strategy performance
- [ ] Model retraining schedule

### 2.4 Feature Gating & Access Control
- [ ] Middleware to check subscription tier on API routes
- [ ] Frontend conditional rendering based on plan
- [ ] Signal limit enforcement (e.g., 5 signals/day for free)
- [ ] Auto-trading enablement per tier
- [ ] Advanced analytics access control

### 2.5 User Experience
- [ ] Upgrade prompts and CTAs
- [ ] Plan comparison page with feature matrix
- [ ] Billing dashboard (view invoices, update payment method)
- [ ] Cancellation flow with retention offers

---

## 3. Phase 1: Payment & Subscription Infrastructure

### 3.1 Choose Payment Provider

| Provider | Best For | Pricing | Integration |
|----------|----------|---------|-------------|
| **Stripe** | Global users, USD | 2.9% + 30¢ per transaction | Excellent Python SDK |
| **Razorpay** | Indian users, INR | 2% per transaction | Strong Indian support |
| **PayPal** | Older demographics | 2.9% + fixed fee | Well-known brand |

**Recommendation**: Use **Stripe** for global reach + **Razorpay** for Indian market. Start with one.

### 3.2 Database Schema Updates

```sql
-- subscriptions table
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    stripe_subscription_id VARCHAR(255),
    stripe_customer_id VARCHAR(255),
    plan_type VARCHAR(50) NOT NULL, -- 'free', 'premium', 'pro'
    status VARCHAR(50) NOT NULL, -- 'active', 'trialing', 'past_due', 'cancelled'
    current_period_start DATETIME,
    current_period_end DATETIME,
    trial_start DATETIME,
    trial_end DATETIME,
    cancelled_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- payments table
CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subscription_id INTEGER,
    stripe_payment_intent_id VARCHAR(255),
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(50) NOT NULL, -- 'succeeded', 'failed', 'pending'
    payment_method VARCHAR(50),
    invoice_url VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);

-- Add to users table
ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255);
ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(50) DEFAULT 'free';
```

### 3.3 Stripe Integration Code

```python
# payments/stripe_client.py
import stripe
from flask import current_app

class StripeClient:
    def __init__(self):
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        self.webhook_secret = current_app.config['STRIPE_WEBHOOK_SECRET']
    
    def create_customer(self, email, name):
        """Create a Stripe customer"""
        return stripe.Customer.create(email=email, name=name)
    
    def create_subscription(self, customer_id, price_id, trial_days=7):
        """Create a subscription with trial period"""
        return stripe.Subscription.create(
            customer=customer_id,
            items=[{'price': price_id}],
            trial_period_days=trial_days,
            payment_behavior='default_incomplete',
            expand=['latest_invoice.payment_intent']
        )
    
    def handle_webhook(self, payload, sig_header):
        """Handle Stripe webhooks"""
        return stripe.Webhook.construct_event(
            payload, sig_header, self.webhook_secret
        )
```

### 3.4 Flask Routes for Payments

```python
# routes/payments.py
from flask import Blueprint, request, jsonify, session
from functools import wraps

payments_bp = Blueprint('payments', __name__)

@payments_bp.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """Create Stripe Checkout session for subscription"""
    # Implementation
    pass

@payments_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks"""
    # Implementation
    pass

@payments_bp.route('/portal', methods=['GET'])
def customer_portal():
    """Redirect to Stripe Customer Portal"""
    # Implementation
    pass
```

### 3.5 Webhook Events to Handle

| Event | Action Required |
|-------|-----------------|
| `checkout.session.completed` | Activate subscription, grant access |
| `invoice.payment_succeeded` | Record payment, extend access |
| `invoice.payment_failed` | Notify user, mark past_due |
| `customer.subscription.deleted` | Cancel subscription, downgrade to free |
| `customer.subscription.updated` | Update plan details in DB |

---

## 4. Phase 2: AI/ML Trading Engine

### 4.1 Why Current System Isn't "AI"

The current `trading_system.py` uses **rule-based strategies**:
- RSI > 70 → SELL
- MACD crossover → BUY
- Bollinger Band touch → Signal

These are **technical indicators**, not AI. True AI trading requires machine learning models that learn from data.

### 4.2 AI Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Data Pipeline  │────▶│  Feature Store   │────▶│  Model Training │
│                 │     │                  │     │                 │
│ - Historical    │     │ - Technical      │     │ - LSTM/XGBoost  │
│   prices        │     │   indicators     │     │ - Backtesting   │
│ - Market data   │     │ - Sentiment      │     │ - Validation    │
│ - News/sentiment│     │ - Price patterns │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Trade Execution│◀────│  Signal API      │◀────│  Model Serving  │
│                 │     │                  │     │                 │
│ - Auto-trader   │     │ - REST endpoint  │     │ - Real-time     │
│ - Risk manager  │     │ - WebSocket      │     │   inference     │
│ - Position mgmt │     │ - Confidence     │     │ - A/B testing   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### 4.3 Model Options

| Model | Pros | Cons | Use Case |
|-------|------|------|----------|
| **LSTM** | Good for time series, captures temporal patterns | Requires lots of data, slow training | Price prediction, trend forecasting |
| **XGBoost** | Fast, interpretable, handles tabular well | Doesn't capture temporal dependencies | Feature-based signal classification |
| **Transformer** | State-of-the-art for sequences | Very data hungry, expensive | Multi-asset correlation analysis |
| **Reinforcement Learning** | Learns optimal trading policy | Complex, hard to train | Direct strategy optimization |

**Recommendation**: Start with **XGBoost** for signal classification, then add **LSTM** for price prediction.

### 4.4 Sample AI Model Code

```python
# ai_models/signal_predictor.py
import xgboost as xgb
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

class AISignalPredictor:
    def __init__(self):
        self.model = None
        self.feature_columns = [
            'rsi', 'macd', 'macd_signal', 'bb_position',
            'sma_20_cross', 'volume_ratio', 'price_momentum',
            'volatility', 'atr_ratio'
        ]
    
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Engineer features from raw market data"""
        features = pd.DataFrame()
        
        # Technical indicators (already calculated)
        features['rsi'] = df['rsi']
        features['macd'] = df['macd']
        features['macd_signal'] = df['macd_signal']
        
        # Custom features
        features['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        features['sma_20_cross'] = (df['close'] > df['sma_20']).astype(int)
        features['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        features['price_momentum'] = df['close'].pct_change(5)
        features['volatility'] = df['close'].pct_change().rolling(20).std()
        features['atr_ratio'] = df['atr'] / df['close']
        
        return features
    
    def train(self, X: pd.DataFrame, y: pd.Series):
        """Train the XGBoost model"""
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False  # Time series — no shuffle
        )
        
        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            objective='multi:softprob',
            num_class=3  # BUY, SELL, HOLD
        )
        
        self.model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test)
        print(classification_report(y_test, y_pred))
    
    def predict(self, features: pd.DataFrame) -> dict:
        """Generate trading signal with confidence"""
        if self.model is None:
            raise ValueError("Model not trained")
        
        prediction = self.model.predict_proba(features)
        
        classes = ['SELL', 'HOLD', 'BUY']
        signal = classes[np.argmax(prediction)]
        confidence = np.max(prediction)
        
        return {
            'signal': signal,
            'confidence': float(confidence),
            'probabilities': {
                cls: float(prob) for cls, prob in zip(classes, prediction[0])
            }
        }
```

### 4.5 Model Training Pipeline

```python
# ai_models/training_pipeline.py
class ModelTrainingPipeline:
    def __init__(self):
        self.predictor = AISignalPredictor()
    
    def fetch_training_data(self, symbols, start_date, end_date):
        """Fetch historical data for training"""
        # Use existing data providers
        pass
    
    def create_labels(self, df, forward_window=5, profit_threshold=0.02):
        """Create labels: BUY if price goes up >2% in next 5 days, SELL if down"""
        future_return = df['close'].shift(-forward_window) / df['close'] - 1
        
        labels = pd.Series('HOLD', index=df.index)
        labels[future_return > profit_threshold] = 'BUY'
        labels[future_return < -profit_threshold] = 'SELL'
        
        return labels
    
    def run_pipeline(self):
        """Full training pipeline"""
        # 1. Fetch data
        # 2. Engineer features
        # 3. Create labels
        # 4. Train model
        # 5. Save model
        # 6. Deploy to production
        pass
```

---

## 5. Phase 3: Feature Gating & Tiered Access

### 5.1 Subscription Tiers

| Feature | Free | Premium ($49/mo) | Pro ($99/mo) |
|---------|------|------------------|--------------|
| Basic signals | 5/day | Unlimited | Unlimited |
| AI-powered signals | ❌ | ✅ | ✅ |
| Auto-trading | ❌ | 1 strategy | Multiple strategies |
| Real-time data | Delayed 15min | Real-time | Real-time |
| Risk management | Basic | Advanced | Custom |
| Portfolio analytics | Basic | Advanced | Full + API |
| Support | Email | Priority | 24/7 + Dedicated |
| API access | ❌ | ❌ | ✅ |
| Custom strategies | ❌ | ❌ | ✅ |
| Team members | 1 | 1 | Up to 5 |

### 5.2 Decorator for Feature Gating

```python
# auth/decorators.py
from functools import wraps
from flask import session, jsonify

require_subscription = ['premium', 'pro']

def require_plan(min_plan='premium'):
    """Decorator to restrict access based on subscription tier"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Authentication required'}), 401
            
            user = get_user_by_id(session['user_id'])
            
            tier_levels = {
                'free': 0,
                'premium': 1,
                'pro': 2
            }
            
            if tier_levels.get(user.subscription_tier, 0) < tier_levels.get(min_plan, 0):
                return jsonify({
                    'error': 'Subscription required',
                    'required_plan': min_plan,
                    'current_plan': user.subscription_tier,
                    'upgrade_url': '/subscription'
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Usage in routes
@app.route('/api/ai-signals')
@require_plan('premium')
def get_ai_signals():
    """AI-powered signals — Premium only"""
    pass

@app.route('/api/auto-trade')
@require_plan('premium')
def start_auto_trading():
    """Auto-trading — Premium only"""
    pass
```

### 5.3 Signal Quota Enforcement

```python
# middleware/quota.py
class SignalQuota:
    def __init__(self, db):
        self.db = db
    
    def check_quota(self, user_id: int) -> bool:
        """Check if user has exceeded daily signal quota"""
        user = self.db.get_user(user_id)
        
        quotas = {
            'free': 5,
            'premium': float('inf'),
            'pro': float('inf')
        }
        
        daily_limit = quotas.get(user.subscription_tier, 5)
        signals_today = self.db.count_signals_today(user_id)
        
        return signals_today < daily_limit
    
    def enforce_quota(self, user_id: int):
        """Decorator/ middleware to enforce quota"""
        if not self.check_quota(user_id):
            raise QuotaExceededError(
                "Daily signal limit reached. Upgrade to Premium for unlimited signals."
            )
```

---

## 6. Phase 4: Advanced Monetization Features

### 6.1 Referral Program

```python
# referrals/referral_system.py
class ReferralSystem:
    def __init__(self):
        self.referral_reward = 10.00  # $10 credit per referral
    
    def generate_referral_code(self, user_id):
        """Generate unique referral code"""
        return f"REF{user_id}{uuid4().hex[:6].upper()}"
    
    def apply_referral(self, code, new_user_id):
        """Apply referral code and give credit"""
        referrer = self.get_referrer_by_code(code)
        if referrer:
            self.add_account_credit(referrer.id, self.referral_reward)
            self.mark_referral_success(code, new_user_id)
```

### 6.2 Affiliate Program

| Tier | Monthly Sales | Commission |
|------|--------------|------------|
| Bronze | $0 - $1,000 | 20% |
| Silver | $1,000 - $5,000 | 25% |
| Gold | $5,000+ | 30% |

### 6.3 Enterprise Plan

- White-label solution for brokerages
- Custom AI model training
- Dedicated infrastructure
- SLA guarantees
- **Price**: $2,000+/month

---

## 7. Database Schema Changes

### Full Schema for Subscription Business

```sql
-- Existing tables (keep as-is)
-- users, trades, positions, portfolio_history, signals, market_data

-- NEW: Subscription management
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    provider VARCHAR(50) NOT NULL, -- 'stripe', 'razorpay'
    provider_subscription_id VARCHAR(255),
    provider_customer_id VARCHAR(255),
    plan_type VARCHAR(50) NOT NULL, -- 'free', 'premium', 'pro', 'enterprise'
    status VARCHAR(50) NOT NULL, -- 'active', 'trialing', 'past_due', 'cancelled', 'unpaid'
    billing_cycle VARCHAR(20) DEFAULT 'monthly', -- 'monthly', 'yearly'
    current_period_start DATETIME,
    current_period_end DATETIME,
    trial_start DATETIME,
    trial_end DATETIME,
    cancelled_at DATETIME,
    cancellation_reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- NEW: Payment records
CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subscription_id INTEGER,
    provider VARCHAR(50) NOT NULL,
    provider_payment_id VARCHAR(255),
    provider_invoice_id VARCHAR(255),
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status VARCHAR(50) NOT NULL, -- 'succeeded', 'failed', 'pending', 'refunded'
    payment_method VARCHAR(50),
    payment_method_last4 VARCHAR(4),
    invoice_url VARCHAR(500),
    failure_reason TEXT,
    refunded_amount DECIMAL(10,2) DEFAULT 0.00,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);

-- NEW: Feature usage tracking
CREATE TABLE feature_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    feature_name VARCHAR(100) NOT NULL,
    usage_count INTEGER DEFAULT 1,
    usage_date DATE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, feature_name, usage_date)
);

-- NEW: Referrals
CREATE TABLE referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_user_id INTEGER NOT NULL,
    referred_user_id INTEGER,
    referral_code VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'converted', 'rewarded'
    reward_amount DECIMAL(10,2) DEFAULT 0.00,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    converted_at DATETIME,
    FOREIGN KEY (referrer_user_id) REFERENCES users(id),
    FOREIGN KEY (referred_user_id) REFERENCES users(id)
);

-- NEW: AI model performance
CREATE TABLE ai_model_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    signal_type VARCHAR(10) NOT NULL, -- 'BUY', 'SELL', 'HOLD'
    predicted_confidence DECIMAL(5,2),
    actual_return DECIMAL(10,4),
    was_correct BOOLEAN,
    signal_date DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Update users table
ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(50) DEFAULT 'free';
ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255);
ALTER TABLE users ADD COLUMN razorpay_customer_id VARCHAR(255);
ALTER TABLE users ADD COLUMN referral_code VARCHAR(50);
ALTER TABLE users ADD COLUMN account_credit DECIMAL(10,2) DEFAULT 0.00;
```

---

## 8. API Endpoints Required

### 8.1 Subscription Management

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/subscriptions/create` | Create new subscription | ✅ |
| GET | `/api/subscriptions/current` | Get current subscription | ✅ |
| POST | `/api/subscriptions/cancel` | Cancel subscription | ✅ |
| POST | `/api/subscriptions/upgrade` | Upgrade plan | ✅ |
| POST | `/api/subscriptions/downgrade` | Downgrade plan | ✅ |
| GET | `/api/subscriptions/invoices` | List payment history | ✅ |
| GET | `/api/subscriptions/usage` | Feature usage stats | ✅ |

### 8.2 AI Signals

| Method | Endpoint | Description | Plan Required |
|--------|----------|-------------|---------------|
| GET | `/api/ai-signals` | Get AI-powered trading signals | Premium+ |
| GET | `/api/ai-signals/<symbol>` | Get signal for specific symbol | Premium+ |
| GET | `/api/ai-performance` | AI model performance metrics | Premium+ |
| POST | `/api/ai-feedback` | Provide feedback on signals | Premium+ |

### 8.3 Webhooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/webhooks/stripe` | Stripe event webhooks |
| POST | `/webhooks/razorpay` | Razorpay event webhooks |

---

## 9. Technology Stack Recommendations

### 9.1 Payment Processing

| Component | Technology | Reason |
|-----------|-----------|--------|
| Payment Gateway | **Stripe** + **Razorpay** | Best coverage for global + Indian markets |
| Webhook Handling | Flask routes + Redis queue | Async processing for reliability |
| Invoice Generation | **Stripe Invoicing** + PDF generation | Built-in + custom branding |

### 9.2 AI/ML Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Model Training | **XGBoost** + **PyTorch/LSTM** | Proven for financial time series |
| Feature Store | **Feast** or custom SQLite | Manage features across environments |
| Model Serving | **Flask API** + **Redis caching** | Low-latency inference |
| Experiment Tracking | **MLflow** | Track model versions and performance |
| Data Pipeline | **Apache Airflow** or **Cron** | Schedule data fetching and retraining |

### 9.3 Infrastructure

| Component | Technology | Reason |
|-----------|-----------|--------|
| Database | **PostgreSQL** (migrate from SQLite) | Production-grade, concurrent access |
| Cache | **Redis** | Session storage, rate limiting, model cache |
| Queue | **Celery + Redis** | Background jobs, webhook processing |
| Monitoring | **Prometheus + Grafana** | System and business metrics |
| Logging | **ELK Stack** or **Sentry** | Centralized logging and error tracking |

---

## 10. Implementation Timeline

### Week 1-2: Foundation
- [ ] Set up Stripe/Razorpay accounts
- [ ] Create subscription database schema
- [ ] Implement basic checkout flow
- [ ] Add webhook handlers

### Week 3-4: Subscription Lifecycle
- [ ] Trial period automation
- [ ] Plan upgrade/downgrade logic
- [ ] Invoice and receipt generation
- [ ] Cancellation flow

### Week 5-6: AI/ML Foundation
- [ ] Build data pipeline for historical data
- [ ] Engineer features
- [ ] Train first XGBoost model
- [ ] Create model serving API

### Week 7-8: Feature Gating
- [ ] Implement subscription decorators
- [ ] Add quota enforcement
- [ ] Build plan comparison page
- [ ] Add upgrade prompts

### Week 9-10: Polish & Launch
- [ ] A/B test pricing
- [ ] Add referral program
- [ ] Performance optimization
- [ ] Launch to beta users

---

## 11. Revenue Projections

### Assumptions

| Metric | Value |
|--------|-------|
| Monthly visitors | 10,000 |
| Free-to-paid conversion | 3% |
| Premium plan split | 70% Premium, 30% Pro |
| Monthly churn rate | 5% |
| Annual plan discount | 20% |

### Projected Monthly Revenue

| Month | Free Users | Premium ($49) | Pro ($99) | Monthly Revenue |
|-------|-----------|---------------|-----------|-----------------|
| 1 | 9,700 | 210 | 90 | $19,290 |
| 3 | 9,400 | 420 | 180 | $38,580 |
| 6 | 9,100 | 630 | 270 | $57,870 |
| 12 | 8,800 | 840 | 360 | $77,160 |

**Year 1 Target**: $500,000 ARR (Annual Recurring Revenue)

---

## 📎 Appendix

### A. Security Considerations
- Encrypt all payment data at rest
- Use HTTPS for all payment flows
- Implement idempotency keys for payment operations
- PCI DSS compliance for card data (use Stripe Elements to avoid handling card data)
- Rate limit payment endpoints
- Log all payment events for audit

### B. Legal Considerations
- Terms of Service with subscription terms
- Privacy Policy (GDPR/CCPA compliant)
- Refund policy
- Securities disclaimers (trading involves risk)
- Subscription cancellation rights

### C. Marketing Launch Checklist
- [ ] Landing page with pricing
- [ ] Demo video of AI signals
- [ ] Case studies / testimonials
- [ ] Email drip campaign for free users
- [ ] Social proof (user count, performance stats)
- [ ] Limited-time launch discount

---

**Document Version**: 1.0  
**Last Updated**: 2026-05-06  
**Author**: AI Analysis for KishanX Trading Signals
