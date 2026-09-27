-- =============================================================================
-- Migration 001 : Table tool_call_metrics
-- Instrumentation systématique des appels d'outils J.A.R.V.I.S.
-- =============================================================================

CREATE TABLE IF NOT EXISTS tool_call_metrics (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    tool_name           TEXT            NOT NULL,
    status              TEXT            NOT NULL,
    latency_ms          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    cognitive_tier      SMALLINT,
    cost_est            DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    is_paid_key         BOOLEAN         NOT NULL DEFAULT FALSE,
    metadata            JSONB           NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_created_at ON tool_call_metrics (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_tool_name ON tool_call_metrics (tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_status ON tool_call_metrics (status);
CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_tier ON tool_call_metrics (cognitive_tier);
