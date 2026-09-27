-- =============================================================================
-- J.A.R.V.I.S. Long-Term Memory Schema — PostgreSQL 16
-- =============================================================================

-- Extension UUID pour clés primaires robustes
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- TABLE : conversations
-- Historique des sessions vocales avec Jarvis (résumé court)
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ,
    summary     TEXT        NOT NULL DEFAULT '',
    tags        TEXT[]      DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_conversations_started_at ON conversations (started_at DESC);

-- =============================================================================
-- TABLE : memories
-- Mémoire long-terme : faits, préférences, tâches mémorisées par Jarvis
-- La colonne qdrant_id fait le lien avec le point vectoriel dans Qdrant
-- =============================================================================
DO $$ BEGIN
    CREATE TYPE memory_category AS ENUM (
        'préférence',
        'fait',
        'tâche',
        'habitude',
        'projet',
        'contact',
        'général'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS memories (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    category        memory_category NOT NULL DEFAULT 'fait',
    content         TEXT            NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    qdrant_id       UUID,
    conversation_id UUID            REFERENCES conversations(id) ON DELETE SET NULL,
    importance      SMALLINT        NOT NULL DEFAULT 1 CHECK (importance BETWEEN 1 AND 5),
    metadata        JSONB           NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_memories_category    ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_created_at  ON memories (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_qdrant_id   ON memories (qdrant_id);

-- Trigger pour updated_at automatique
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_memories_updated_at ON memories;
CREATE TRIGGER trg_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =============================================================================
-- TABLE : tier_routing_log
-- Journalisation de l'arbitrage cognitif et de la résilience 429
-- =============================================================================
CREATE TABLE IF NOT EXISTS tier_routing_log (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    query_text          TEXT            NOT NULL,
    chosen_tier         SMALLINT        NOT NULL CHECK (chosen_tier IN (1, 2, 3)),
    reason              TEXT            NOT NULL DEFAULT '',
    final_tier          SMALLINT        NOT NULL CHECK (final_tier IN (1, 2, 3)),
    fallback_occurred   BOOLEAN         NOT NULL DEFAULT FALSE,
    latency_ms          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    override_manuel     BOOLEAN         NOT NULL DEFAULT FALSE,
    metadata            JSONB           NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tier_routing_created_at ON tier_routing_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tier_routing_chosen_tier ON tier_routing_log (chosen_tier);
CREATE INDEX IF NOT EXISTS idx_tier_routing_final_tier ON tier_routing_log (final_tier);
