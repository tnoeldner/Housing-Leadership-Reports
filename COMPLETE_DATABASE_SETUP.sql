-- COMPLETE DATABASE SETUP FOR UND REPORTING TOOL
-- Run this entire script in Supabase SQL Editor to create all required tables
-- This combines all schemas and fixes save functionality issues

-- =============================================================================
-- PART 1: SAVED REPORTS TABLES (Duty Analysis & Staff Recognition)
-- =============================================================================

-- Table for saved weekly duty report analyses
CREATE TABLE IF NOT EXISTS saved_duty_analyses (
    id BIGSERIAL PRIMARY KEY,
    week_ending_date DATE NOT NULL,
    report_type TEXT NOT NULL, -- 'weekly_summary' or 'standard_analysis'
    date_range_start DATE NOT NULL,
    date_range_end DATE NOT NULL,
    reports_analyzed INTEGER DEFAULT 0,
    total_selected INTEGER DEFAULT 0,
    analysis_text TEXT NOT NULL,
    created_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for saved staff recognition reports  
CREATE TABLE IF NOT EXISTS saved_staff_recognition (
    id BIGSERIAL PRIMARY KEY,
    week_ending_date DATE NOT NULL,
    ascend_recognition JSONB, -- Store ASCEND recognition details
    north_recognition JSONB,  -- Store NORTH recognition details
    recognition_text TEXT,    -- Formatted recognition report
    created_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for saved reports
CREATE INDEX IF NOT EXISTS idx_saved_duty_analyses_week ON saved_duty_analyses(week_ending_date);
CREATE INDEX IF NOT EXISTS idx_saved_duty_analyses_creator ON saved_duty_analyses(created_by);
CREATE INDEX IF NOT EXISTS idx_saved_duty_analyses_created ON saved_duty_analyses(created_at);

CREATE INDEX IF NOT EXISTS idx_saved_staff_recognition_week ON saved_staff_recognition(week_ending_date);
CREATE INDEX IF NOT EXISTS idx_saved_staff_recognition_creator ON saved_staff_recognition(created_by);
CREATE INDEX IF NOT EXISTS idx_saved_staff_recognition_created ON saved_staff_recognition(created_at);

-- Unique constraints
CREATE UNIQUE INDEX IF NOT EXISTS idx_duty_analyses_unique_week_creator 
ON saved_duty_analyses(week_ending_date, created_by, report_type);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_recognition_unique_week_creator 
ON saved_staff_recognition(week_ending_date, created_by);

-- =============================================================================
-- PART 2: ENGAGEMENT ANALYSIS TABLES
-- =============================================================================

-- Table for storing quantitative engagement data from individual event submissions
CREATE TABLE IF NOT EXISTS engagement_report_data (
    id BIGSERIAL PRIMARY KEY,
    report_date DATE,
    event_title TEXT,
    event_type TEXT,
    event_date DATE,
    location_hall TEXT,
    location_details TEXT,
    staff_organizer TEXT,
    estimated_attendance INTEGER DEFAULT 0,
    event_status TEXT, -- planned, completed, cancelled
    budget_amount DECIMAL(10,2),
    collaboration_partners TEXT,
    programming_theme TEXT,
    target_audience TEXT,
    generated_by_user_id UUID REFERENCES auth.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    date_range_start DATE,
    date_range_end DATE,
    form_submission_id TEXT -- ID from Roompact for reference
);

-- Table for storing weekly engagement analyses (similar to saved_duty_analyses)
CREATE TABLE IF NOT EXISTS saved_engagement_analyses (
    id BIGSERIAL PRIMARY KEY,
    week_ending_date DATE NOT NULL,
    report_type TEXT NOT NULL DEFAULT 'weekly_summary', -- weekly_summary, standard_analysis
    date_range_start DATE NOT NULL,
    date_range_end DATE NOT NULL,
    events_analyzed INTEGER NOT NULL DEFAULT 0,
    total_selected INTEGER NOT NULL DEFAULT 0,
    analysis_text TEXT NOT NULL,
    upcoming_events TEXT, -- Special field for upcoming events list
    created_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for engagement data
CREATE INDEX IF NOT EXISTS idx_engagement_data_event_date ON engagement_report_data(event_date);
CREATE INDEX IF NOT EXISTS idx_engagement_data_report_date ON engagement_report_data(report_date);
CREATE INDEX IF NOT EXISTS idx_engagement_data_hall ON engagement_report_data(location_hall);
CREATE INDEX IF NOT EXISTS idx_engagement_data_type ON engagement_report_data(event_type);
CREATE INDEX IF NOT EXISTS idx_engagement_data_status ON engagement_report_data(event_status);
CREATE INDEX IF NOT EXISTS idx_engagement_data_user ON engagement_report_data(generated_by_user_id);
CREATE INDEX IF NOT EXISTS idx_engagement_data_created ON engagement_report_data(created_at);

-- Composite indexes for engagement data
CREATE INDEX IF NOT EXISTS idx_engagement_hall_type_date ON engagement_report_data(location_hall, event_type, event_date);
CREATE INDEX IF NOT EXISTS idx_engagement_date_status ON engagement_report_data(event_date, event_status);
CREATE INDEX IF NOT EXISTS idx_engagement_organizer_date ON engagement_report_data(staff_organizer, event_date);

-- Indexes for engagement analyses
CREATE INDEX IF NOT EXISTS idx_saved_engagement_analyses_week ON saved_engagement_analyses(week_ending_date);
CREATE INDEX IF NOT EXISTS idx_saved_engagement_analyses_creator ON saved_engagement_analyses(created_by);
CREATE INDEX IF NOT EXISTS idx_saved_engagement_analyses_created ON saved_engagement_analyses(created_at);
CREATE INDEX IF NOT EXISTS idx_saved_engagement_analyses_type ON saved_engagement_analyses(report_type);

-- Unique constraints for engagement tables
-- Drop constraint if it exists, then add it
ALTER TABLE engagement_report_data DROP CONSTRAINT IF EXISTS engagement_unique_record;
ALTER TABLE engagement_report_data ADD CONSTRAINT engagement_unique_record 
UNIQUE (form_submission_id, date_range_start, date_range_end, generated_by_user_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_engagement_analyses_unique 
ON saved_engagement_analyses(week_ending_date, created_by, report_type);

-- =============================================================================
-- PART 3: ROW LEVEL SECURITY (RLS) POLICIES
-- =============================================================================

-- Enable RLS on all tables
ALTER TABLE saved_duty_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_staff_recognition ENABLE ROW LEVEL SECURITY;
ALTER TABLE engagement_report_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_engagement_analyses ENABLE ROW LEVEL SECURITY;

-- Drop existing policies to avoid conflicts
DROP POLICY IF EXISTS "Allow authenticated users to read saved duty analyses" ON saved_duty_analyses;
DROP POLICY IF EXISTS "Allow authenticated users to insert/update their own duty analyses" ON saved_duty_analyses;
DROP POLICY IF EXISTS "Allow authenticated users to read saved staff recognition" ON saved_staff_recognition;
DROP POLICY IF EXISTS "Allow authenticated users to insert/update their own staff recognition" ON saved_staff_recognition;
DROP POLICY IF EXISTS "Allow authenticated users to read engagement data" ON engagement_report_data;
DROP POLICY IF EXISTS "Allow authenticated users to insert engagement data" ON engagement_report_data;
DROP POLICY IF EXISTS "Allow authenticated users to read engagement analyses" ON saved_engagement_analyses;
DROP POLICY IF EXISTS "Allow users to manage their own engagement analyses" ON saved_engagement_analyses;

-- Policies for saved_duty_analyses
CREATE POLICY "Allow authenticated users to read saved duty analyses" 
ON saved_duty_analyses FOR SELECT 
TO authenticated 
USING (true);

CREATE POLICY "Allow authenticated users to insert/update their own duty analyses" 
ON saved_duty_analyses FOR ALL 
TO authenticated 
USING (auth.uid() = created_by OR created_by IS NULL)
WITH CHECK (auth.uid() = created_by OR created_by IS NULL);

-- Policies for saved_staff_recognition
CREATE POLICY "Allow authenticated users to read saved staff recognition" 
ON saved_staff_recognition FOR SELECT 
TO authenticated 
USING (true);

CREATE POLICY "Allow authenticated users to insert/update their own staff recognition" 
ON saved_staff_recognition FOR ALL 
TO authenticated 
USING (auth.uid() = created_by OR created_by IS NULL)
WITH CHECK (auth.uid() = created_by OR created_by IS NULL);

-- Policies for engagement_report_data
CREATE POLICY "Allow authenticated users to read engagement data" 
ON engagement_report_data FOR SELECT 
TO authenticated 
USING (true);

CREATE POLICY "Allow authenticated users to insert engagement data" 
ON engagement_report_data FOR INSERT 
TO authenticated 
WITH CHECK (auth.uid() = generated_by_user_id OR generated_by_user_id IS NULL);

-- Policies for saved_engagement_analyses
CREATE POLICY "Allow authenticated users to read engagement analyses" 
ON saved_engagement_analyses FOR SELECT 
TO authenticated 
USING (true);

CREATE POLICY "Allow users to manage their own engagement analyses" 
ON saved_engagement_analyses FOR ALL 
TO authenticated 
USING (auth.uid() = created_by OR created_by IS NULL)
WITH CHECK (auth.uid() = created_by OR created_by IS NULL);

-- =============================================================================
-- PART 4: DOCUMENTATION COMMENTS
-- =============================================================================

COMMENT ON TABLE saved_duty_analyses IS 'Stores saved weekly duty report analyses for historical access and reporting';
COMMENT ON TABLE saved_staff_recognition IS 'Stores saved weekly staff recognition reports';
COMMENT ON TABLE engagement_report_data IS 'Stores quantitative data extracted from Residence Life Event Submission forms for historical analysis and trending';
COMMENT ON TABLE saved_engagement_analyses IS 'Stores completed engagement analysis reports for future reference and integration into weekly summaries';

-- Success message
SELECT 'Database setup complete! All tables, indexes, and policies created successfully.' as setup_status;