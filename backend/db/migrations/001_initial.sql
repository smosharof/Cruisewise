-- Cruisewise initial schema
-- Run with: psql $DATABASE_URL -f backend/db/migrations/001_initial.sql

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- match_intakes / match_results
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS match_intakes (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    intake_json JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Many results per intake: re-runs accumulate, letting us track agent quality over time.
CREATE TABLE IF NOT EXISTS match_results (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    intake_id   UUID NOT NULL REFERENCES match_intakes(id) ON DELETE CASCADE,
    result_json JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_match_results_intake ON match_results(intake_id);

-- ---------------------------------------------------------------------------
-- bookings
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bookings (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID REFERENCES users(id) ON DELETE SET NULL,
    sailing_id          TEXT NOT NULL,
    cruise_line         TEXT NOT NULL,
    ship_name           TEXT NOT NULL,
    departure_date      DATE NOT NULL,
    cabin_category      TEXT NOT NULL,
    cabin_number        TEXT,                          -- nullable until assigned
    price_paid_usd      INTEGER NOT NULL,
    perks_at_booking    JSONB NOT NULL DEFAULT '[]',
    booking_source      TEXT NOT NULL CHECK (booking_source IN ('match', 'external')),
    final_payment_date  DATE NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- watches
-- Note: CASCADE here means deleting a booking destroys its watch and all
-- price history. Intentional for MVP — add soft-delete before production.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS watches (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id          UUID NOT NULL UNIQUE REFERENCES bookings(id) ON DELETE CASCADE,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    watching_since      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checks_performed    INTEGER NOT NULL DEFAULT 0,
    reprice_events_count INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- price_history
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_history (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id          UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_price_usd   INTEGER NOT NULL,
    current_perks       JSONB NOT NULL DEFAULT '[]',
    source              TEXT NOT NULL CHECK (source IN ('live_api', 'mock'))
);

CREATE INDEX IF NOT EXISTS idx_price_history_booking ON price_history(booking_id, checked_at DESC);

-- ---------------------------------------------------------------------------
-- reprice_events
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reprice_events (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id           UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    detected_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recommendation_json  JSONB NOT NULL,
    user_acknowledged_at TIMESTAMPTZ          -- null until user opens/dismisses
);

CREATE INDEX IF NOT EXISTS idx_reprice_events_booking ON reprice_events(booking_id, detected_at DESC);

-- ---------------------------------------------------------------------------
-- review_chunks (pgvector)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_chunks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ship_name   TEXT NOT NULL,
    cruise_line TEXT NOT NULL,
    chunk_text  TEXT NOT NULL,
    embedding   vector(1536),               -- OpenAI text-embedding-3-small output dim
    source_url  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW index for fast approximate nearest-neighbour search (cosine distance).
-- m=16, ef_construction=64 are pgvector defaults; tune after load testing.
CREATE INDEX IF NOT EXISTS idx_review_chunks_embedding
    ON review_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_review_chunks_ship ON review_chunks(ship_name);
