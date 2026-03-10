import streamlit as st
import time
import pandas as pd
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
        from datetime import timezone
        def ZoneInfo(tz):
            if tz == "US/Central" or tz == "America/Chicago":
                return timezone.utc  # Simplified fallback
            return timezone.utc

from src.database import supabase
from src.utils import get_deadline_settings
from src.email_service import send_email

def profile_page():
    st.title("My Profile")
    st.write(f"**Email:** {st.session_state['user'].email}")
    st.write(f"**Role:** {st.session_state.get('role', 'N/A')}")
    with st.form("update_profile"):
        current_name = st.session_state.get("full_name", "")
        new_name = st.text_input("Full Name", value=current_name)
        current_title = st.session_state.get("title", "")
        new_title = st.text_input("Position Title", value=current_title)
        submitted = st.form_submit_button("Update Profile")
        if submitted:
            try:
                user_id = st.session_state["user"].id
                update_data = {"full_name": new_name, "title": new_title}
                supabase.table("profiles").update(update_data).eq("id", user_id).execute()
                st.session_state["full_name"] = new_name
                st.session_state["title"] = new_title
                st.success("Profile updated successfully!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"An error occurred: {e}")

## Welcome to the UND Housing Leadership Reporting Tool


def user_manual_page():
    st.title("User Manual & Getting Started Guide")
    st.markdown("""
## Welcome to the UND Housing Leadership Reporting Tool

Practical steps for signing in, submitting weekly impact reports, and using supervisor/admin tools.

---

### 1) Sign In and Roles
- **Sign up or log in in the sidebar.** Use your UND email; confirm the email link before logging in the first time.
- **Profile basics:** Set your name and title in **My Profile** so supervisors and admins see accurate info.
- **Roles:**
    - **Staff:** Create, edit, and finalize your own weekly reports; view your own recognition.
    - **Supervisors:** Everything staff can do, plus view direct-report submissions, respond with email, and save team summaries.
    - **Admins/Directors:** Full access to all reports, summaries, recognition, form analysis, and system settings.

---

### 2) Weekly Report Workflow (Staff)
1. Open **Submit / Edit Report**.
2. Choose the active week. Deadlines and grace periods are shown; admins can unlock late reports if needed.
3. Add entries for each section (Students/Stakeholders, Projects, Collaborations, General Job Responsibilities, Staffing/Personnel, KPIs, Events/Committees) with successes and challenges.
4. Add **General Updates** (professional development, lookahead, personal check-in, optional director concerns) and your well-being rating.
5. **Save Draft** anytime. Use **Proceed to Review** to let the AI categorize items (ASCEND/NORTH) and draft a summary.
6. Review and adjust categories and text. When ready, **Lock and Submit** to finalize.
7. Finalized reports are read-only; ask a supervisor/admin to unlock if a correction is required after the deadline.

---

### 3) Supervisor Tools
- **Supervisor Dashboard:** Track who has submitted for the selected week and view status at a glance.
- **Team Reports Viewer:** Filter by date range, inspect report details, and send email responses to direct reports from within the app.
- **Saved Team Summaries:** View AI summaries you generated for prior weeks.
- **Form Analysis:** Duty analysis, general Roompact form analysis, and individual report review with AI-assisted summaries.

---

### 4) Admin/Director Tools
- **Saved Reports:** Browse duty analyses, staff recognition, weekly summaries, and all submitted weekly reports.
- **Staff Recognition & Quarterly Recognition:** Review weekly recognition outputs and manage quarterly winners.
- **Admin Dashboard:**
    - Deadline settings and submission tracking
    - Email configuration and outbound reply helpers
    - User management (roles, supervisor assignments, password reset emails)
    - AI prompt templates for summaries
    - Weekly reports summary and weekly summary generator
- **Form Analysis:** Same tooling as supervisors, but with full data access.

---

### 5) Data Visibility & Security
- Row-level security limits visibility to what your role permits. Supervisors see direct reports; admins can bypass RLS via the service role.
- Director concerns fields are visible only to the report owner and admins/directors.

---

### 6) Troubleshooting
- Cannot submit? Check the deadline banner; if the grace period passed, request an admin unlock.
- Missing reports? Ensure your supervisor assignment is set; admins can adjust it in User Management.
- AI summary issues? Simplify the text or retry the review step.
- For account or access problems, contact an admin/director.

---

Thank you for using the UND Housing Leadership Reporting Tool!
""", unsafe_allow_html=False)
