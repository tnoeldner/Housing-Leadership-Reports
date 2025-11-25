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

This guide will help you get started and make the most of the app, whether you are a staff member, supervisor, or admin.

---

### 1. Getting Started: Account & Access
- **Sign Up:** Use the sidebar to create an account. Enter your UND email, full name, position title, and a password.
- **Email Confirmation:** After signing up, check your email for a Supabase confirmation link. You must confirm before logging in.
- **Login:** Use the sidebar to log in. Once logged in, the sidebar will show pages available for your role.
- **Roles:**
    - **Staff:** Submit and view your own reports, view your own recognition.
    - **Supervisor:** Submit/view own reports, view team reports, generate and save team summaries, view team recognition.
    - **Admin/Director:** Full access to all finalized reports, archived weekly summaries, and all recognition.

---

### 2. Submitting a Weekly Report
1. Go to **Submit / Edit Report** in the sidebar.
2. Select the active week (the app calculates the current week and grace period).
3. Complete the following sections:
    - **Core Activities:** Add entries for Students/Stakeholders, Projects, Collaborations, General Job Responsibilities, Staffing, KPIs. For each, add Successes and Challenges.
    - **General Updates:** Personal check-in, Professional development, Lookahead, and (optionally) Director concerns.
4. **Save Draft:** You can save your progress and return later.
5. **Proceed to Review:** The app uses AI to categorize your entries (ASCEND/NORTH) and generate a summary.
6. **Review & Edit:** Edit categories, adjust the AI summary, confirm well-being score and general updates.
7. **Lock and Submit:** Finalizes the report. Finalized reports cannot be edited without supervisor/admin help.

---

### 3. Staff Recognition
1. Go to **Staff Recognition** tab in the Saved Reports Archive.
2. View weekly recognition reports for ASCEND and NORTH categories.
3. Download recognition reports as markdown files.
4. Supervisors and admins can view all staff recognition; staff see their own.

---

### 4. Viewing Weekly Summaries
1. Go to **Weekly Summaries** tab in the Saved Reports Archive.
2. View all finalized weekly summaries grouped by year.
3. Download summaries as markdown files.
4. Supervisors and admins can view all summaries; staff see their own.

---

### 5. Navigation & Pages
- **My Profile:** View and update your profile information.
- **Submit / Edit Report:** Create or edit your weekly report.
- **Saved Reports Archive:** Access all duty analyses, staff recognition, and weekly summaries.
- **User Manual:** Access this guide anytime.
- **Supervisor/Admin Pages:** Supervisors and admins have additional dashboard and team summary pages.

---

### 6. Privacy & Security
- **Row-Level Security:** You only see reports and recognition you are permitted to view.
- **Director Concerns:** Only visible to the report owner and admins/directors.
- **Supervisors:** Can view finalized reports for their direct reports only.
- **Admins/Directors:** Have access to all reports and summaries.

---

### 7. Troubleshooting & Tips
- If the app shows unexpected behavior, restart and check Streamlit logs for errors.
- If you can't see a report, confirm it is finalized and your supervisor_id is set correctly in your profile.
- If AI summary fails, simplify your entries and retry.
- For help, contact your supervisor or admin.

---

**Thank you for using the UND Housing Leadership Reporting Tool!**
""", unsafe_allow_html=False)
