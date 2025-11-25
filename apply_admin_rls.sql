-- Fix RLS policies to allow admins to view all reports

-- 1. Drop existing restrictive policies on the reports table
DROP POLICY IF EXISTS "Admins can manage all reports" ON reports;
DROP POLICY IF EXISTS "Admins can create reports for others" ON reports;

-- 2. Create a policy that allows admins to do EVERYTHING (SELECT, INSERT, UPDATE, DELETE)
CREATE POLICY "Admins can manage all reports" ON reports
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM profiles 
      WHERE profiles.id = auth.uid() 
      AND profiles.role = 'admin'
    )
  );

-- 3. Verify the policy was created
SELECT * FROM pg_policies WHERE tablename = 'reports';
