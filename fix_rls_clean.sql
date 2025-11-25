-- Clean up ALL existing RLS policies on reports table
DROP POLICY IF EXISTS "Admins can manage all reports" ON reports;
DROP POLICY IF EXISTS "Admins can view all reports." ON reports;
DROP POLICY IF EXISTS "Allow admins to view all reports" ON reports;
DROP POLICY IF EXISTS "Allow users to insert their own reports" ON reports;
DROP POLICY IF EXISTS "Allow users to update their own reports" ON reports;
DROP POLICY IF EXISTS "Allow users to view their own reports" ON reports;
DROP POLICY IF EXISTS "delete_reports_admin" ON reports;
DROP POLICY IF EXISTS "insert_reports_owner" ON reports;
DROP POLICY IF EXISTS "select_reports_owner_or_admin" ON reports;
DROP POLICY IF EXISTS "update_reports_owner_or_admin" ON reports;

-- Create clean, simple policies

-- 1. Admins can do EVERYTHING
CREATE POLICY "admins_all_access" ON reports
  FOR ALL 
  USING (
    EXISTS (
      SELECT 1 FROM profiles 
      WHERE profiles.id = auth.uid() 
      AND profiles.role = 'admin'
    )
  );

-- 2. Users can view their own reports
CREATE POLICY "users_view_own" ON reports
  FOR SELECT
  USING (user_id = auth.uid());

-- 3. Users can insert their own reports
CREATE POLICY "users_insert_own" ON reports
  FOR INSERT
  WITH CHECK (user_id = auth.uid());

-- 4. Users can update their own reports (when not finalized)
CREATE POLICY "users_update_own" ON reports
  FOR UPDATE
  USING (
    user_id = auth.uid() 
    AND (status != 'finalized' OR status = 'unlocked')
  );

-- Verify the new policies
SELECT policyname, cmd, roles 
FROM pg_policies 
WHERE tablename = 'reports';
