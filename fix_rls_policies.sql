-- Quick fix for RLS policy issues on reports table
-- Run this in your Supabase SQL editor to fix report creation permissions

-- Drop existing restrictive policies
DROP POLICY IF EXISTS "Users can view own reports" ON reports;
DROP POLICY IF EXISTS "Users can insert own reports" ON reports;
DROP POLICY IF EXISTS "Users can update own reports" ON reports;
DROP POLICY IF EXISTS "Supervisors can view team reports" ON reports;
DROP POLICY IF EXISTS "Admins can manage all reports" ON reports;
DROP POLICY IF EXISTS "Supervisors can unlock team reports" ON reports;
DROP POLICY IF EXISTS "Admins can create reports for others" ON reports;

-- Create comprehensive RLS policies for reports
-- Allow users to view their own reports
CREATE POLICY "Users can view own reports" ON reports
  FOR SELECT USING (user_id = auth.uid());

-- Allow users to insert their own reports
CREATE POLICY "Users can insert own reports" ON reports
  FOR INSERT WITH CHECK (user_id = auth.uid());

-- Allow users to update their own reports (when not finalized or when unlocked)
CREATE POLICY "Users can update own reports" ON reports
  FOR UPDATE USING (
    user_id = auth.uid() AND 
    (status != 'finalized' OR status = 'unlocked')
  );

-- Allow supervisors to view reports of their direct reports
CREATE POLICY "Supervisors can view team reports" ON reports
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM profiles 
      WHERE profiles.supervisor_id = auth.uid() 
      AND profiles.id = reports.user_id
    )
  );

-- Allow supervisors to unlock reports of their direct reports
CREATE POLICY "Supervisors can unlock team reports" ON reports
  FOR UPDATE USING (
    EXISTS (
      SELECT 1 FROM profiles 
      WHERE profiles.supervisor_id = auth.uid() 
      AND profiles.id = reports.user_id
    )
  );

-- Allow admins to manage all reports (view, insert, update, delete)
CREATE POLICY "Admins can manage all reports" ON reports
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM profiles 
      WHERE profiles.id = auth.uid() 
      AND profiles.role = 'admin'
    )
  );

-- Allow admins to create reports on behalf of others
CREATE POLICY "Admins can create reports for others" ON reports
  FOR INSERT WITH CHECK (
    EXISTS (
      SELECT 1 FROM profiles 
      WHERE profiles.id = auth.uid() 
      AND profiles.role = 'admin'
    )
  );

-- Verify policies were created
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual 
FROM pg_policies 
WHERE tablename = 'reports';