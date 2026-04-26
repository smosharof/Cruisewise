-- Add currency to sailings so multi-market scraping (USD/GBP/EUR/AUD) is correctly recorded.
-- Run with: psql $DATABASE_URL -f backend/db/migrations/003_add_currency.sql

ALTER TABLE sailings ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'USD';
CREATE INDEX IF NOT EXISTS idx_sailings_currency ON sailings (currency);
