-- Supabase table for storing historical duty report incidents
-- This table enables historical analysis, trending, and graphing by hall, incident type, and date

CREATE TABLE IF NOT EXISTS duty_report_incidents (
    id BIGSERIAL PRIMARY KEY,
    report_date DATE,
    hall_name TEXT NOT NULL,
    staff_author TEXT,
    form_type TEXT,
    incident_type TEXT NOT NULL,
    incident_count INTEGER DEFAULT 1,
    generated_by_user_id UUID REFERENCES auth.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    date_range_start DATE,
    date_range_end DATE
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_duty_report_incidents_date ON duty_report_incidents(report_date);
CREATE INDEX IF NOT EXISTS idx_duty_report_incidents_hall ON duty_report_incidents(hall_name);
CREATE INDEX IF NOT EXISTS idx_duty_report_incidents_type ON duty_report_incidents(incident_type);
CREATE INDEX IF NOT EXISTS idx_duty_report_incidents_user ON duty_report_incidents(generated_by_user_id);
CREATE INDEX IF NOT EXISTS idx_duty_report_incidents_created ON duty_report_incidents(created_at);

-- Create composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_duty_incidents_hall_type_date ON duty_report_incidents(hall_name, incident_type, report_date);
CREATE INDEX IF NOT EXISTS idx_duty_incidents_date_type ON duty_report_incidents(report_date, incident_type);

-- Create unique constraint to prevent duplicate records (same report date, hall, staff, form type, incident type)
-- This prevents the same incident from being recorded multiple times in the same analysis run
CREATE UNIQUE INDEX IF NOT EXISTS idx_duty_incidents_unique_record 
ON duty_report_incidents(report_date, hall_name, staff_author, form_type, incident_type, date_range_start, date_range_end) 
WHERE report_date IS NOT NULL;

-- RLS (Row Level Security) policies
ALTER TABLE duty_report_incidents ENABLE ROW LEVEL SECURITY;

-- Policy to allow authenticated users to read all records (for analysis)
CREATE POLICY "Allow authenticated users to read duty incidents" 
ON duty_report_incidents FOR SELECT 
TO authenticated 
USING (true);

-- Policy to allow authenticated users to insert their own records
CREATE POLICY "Allow authenticated users to insert duty incidents" 
ON duty_report_incidents FOR INSERT 
TO authenticated 
WITH CHECK (auth.uid() = generated_by_user_id OR generated_by_user_id IS NULL);

-- Comments for documentation
COMMENT ON TABLE duty_report_incidents IS 'Stores individual incident records from duty reports for historical analysis and graphing';
COMMENT ON COLUMN duty_report_incidents.report_date IS 'The date when the duty report was filed';
COMMENT ON COLUMN duty_report_incidents.hall_name IS 'Name of the residence hall or building';
COMMENT ON COLUMN duty_report_incidents.staff_author IS 'Staff member who filed the duty report';
COMMENT ON COLUMN duty_report_incidents.form_type IS 'Type of duty report form (RA, CA, RD, RM)';
COMMENT ON COLUMN duty_report_incidents.incident_type IS 'Category: lockout, maintenance, policy_violation, safety_concern, general_activity';
COMMENT ON COLUMN duty_report_incidents.incident_count IS 'Number of incidents of this type (usually 1)';
COMMENT ON COLUMN duty_report_incidents.generated_by_user_id IS 'User who generated/stored this data from the reporting tool';
COMMENT ON COLUMN duty_report_incidents.date_range_start IS 'Start date of the analysis range that generated this record';
COMMENT ON COLUMN duty_report_incidents.date_range_end IS 'End date of the analysis range that generated this record';

-- Example queries for common use cases:

-- 1. Get incident counts by hall for a date range
-- SELECT hall_name, incident_type, SUM(incident_count) as total_incidents
-- FROM duty_report_incidents 
-- WHERE report_date BETWEEN '2025-01-01' AND '2025-01-31'
-- GROUP BY hall_name, incident_type
-- ORDER BY hall_name, total_incidents DESC;

-- 2. Get trending data for a specific hall
-- SELECT DATE_TRUNC('week', report_date) as week, incident_type, SUM(incident_count) as incidents
-- FROM duty_report_incidents 
-- WHERE hall_name = 'Residence Hall Name'
-- AND report_date >= CURRENT_DATE - INTERVAL '3 months'
-- GROUP BY week, incident_type
-- ORDER BY week, incidents DESC;

-- 3. Get comparative data across all halls
-- SELECT hall_name, 
--        SUM(CASE WHEN incident_type = 'lockout' THEN incident_count ELSE 0 END) as lockouts,
--        SUM(CASE WHEN incident_type = 'maintenance' THEN incident_count ELSE 0 END) as maintenance,
--        SUM(CASE WHEN incident_type = 'policy_violation' THEN incident_count ELSE 0 END) as violations,
--        SUM(CASE WHEN incident_type = 'safety_concern' THEN incident_count ELSE 0 END) as safety
-- FROM duty_report_incidents 
-- WHERE report_date >= CURRENT_DATE - INTERVAL '1 month'
-- GROUP BY hall_name
-- ORDER BY (lockouts + maintenance + violations + safety) DESC;