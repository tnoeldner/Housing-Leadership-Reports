-- ENHANCED ENGAGEMENT DATABASE SCHEMA
-- Updated to handle complete event lifecycle from proposal to completion
-- Fall Semester: August 22 - End of December

-- Drop and recreate engagement_report_data with full form mapping
DROP TABLE IF EXISTS engagement_report_data CASCADE;

CREATE TABLE engagement_report_data (
    id BIGSERIAL PRIMARY KEY,
    
    -- Form metadata
    form_submission_id TEXT UNIQUE NOT NULL, -- Roompact form ID for uniqueness
    submission_date TIMESTAMP WITH TIME ZONE, -- When form was submitted
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Event basic information
    event_name TEXT, -- "Name of Event" field
    event_type TEXT, -- Event type/category
    event_description TEXT, -- Event description/details
    
    -- Event scheduling
    event_date DATE, -- "Date and Event Start Time" field
    event_start_time TIME,
    event_end_time TIME,
    event_duration_hours DECIMAL(4,2),
    
    -- Event approval and status
    event_approval TEXT, -- "Event Approval" field - maps to event_status
    event_status TEXT GENERATED ALWAYS AS (
        CASE 
            WHEN event_approval = 'Approved' THEN 'approved'
            WHEN event_approval = 'Cancelled' OR event_approval = 'Canceled' THEN 'cancelled'
            WHEN event_approval IS NULL OR event_approval = '' THEN 'pending'
            ELSE 'pending'
        END
    ) STORED,
    
    -- Location information
    hall TEXT, -- "Hall" field
    specific_location TEXT, -- Room/area details
    location_notes TEXT,
    
    -- Attendance information
    anticipated_attendance INTEGER DEFAULT 0, -- "Anticipated Number Attendees"
    actual_attendance INTEGER, -- Updated after event completion
    attendance_updated_date TIMESTAMP,
    
    -- Staffing and organization
    event_organizer TEXT, -- Form submitter
    co_organizers TEXT,
    staff_advisor TEXT,
    
    -- Programming details  
    programming_theme TEXT,
    target_audience TEXT,
    educational_objectives TEXT,
    
    -- Budget and resources
    estimated_budget DECIMAL(10,2),
    actual_budget DECIMAL(10,2),
    funding_source TEXT,
    resources_needed TEXT,
    
    -- Partnerships and collaboration
    collaboration_partners TEXT,
    campus_partners TEXT,
    external_partners TEXT,
    
    -- Marketing and promotion
    marketing_plan TEXT,
    promotional_materials TEXT,
    registration_required BOOLEAN DEFAULT FALSE,
    registration_deadline DATE,
    
    -- Follow-up and assessment
    assessment_method TEXT,
    follow_up_actions TEXT,
    event_feedback TEXT,
    lessons_learned TEXT,
    
    -- Form responses (complete form data as JSONB)
    form_responses JSONB,
    
    -- System fields
    semester TEXT DEFAULT 'Fall 2024', -- Fall semester tracking
    academic_year TEXT DEFAULT '2024-2025',
    generated_by_user_id UUID REFERENCES auth.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Tracking fields for analysis
    date_range_start DATE, -- Analysis period start
    date_range_end DATE,   -- Analysis period end
    
    -- Metadata for debugging
    form_debug_info JSONB -- For troubleshooting form mapping issues
);

-- Comprehensive indexing strategy
CREATE INDEX idx_engagement_form_id ON engagement_report_data(form_submission_id);
CREATE INDEX idx_engagement_event_date ON engagement_report_data(event_date);
CREATE INDEX idx_engagement_event_status ON engagement_report_data(event_status);
CREATE INDEX idx_engagement_event_approval ON engagement_report_data(event_approval);
CREATE INDEX idx_engagement_hall ON engagement_report_data(hall);
CREATE INDEX idx_engagement_organizer ON engagement_report_data(event_organizer);
CREATE INDEX idx_engagement_semester ON engagement_report_data(semester);
CREATE INDEX idx_engagement_submission_date ON engagement_report_data(submission_date);
CREATE INDEX idx_engagement_last_updated ON engagement_report_data(last_updated);

-- Composite indexes for common queries
CREATE INDEX idx_engagement_semester_status ON engagement_report_data(semester, event_status);
CREATE INDEX idx_engagement_hall_date ON engagement_report_data(hall, event_date);
CREATE INDEX idx_engagement_date_approval ON engagement_report_data(event_date, event_approval);
CREATE INDEX idx_engagement_weekly_lookup ON engagement_report_data(event_date, event_status) WHERE event_date >= CURRENT_DATE - INTERVAL '7 days';
CREATE INDEX idx_engagement_upcoming_events ON engagement_report_data(event_date, event_status) WHERE event_date >= CURRENT_DATE;

-- Fall semester date range check constraint
ALTER TABLE engagement_report_data 
ADD CONSTRAINT check_fall_semester_dates 
CHECK (event_date >= '2024-08-22' AND event_date <= '2024-12-31');

-- Event status validation
ALTER TABLE engagement_report_data 
ADD CONSTRAINT check_event_status 
CHECK (event_status IN ('pending', 'approved', 'cancelled', 'completed'));

-- Unique constraint for form submissions
ALTER TABLE engagement_report_data 
ADD CONSTRAINT unique_form_submission 
UNIQUE (form_submission_id);

-- Comments for documentation
COMMENT ON TABLE engagement_report_data IS 'Complete event lifecycle tracking from proposal to completion for Fall semester (Aug 22 - Dec 31)';
COMMENT ON COLUMN engagement_report_data.event_approval IS 'Event Approval field from form - determines event_status';
COMMENT ON COLUMN engagement_report_data.event_status IS 'Generated status: pending (null/blank), approved, cancelled, completed';
COMMENT ON COLUMN engagement_report_data.anticipated_attendance IS 'Anticipated Number Attendees from original proposal';
COMMENT ON COLUMN engagement_report_data.actual_attendance IS 'Updated after event completion with real attendance';
COMMENT ON COLUMN engagement_report_data.form_responses IS 'Complete form data as JSONB for full access to all fields';

-- Enable RLS
ALTER TABLE engagement_report_data ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Allow authenticated users to read engagement data" 
ON engagement_report_data FOR SELECT 
TO authenticated 
USING (true);

CREATE POLICY "Allow authenticated users to insert/update engagement data" 
ON engagement_report_data FOR ALL 
TO authenticated 
USING (auth.uid() = generated_by_user_id OR generated_by_user_id IS NULL)
WITH CHECK (auth.uid() = generated_by_user_id OR generated_by_user_id IS NULL);

SELECT 'Enhanced engagement database schema created successfully!' as status;