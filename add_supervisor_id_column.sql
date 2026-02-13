-- Add supervisor_id column to profiles table to track supervisor assignments
-- Run this in your Supabase SQL Editor if the column doesn't exist

ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS supervisor_id UUID REFERENCES profiles(id) ON DELETE SET NULL;

-- Create an index on supervisor_id for better query performance
CREATE INDEX IF NOT EXISTS idx_profiles_supervisor_id ON profiles(supervisor_id);

-- Add a comment to document the column
COMMENT ON COLUMN profiles.supervisor_id IS 'UUID of the supervisor assigned to this staff member';
