-- Migration: Add event_id for webhook deduplication
-- Created: 2026-08-30
-- Purpose: Enable proper webhook deduplication using Razorpay event_id

-- Add event_id column to recovery_actions
ALTER TABLE recovery_actions
ADD COLUMN IF NOT EXISTS event_id TEXT;

-- Add unique index (NO time predicate - that belongs in query logic)
-- Allows NULL event_id for non-webhook actions
CREATE UNIQUE INDEX IF NOT EXISTS idx_recovery_actions_event_id_unique
ON recovery_actions (event_id)
WHERE event_id IS NOT NULL;

-- Add lookup index for time-windowed queries
CREATE INDEX IF NOT EXISTS idx_recovery_actions_event_id_lookup
ON recovery_actions (event_id, created_at DESC)
WHERE event_id IS NOT NULL;

-- Add comment
COMMENT ON COLUMN recovery_actions.event_id IS 'Razorpay webhook event_id for deduplication (evt_xxxxx format)';
