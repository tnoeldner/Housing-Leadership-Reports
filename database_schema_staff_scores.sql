-- Database schema for storing individual staff performance scores
-- This table tracks detailed scores for each staff member across ASCEND and NORTH categories

-- Step 1: Create the table
CREATE TABLE IF NOT EXISTS staff_recognition_scores (
    id BIGSERIAL PRIMARY KEY,
    week_ending_date DATE NOT NULL,
    staff_member_name TEXT NOT NULL,
    staff_member_id UUID,
    category_type TEXT NOT NULL,
    category_name TEXT NOT NULL,
    score INTEGER CHECK (score >= 1 AND score <= 4),
    reasoning TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID
);

-- Step 2: Create indexes
CREATE INDEX IF NOT EXISTS idx_staff_scores_week ON staff_recognition_scores(week_ending_date);
CREATE INDEX IF NOT EXISTS idx_staff_scores_member ON staff_recognition_scores(staff_member_id);
CREATE INDEX IF NOT EXISTS idx_staff_scores_category ON staff_recognition_scores(category_type, category_name);
CREATE INDEX IF NOT EXISTS idx_staff_scores_created ON staff_recognition_scores(created_at);
CREATE INDEX IF NOT EXISTS idx_staff_scores_member_week ON staff_recognition_scores(staff_member_id, week_ending_date);

-- Step 3: Enable RLS
ALTER TABLE staff_recognition_scores ENABLE ROW LEVEL SECURITY;

-- Step 4: Create RLS policies
CREATE POLICY "Allow authenticated users to read staff scores" 
ON staff_recognition_scores FOR SELECT 
TO authenticated 
USING (true);

CREATE POLICY "Allow authenticated users to insert staff scores" 
ON staff_recognition_scores FOR INSERT 
TO authenticated 
WITH CHECK (auth.uid() = created_by OR created_by IS NULL);

CREATE POLICY "Admins can manage all staff scores" 
ON staff_recognition_scores FOR ALL 
TO authenticated 
USING (
    EXISTS (
        SELECT 1 FROM profiles 
        WHERE profiles.id = auth.uid() 
        AND profiles.role IN ('admin', 'director')
    )
);

CREATE POLICY "Supervisors can view team scores" 
ON staff_recognition_scores FOR SELECT 
TO authenticated 
USING (
    EXISTS (
        SELECT 1 FROM profiles 
        WHERE profiles.supervisor_id = auth.uid() 
        AND profiles.id = staff_recognition_scores.staff_member_id
    )
);

CREATE POLICY "Staff can view own scores" 
ON staff_recognition_scores FOR SELECT 
TO authenticated 
USING (auth.uid() = staff_recognition_scores.staff_member_id);
