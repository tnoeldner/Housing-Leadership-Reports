# RLS Canonical Policies

This folder holds the authoritative RLS definitions to apply in Supabase.

## How to apply
1. Use the service-role key in the Supabase SQL editor.
2. Run `canonical_policies.sql` once. It drops old policies for the covered tables and recreates the intended set.
3. Verify (optional):
   ```sql
   SELECT schemaname, tablename, policyname, cmd
   FROM pg_policies
   WHERE tablename IN ('profiles','reports','engagement_report_data');
   ```

## Coverage
- `profiles`: admins read/update all; users read/insert/update own (first-login create allowed).
- `reports`: admins all access; users own view/insert/update (not finalized unless unlocked); supervisors view/unlock team; admins can create for others.
- `engagement_report_data`: authenticated + service-role can read/modify.

## Superseded files
Legacy RLS scripts in the repo are marked "DO NOT RUN" and kept only for reference:
- fix_rls_clean.sql
- fix_rls_policies.sql
- apply_admin_rls.sql
- simplify_rls.sql / rls_admin_only_updates.sql / fix_rls_recursion.sql (overlapping profiles policies)

Please use only `canonical_policies.sql` going forward.
