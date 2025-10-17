-- Update existing engagement_report_data table to use new field name
-- Run this if you've already created the table with the old name

-- Rename the column from attendance_count to estimated_attendance
ALTER TABLE engagement_report_data 
RENAME COLUMN attendance_count TO estimated_attendance;

-- Update any existing indexes that reference the old column name
DROP INDEX IF EXISTS idx_engagement_attendance;
CREATE INDEX IF NOT EXISTS idx_engagement_estimated_attendance ON engagement_report_data(estimated_attendance);

-- Update comments
COMMENT ON COLUMN engagement_report_data.estimated_attendance IS 'Anticipated number of attendees/participants for the event';

SELECT 'Column renamed from attendance_count to estimated_attendance successfully!' as update_status;