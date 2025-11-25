-- Check if there are ANY reports in the table (bypassing RLS for the count if run as superuser/postgres)
SELECT count(*) as total_reports FROM reports;

-- Check the most recent reports
SELECT id, week_ending_date, user_id, status, created_at 
FROM reports 
ORDER BY created_at DESC 
LIMIT 5;

-- Verify RLS is enabled
SELECT relname, relrowsecurity 
FROM pg_class 
WHERE oid = 'reports'::regclass;

-- List all policies on the reports table again to be sure
SELECT policyname, cmd, roles, qual
FROM pg_policies 
WHERE tablename = 'reports';
