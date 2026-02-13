# Role-Based Access Control Implementation

## Overview
The application now has three-tier access control based on user role and supervisor status.

## Access Levels

### 1. All Users (role = "user" or "admin")
These pages are available to everyone:
- **My Profile** - View and edit their own profile information
- **Submit / Edit Report** - Submit weekly reports and edit existing drafts
- **User Manual** - View help documentation

### 2. Supervisors (is_supervisor = true)
In addition to all user pages, supervisors have:
- **Supervisor Summaries** - View saved summaries of their direct reports
- **Dashboard** - Supervisor Dashboard showing submission status of their direct reports

**Supervisor Detection:**
- A user is automatically marked as a supervisor if any other users have their ID as `supervisor_id`
- This is checked on page load and cached in `st.session_state["is_supervisor"]`

### 3. Admins Only (role = "admin")
Admin-only pages (replaces all other pages):
- **Saved Reports** - View all saved reports
- **Staff Recognition** - View staff recognition records
- **Quarterly Recognition** - Quarterly winner selection
- **Admin Dashboard** - Administrative dashboard with all data
- **Supervisors** - Supervisors section for form analysis
- **User Management** - Manage user roles, supervisors, and send password resets

## Data Filtering

### Supervisor Dashboard
- Shows only reports from users with `supervisor_id` = current user's ID
- Uses RPC function `get_finalized_reports_for_supervisor` to fetch data
- Displays list of direct reports and their submission status

### Supervisor Summaries
- Shows only summaries created by the supervisor
- Uses RPC function `get_supervisor_summaries` to fetch data

### Admin Dashboard
- Shows all data (no filtering)
- Requires role = "admin"

## Navigation Updates
The navigation is built dynamically in [app.py](app.py#L81-L110):
1. All users get base pages (My Profile, Submit/Edit Report, User Manual)
2. If is_supervisor = true, add Supervisor Summaries and Dashboard
3. If role = admin, show only admin-specific pages

## Database Requirements
- `profiles` table must have:
  - `id` (UUID, user ID from auth)
  - `role` (varchar: "user" or "admin")
  - `supervisor_id` (UUID, nullable - references another profile)
  - `email` (varchar - stored at signup)
  - `full_name` (varchar)
  - `title` (varchar)

## RLS Policies
Simple RLS policy (in Supabase):
```sql
CREATE POLICY "Allow authenticated users to read own profile"
ON profiles
FOR SELECT
USING (auth.uid() = id);
```

Admin operations bypass RLS using service_role_key client.

## Testing Checklist
- [ ] Regular user can access: My Profile, Submit/Edit Report, User Manual
- [ ] Supervisor (with supervised staff) can access additionally: Supervisor Summaries, Dashboard
- [ ] Admin can access all admin pages only
- [ ] Non-supervisor cannot see Supervisor Summaries or Dashboard
- [ ] Supervisor Dashboard shows only their direct reports
