# Engagement Analysis Cleanup - Database SQL Commands

## Database Tables to Remove

Execute these SQL commands in your Supabase SQL Editor to completely remove all engagement analysis database objects:

```sql
-- Drop engagement analysis tables
DROP TABLE IF EXISTS event_table CASCADE;
DROP TABLE IF EXISTS saved_engagement_analyses CASCADE;
DROP TABLE IF EXISTS engagement_report_data CASCADE;

-- Remove any related indexes or functions if they exist
-- (These may not exist depending on your setup)
DROP INDEX IF EXISTS idx_event_table_roompact_id;
DROP INDEX IF EXISTS idx_event_table_event_approval;
DROP INDEX IF EXISTS idx_event_table_is_approved;
DROP INDEX IF EXISTS idx_event_table_hall;
DROP INDEX IF EXISTS idx_event_table_name_of_event;
DROP INDEX IF EXISTS idx_event_table_date_start;
DROP INDEX IF EXISTS idx_event_table_created_at;
DROP INDEX IF EXISTS idx_event_table_updated_at;
DROP INDEX IF EXISTS idx_event_table_raw_data;

-- Remove any functions related to engagement analysis
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;

-- Clean up any RLS policies that might reference these tables
-- (Replace 'your_policy_name' with actual policy names if they exist)
-- DROP POLICY IF EXISTS "policy_name" ON event_table;
-- DROP POLICY IF EXISTS "policy_name" ON saved_engagement_analyses;
-- DROP POLICY IF EXISTS "policy_name" ON engagement_report_data;
```

## Verification

After running these commands, verify the cleanup by checking:

```sql
-- Check that tables are gone
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN ('event_table', 'saved_engagement_analyses', 'engagement_report_data');

-- Should return no rows if cleanup was successful
```

## What Was Removed

- All Roompact API integration code
- All engagement analysis functions and UI components
- Event data synchronization scripts
- Database schemas for event tracking
- Over 50 engagement analysis related files
- Engagement analysis tabs from supervisor and saved reports sections

The application now focuses solely on its core functionality without the problematic engagement analysis features.