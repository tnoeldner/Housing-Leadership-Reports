-- Database setup script for UND Housing Leadership Reports
-- Run this in your Supabase SQL editor to create required tables

-- 1. Create admin_settings table for storing configurable settings
CREATE TABLE IF NOT EXISTS admin_settings (
  id SERIAL PRIMARY KEY,
  setting_name TEXT UNIQUE NOT NULL,
  setting_value JSONB NOT NULL,
  updated_by UUID REFERENCES profiles(id),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS for admin_settings
ALTER TABLE admin_settings ENABLE ROW LEVEL SECURITY;

-- Allow admins to manage settings
CREATE POLICY "Admin can manage settings" ON admin_settings
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM profiles 
      WHERE profiles.id = auth.uid() 
      AND profiles.role = 'admin'
    )
  );

-- 2. Add submission tracking columns to reports table (if they don't exist)
ALTER TABLE reports 
ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS created_by_admin UUID REFERENCES profiles(id),
ADD COLUMN IF NOT EXISTS admin_note TEXT;

-- 3. Create an index for better performance on submission tracking
CREATE INDEX IF NOT EXISTS idx_reports_submitted_at ON reports(submitted_at);
CREATE INDEX IF NOT EXISTS idx_reports_week_status ON reports(week_ending_date, status);

-- 4. Insert default deadline settings
INSERT INTO admin_settings (setting_name, setting_value) 
VALUES (
  'report_deadline', 
  '{"day_of_week": 0, "hour": 16, "minute": 0, "grace_hours": 16}'::jsonb
) 
ON CONFLICT (setting_name) DO NOTHING;

-- 5. Create a function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_admin_settings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to automatically update the timestamp
DROP TRIGGER IF EXISTS update_admin_settings_updated_at ON admin_settings;
CREATE TRIGGER update_admin_settings_updated_at
  BEFORE UPDATE ON admin_settings
  FOR EACH ROW
  EXECUTE FUNCTION update_admin_settings_updated_at();

-- 6. Update RLS policies for reports table to allow admin creation
-- Drop existing policies that might be too restrictive
DROP POLICY IF EXISTS "Users can view own reports" ON reports;
DROP POLICY IF EXISTS "Users can insert own reports" ON reports;
DROP POLICY IF EXISTS "Users can update own reports" ON reports;
DROP POLICY IF EXISTS "Supervisors can view team reports" ON reports;
DROP POLICY IF EXISTS "Admins can manage all reports" ON reports;

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

-- Verify the setup
SELECT 'Database setup completed successfully' as status;
SELECT setting_name, setting_value FROM admin_settings;