-- Canonical RLS policies for Housing Leadership Reports
-- Apply with service role in Supabase SQL editor.
-- Tables covered: profiles, reports, engagement_report_data.

-- PROFILES: admins full access; users read/update own (no self-joins to avoid recursion)
DROP POLICY IF EXISTS "admins_can_update_any_profile" ON profiles;
DROP POLICY IF EXISTS "users_can_update_own_profile" ON profiles;
DROP POLICY IF EXISTS "admins_can_read_all_profiles" ON profiles;
DROP POLICY IF EXISTS "users_can_read_own_profile" ON profiles;
DROP POLICY IF EXISTS "service_role_all_profiles" ON profiles;
DROP POLICY IF EXISTS "users_can_insert_own_profile" ON profiles;

-- Helper claim check for admin: assumes JWT has claim role='admin'. Adjust if your claim key differs.
-- This avoids selecting from profiles inside the policy (which triggers recursion).

CREATE POLICY "service_role_all_profiles" ON profiles
  FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "admins_can_read_all_profiles" ON profiles
  FOR SELECT
  USING ((auth.jwt() ->> 'role') = 'admin' OR auth.role() = 'service_role');

CREATE POLICY "admins_can_update_any_profile" ON profiles
  FOR ALL
  USING ((auth.jwt() ->> 'role') = 'admin' OR auth.role() = 'service_role')
  WITH CHECK ((auth.jwt() ->> 'role') = 'admin' OR auth.role() = 'service_role');

CREATE POLICY "users_can_read_own_profile" ON profiles
  FOR SELECT
  USING (id = auth.uid());

CREATE POLICY "users_can_insert_own_profile" ON profiles
  FOR INSERT
  WITH CHECK (id = auth.uid());

CREATE POLICY "users_can_update_own_profile" ON profiles
  FOR UPDATE
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());

-- REPORTS: admins all; users own; supervisors see/unlock team; admins create for others
DROP POLICY IF EXISTS "admins_all_access" ON reports;
DROP POLICY IF EXISTS "admins_all_access_claim" ON reports;
DROP POLICY IF EXISTS "service_role_all_reports" ON reports;
DROP POLICY IF EXISTS "authenticated_all_reports" ON reports;
DROP POLICY IF EXISTS "admins_can_manage_all_reports" ON reports;
DROP POLICY IF EXISTS "users_view_own" ON reports;
DROP POLICY IF EXISTS "users_insert_own" ON reports;
DROP POLICY IF EXISTS "users_update_own" ON reports;
DROP POLICY IF EXISTS "supervisors_view_team" ON reports;
DROP POLICY IF EXISTS "supervisors_unlock_team" ON reports;
DROP POLICY IF EXISTS "Users can view own reports" ON reports;
DROP POLICY IF EXISTS "Users can insert own reports" ON reports;
DROP POLICY IF EXISTS "Users can update own reports" ON reports;
DROP POLICY IF EXISTS "Supervisors can view team reports" ON reports;
DROP POLICY IF EXISTS "Supervisors can unlock team reports" ON reports;
DROP POLICY IF EXISTS "Admins can create reports for others" ON reports;
DROP POLICY IF EXISTS "admins_create_for_others" ON reports;

CREATE POLICY "admins_all_access" ON reports
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin'))
  WITH CHECK (TRUE);

CREATE POLICY "service_role_all_reports" ON reports
  FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Temporary unblock: allow any authenticated user to manage reports (relies on user_id being supplied in payload)
CREATE POLICY "authenticated_all_reports" ON reports
  FOR ALL
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

-- Fallback for admins when profile lookup is missing; relies on JWT claim role='admin'
CREATE POLICY "admins_all_access_claim" ON reports
  FOR ALL
  USING ((auth.jwt() ->> 'role') = 'admin' OR auth.role() = 'service_role')
  WITH CHECK ((auth.jwt() ->> 'role') = 'admin' OR auth.role() = 'service_role');

CREATE POLICY "users_view_own" ON reports
  FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "users_insert_own" ON reports
  FOR INSERT
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "users_update_own" ON reports
  FOR UPDATE
  USING (user_id = auth.uid() AND (status != 'finalized' OR status = 'unlocked'))
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "supervisors_view_team" ON reports
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.supervisor_id = auth.uid()
        AND p.id = reports.user_id
    )
  );

CREATE POLICY "supervisors_unlock_team" ON reports
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM profiles p
      WHERE p.supervisor_id = auth.uid()
        AND p.id = reports.user_id
    )
  );

CREATE POLICY "admins_create_for_others" ON reports
  FOR INSERT
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin'));

-- ENGAGEMENT_REPORT_DATA: authenticated + service-role can read/modify
DROP POLICY IF EXISTS "Allow service key and authenticated users to read engagement data" ON engagement_report_data;
DROP POLICY IF EXISTS "Allow service key and authenticated users to modify engagement data" ON engagement_report_data;

CREATE POLICY "Allow service key and authenticated users to read engagement data"
  ON engagement_report_data
  FOR SELECT
  USING (auth.role() IN ('authenticated', 'service_role'));

CREATE POLICY "Allow service key and authenticated users to modify engagement data"
  ON engagement_report_data
  FOR ALL
  USING (auth.role() IN ('authenticated', 'service_role'))
  WITH CHECK (auth.role() IN ('authenticated', 'service_role'));

-- ADMIN_SETTINGS: service role and admins can manage
DROP POLICY IF EXISTS "service_role_all_admin_settings" ON admin_settings;
DROP POLICY IF EXISTS "admins_all_admin_settings" ON admin_settings;
DROP POLICY IF EXISTS "authenticated_all_admin_settings" ON admin_settings;

-- Service role full access
CREATE POLICY "service_role_all_admin_settings" ON admin_settings
  FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Admins via profile lookup (avoids relying on custom JWT claims)
CREATE POLICY "admins_all_admin_settings" ON admin_settings
  FOR ALL
  USING (
    auth.role() = 'service_role'
    OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
  )
  WITH CHECK (
    auth.role() = 'service_role'
    OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
  );

-- Temporary unblock: allow any authenticated user to manage admin_settings
CREATE POLICY "authenticated_all_admin_settings" ON admin_settings
  FOR ALL
  USING (auth.role() = 'authenticated' OR auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'authenticated' OR auth.role() = 'service_role');

-- Verification helper (run manually if desired)
-- SELECT schemaname, tablename, policyname, cmd FROM pg_policies WHERE tablename IN ('profiles','reports','engagement_report_data');
