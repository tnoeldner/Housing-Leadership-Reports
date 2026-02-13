-- FIX: RLS Policies with infinite recursion removed
-- Drop the problematic policies
DROP POLICY IF EXISTS "Allow admin to update profiles" ON profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON profiles;
DROP POLICY IF EXISTS "Admins can read all profiles" ON profiles;
DROP POLICY IF EXISTS "Users can read own profile" ON profiles;

-- Create a helper function to check if user is admin (SECURITY DEFINER bypasses RLS)
CREATE OR REPLACE FUNCTION is_admin(user_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM profiles 
    WHERE id = user_id AND role = 'admin'
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Now create RLS policies that use the function (avoids recursion)
-- Allow admins to update any profile
CREATE POLICY "admins_can_update_any_profile"
ON profiles
FOR UPDATE
USING (is_admin(auth.uid()))
WITH CHECK (is_admin(auth.uid()));

-- Allow users to update only their own profile
CREATE POLICY "users_can_update_own_profile"
ON profiles
FOR UPDATE
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id);

-- Allow admins to read all profiles
CREATE POLICY "admins_can_read_all_profiles"
ON profiles
FOR SELECT
USING (is_admin(auth.uid()));

-- Allow users to read their own profile
CREATE POLICY "users_can_read_own_profile"
ON profiles
FOR SELECT
USING (auth.uid() = id);
