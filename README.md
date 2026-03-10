# Housing Leadership Reports

Streamlit app for weekly impact reporting, supervisor dashboards, and admin oversight for UND Housing & Residence Life.

## Features
- Weekly staff reports with ASCEND/NORTH categorization, AI summaries, and well-being check-ins
- Supervisor dashboards to track submissions, view direct-report details, and send email responses
- Saved reports archive for duty analyses, recognition, weekly summaries, and all submitted reports
- Admin tools for deadlines, user management, AI prompt templates, and summary generation
- Optional Roompact form analysis to pull duty and engagement data

## Roles and Access
- **Staff:** Create, edit, and finalize your own reports; view your own recognition.
- **Supervisors:** Everything staff can do, plus view direct-report submissions, save team summaries, and access the supervisor dashboard and form analysis tools.
- **Admins/Directors:** Full access to all reports, recognition, admin dashboard, saved reports archive, and quarterly recognition.

## Run the App Locally
1. Install Python 3.11+.
2. Create and activate a virtual environment:
	- Windows: `python -m venv .venv` then `.venv\Scripts\activate`
3. Install dependencies: `pip install -r requirements.txt`.
4. Set environment variables (see below).
5. Launch: `streamlit run app.py` (or use the provided VS Code task to run `app.py`).

## Required Configuration
- `SUPABASE_URL` and `SUPABASE_KEY` (anon key) for user-scoped access
- `SUPABASE_SERVICE_ROLE_KEY` for admin operations and background tasks
- `GOOGLE_API_KEY` for Gemini-powered summaries and categorization
- Roompact (optional for form analysis): `ROOMPACT_API_TOKEN` or `ROOMPACT_API_KEY`; optional `ROOMPACT_BASE_URL`

## Usage Highlights
- Sign up or log in from the sidebar; confirm the email link on first login.
- Use **Submit / Edit Report** to create weekly reports; AI assists with categorization and summaries before you finalize.
- Supervisors use **Supervisor Dashboard**, **Team Reports Viewer**, and **Form Analysis** to monitor submissions and respond.
- Admins manage deadlines, users, AI prompts, and saved outputs from **Admin Dashboard**, **Saved Reports**, **Staff Recognition**, and **Quarterly Recognition**.

## Support
- If you cannot submit due to a passed deadline, request an admin unlock.
- If reports or team members are missing, verify supervisor assignments in **Admin Dashboard > User Management**.
- For access or credential issues, contact an administrator/director.
