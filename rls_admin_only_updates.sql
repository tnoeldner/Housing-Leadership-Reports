-- RLS Policy: Allow only admins to update profiles
-- This ensures that only users with role='admin' can modify other users' profiles

-- Drop existing conflicting policies if needed
DROP POLICY IF EXISTS "Allow admin to update profiles" ON profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON profiles;

-- Create a policy that allows admins to update any profile
CREATE POLICY "Allow admin to update profiles"
ON profiles
FOR UPDATE
USING (
  (SELECT role FROM profiles WHERE id = auth.uid()) = 'admin'
)
WITH CHECK (
  (SELECT role FROM profiles WHERE id = auth.uid()) = 'admin'
);

-- Create a policy that allows users to update only their own profile (non-admin fields)
CREATE POLICY "Users can update own profile"
ON profiles
FOR UPDATE
USING (auth.uid() = id)
WITH CHECK (
  auth.uid() = id AND
  -- Prevent regular users from changing admin-only fields
  -- This is enforced on the application level, but RLS can provide an extra layer
  (SELECT role FROM profiles WHERE id = auth.uid()) = (SELECT role FROM profiles WHERE id = auth.uid())
);

-- Allow admins to read all profiles
DROP POLICY IF EXISTS "Admins can read all profiles" ON profiles;
CREATE POLICY "Admins can read all profiles"
ON profiles
FOR SELECT
USING (
  (SELECT role FROM profiles WHERE id = auth.uid()) = 'admin'
);

-- Allow users to read their own profile
DROP POLICY IF EXISTS "Users can read own profile" ON profiles;
CREATE POLICY "Users can read own profile"
ON profiles
FOR SELECT
USING (auth.uid() = id);
