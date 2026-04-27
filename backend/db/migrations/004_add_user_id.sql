-- Drop existing FK constraints on user_id columns
ALTER TABLE match_intakes DROP CONSTRAINT IF EXISTS match_intakes_user_id_fkey;
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_user_id_fkey;

-- Change user_id columns from UUID to TEXT to support Firebase UIDs
ALTER TABLE match_intakes ALTER COLUMN user_id TYPE TEXT USING user_id::text;
ALTER TABLE match_intakes ALTER COLUMN user_id SET DEFAULT 'demo-user';

ALTER TABLE bookings ALTER COLUMN user_id TYPE TEXT USING user_id::text;
ALTER TABLE bookings ALTER COLUMN user_id SET DEFAULT 'demo-user';

-- Add indexes for per-user queries
CREATE INDEX IF NOT EXISTS idx_match_intakes_user_id ON match_intakes (user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings (user_id);
