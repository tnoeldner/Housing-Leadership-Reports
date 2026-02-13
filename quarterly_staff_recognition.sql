-- Quarterly Staff Recognition Table
-- Fiscal Year runs July 1 through June 30
-- Q1: July, August, September
-- Q2: October, November, December
-- Q3: January, February, March
-- Q4: April, May, June

CREATE TABLE IF NOT EXISTS quarterly_staff_recognition (
    id BIGSERIAL PRIMARY KEY,
    fiscal_year INT NOT NULL,
    quarter INT NOT NULL CHECK (quarter >= 1 AND quarter <= 4),
    ascend_winner JSONB,
    north_winner JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(fiscal_year, quarter)
);

ALTER TABLE quarterly_staff_recognition ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all to view quarterly recognition"
ON quarterly_staff_recognition
FOR SELECT
USING (true);

CREATE POLICY "Allow service role to manage quarterly recognition"
ON quarterly_staff_recognition
FOR ALL
USING (true)
WITH CHECK (true);
