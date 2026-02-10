CREATE TABLE monthly_staff_recognition (
    id SERIAL PRIMARY KEY,
    recognition_month DATE NOT NULL,
    ascend_winner JSONB,
    north_winner JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE monthly_staff_recognition ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all to read monthly recognition"
ON monthly_staff_recognition
FOR SELECT
USING (true);

CREATE POLICY "Allow admin to insert monthly recognition"
ON monthly_staff_recognition
FOR INSERT
WITH CHECK (
    (get_my_claim('user_role'::text)) = '"admin"'::jsonb
);
