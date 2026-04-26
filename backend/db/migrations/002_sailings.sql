-- Sailings table — populated by Apify scrapers, queried by search_sailings.
-- Run with: psql $DATABASE_URL -f backend/db/migrations/002_sailings.sql

CREATE TABLE IF NOT EXISTS sailings (
    id                  TEXT PRIMARY KEY,          -- "{cruise_line_slug}-{cruiseId}"
    cruise_line         TEXT NOT NULL,
    ship_name           TEXT NOT NULL,
    departure_port      TEXT NOT NULL,
    departure_date      DATE NOT NULL,
    return_date         DATE,
    duration_nights     INTEGER NOT NULL,
    itinerary_summary   TEXT NOT NULL,
    destination_names   JSONB NOT NULL DEFAULT '[]',
    starting_price_usd  INTEGER NOT NULL,
    booking_url         TEXT NOT NULL,
    platform            TEXT NOT NULL,
    scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- A zero or negative starting price is always a parse error, not real data.
    CONSTRAINT sailings_price_positive CHECK (starting_price_usd > 0)
);

CREATE INDEX IF NOT EXISTS idx_sailings_departure_date
    ON sailings (departure_date);
CREATE INDEX IF NOT EXISTS idx_sailings_cruise_line
    ON sailings (cruise_line);
CREATE INDEX IF NOT EXISTS idx_sailings_destination
    ON sailings USING GIN (destination_names);
