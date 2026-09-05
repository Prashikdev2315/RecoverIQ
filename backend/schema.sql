-- AI Revenue Recovery Agent - Database Schema

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    merchant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    amount INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'failed', 'pending', 'refunded')),
    failure_reason TEXT,
    payment_method VARCHAR(20) NOT NULL CHECK (payment_method IN ('card', 'upi', 'netbanking', 'wallet')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    retry_count INTEGER DEFAULT 0
);

-- Checkout sessions table
CREATE TABLE IF NOT EXISTS checkout_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL,
    cart_value INTEGER NOT NULL,
    stage_reached VARCHAR(20) NOT NULL CHECK (stage_reached IN ('cart', 'payment_page', 'otp', 'abandoned', 'completed')),
    abandoned_at TIMESTAMP,
    device VARCHAR(10) NOT NULL CHECK (device IN ('mobile', 'desktop'))
);

-- Subscriptions table
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL,
    plan_amount INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'failed_charge', 'paused', 'cancelled')),
    mandate_status VARCHAR(20) NOT NULL CHECK (mandate_status IN ('active', 'revoked', 'pending')),
    last_charge_attempt TIMESTAMP,
    consecutive_failures INTEGER DEFAULT 0
);

-- Recovery actions table
CREATE TABLE IF NOT EXISTS recovery_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    target_type VARCHAR(20) NOT NULL CHECK (target_type IN ('transaction', 'checkout_session', 'subscription')),
    target_id UUID NOT NULL,
    detected_issue TEXT,
    proposed_action TEXT,
    executed_action TEXT,
    confidence_score FLOAT,
    channel VARCHAR(20) CHECK (channel IN ('sms', 'whatsapp_sim', 'email', 'payment_link', 'none')),
    language VARCHAR(10) CHECK (language IN ('en', 'hinglish')),
    status VARCHAR(30) NOT NULL CHECK (status IN ('proposed', 'executed', 'blocked_by_guardrail', 'recovered', 'no_response')),
    reasoning_log JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_customer ON transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_checkout_sessions_stage ON checkout_sessions(stage_reached);
CREATE INDEX IF NOT EXISTS idx_checkout_sessions_customer ON checkout_sessions(customer_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_customer ON subscriptions(customer_id);
CREATE INDEX IF NOT EXISTS idx_recovery_actions_target ON recovery_actions(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_recovery_actions_status ON recovery_actions(status);
