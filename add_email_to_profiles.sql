-- Migration: Add email column to profiles table
-- This allows us to store the user's email for quick access without querying auth.users

ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS email VARCHAR(255);

-- Create an index for email lookups
CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);

-- Optional: Copy existing emails from auth.users (if you have direct access)
-- This requires using Supabase's admin API or SQL editor with appropriate permissions
-- For now, emails will be captured during signup in the signup_form()
