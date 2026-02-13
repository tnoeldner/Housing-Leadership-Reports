-- SIMPLIFIED: Remove complex RLS policies and rely on application-level auth
-- This is safer and avoids recursion/complexity issues

-- Drop all custom RLS policies
DROP POLICY IF EXISTS "admins_can_update_any_profile" ON profiles;
DROP POLICY IF EXISTS "users_can_update_own_profile" ON profiles;
DROP POLICY IF EXISTS "admins_can_read_all_profiles" ON profiles;
DROP POLICY IF EXISTS "users_can_read_own_profile" ON profiles;
DROP POLICY IF EXISTS "Allow admin to update profiles" ON profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON profiles;
DROP POLICY IF EXISTS "Admins can read all profiles" ON profiles;
DROP POLICY IF EXISTS "Users can read own profile" ON profiles;

-- Drop the helper function if it exists
DROP FUNCTION IF EXISTS is_admin(UUID);

-- Create a simple, permissive policy that allows authenticated users to read their own profile
-- (required for login to work)
CREATE POLICY "Allow authenticated users to read own profile"
ON profiles
FOR SELECT
USING (auth.uid() = id);

-- Authentication check is done at the application level (admin_settings.py checks st.session_state['role'])
-- The admin_client with service_role_key bypasses RLS entirely, so it can update any profile
