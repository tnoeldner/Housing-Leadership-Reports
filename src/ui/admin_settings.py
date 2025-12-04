import time
import os
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from src.database import supabase
from src.utils import get_deadline_settings
from src.email_service import send_email
import streamlit as st

def admin_settings_page():
    if "user" not in st.session_state:
        st.warning("You must be logged in to view this page.")
        st.stop()
    st.title("Administrator Settings")
    st.write("Configure system settings and deadlines.")
    tab1, tab2, tab3, tab4 = st.tabs(["📅 Deadline Settings", "📊 Submission Tracking", "📧 Email Configuration", "📝 AI Prompt Templates"])
    with tab4:
        st.subheader("AI Prompt Templates")
        st.write("Edit the prompt templates used for AI-generated summaries. Changes take effect immediately for all users.")
        # Load current prompts from admin_settings table
        # Default prompts (should match those in ai.py)
        default_dashboard_prompt = """
You are an executive assistant for the Director of Housing & Residence Life at UND. Your task is to synthesize multiple team reports from the week ending {selected_date_for_summary} into a single, comprehensive summary report.

IMPORTANT: Start your response immediately with the first section heading. Do not include any introductory text, cover page text, or phrases like \"Here is the comprehensive summary report\" or \"Weekly Summary Report: Housing & Residence Life\". Begin directly with the Executive Summary section.

DATA SOURCES AVAILABLE:
1. Weekly staff reports from residence life team members
2. Weekly duty reports analysis (if available) - quantitative data on incidents, safety, maintenance, and operations
3. Weekly engagement analysis (if available) - event programming, attendance data, community engagement activities

... (rest of your default prompt here) ...
"""
        default_individual_prompt = """
You are an executive assistant for the Director of Housing & Residence Life at UND. Your task is to synthesize the following individual staff report into a concise, director-focused summary for the week ending {week_ending_date}. Your summary should:
- Reference the staff member by name: {team_member}
- Highlight professional development, engagement, successes, and challenges
- Include any personal well-being check-in and overall well-being score ({well_being_rating}/5)
- Note any concerns for the director and key topics/lookahead
- Use clear, professional language and reference specific activities where possible
- Be written for the director to quickly understand the staff member's overall week and priorities

STAFF REPORT DATA:
{report_json}

Professional Development: {professional_development}
Key Topics & Lookahead: {key_topics_lookahead}
Personal Check-in: {personal_check_in}
Director Concerns: {director_concerns}
Well-being Rating: {well_being_rating}
"""
        dashboard_prompt = ""
        individual_prompt = ""
        try:
            dashboard_row = supabase.table("admin_settings").select("setting_value").eq("setting_name", "dashboard_prompt").single().execute()
            if dashboard_row.data and dashboard_row.data.get("setting_value"):
                dashboard_prompt = dashboard_row.data.get("setting_value", "")
            else:
                dashboard_prompt = default_dashboard_prompt
        except Exception:
            dashboard_prompt = default_dashboard_prompt
        try:
            individual_row = supabase.table("admin_settings").select("setting_value").eq("setting_name", "individual_prompt").single().execute()
            if individual_row.data and individual_row.data.get("setting_value"):
                individual_prompt = individual_row.data.get("setting_value", "")
            else:
                individual_prompt = default_individual_prompt
        except Exception:
            individual_prompt = default_individual_prompt
        with st.form("ai_prompt_templates_form"):
            dashboard_prompt_edit = st.text_area("Admin Dashboard Summary Prompt", value=dashboard_prompt, height=200)
            individual_prompt_edit = st.text_area("Individual Report Summary Prompt", value=individual_prompt, height=200)
            if st.form_submit_button("Save AI Prompts", type="primary"):
                admin_user_id = st.session_state["user"].id
                try:
                    with st.spinner("Saving AI prompts to database..."):
                        supabase.table("admin_settings").upsert({
                            "setting_name": "dashboard_prompt",
                            "setting_value": dashboard_prompt_edit,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                        supabase.table("admin_settings").upsert({
                            "setting_name": "individual_prompt",
                            "setting_value": individual_prompt_edit,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                    st.success("✅ AI prompt templates saved successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save AI prompts: {e}")

    with tab1:
        st.subheader("Weekly Report Deadline Configuration")
        deadline_config = get_deadline_settings(supabase)
        current_day = deadline_config.get("day_of_week", 0)
        current_hour = deadline_config.get("hour", 16)
        current_minute = deadline_config.get("minute", 0)
        current_grace = deadline_config.get("grace_hours", 16)
        st.info(f"**Current Settings:** Reports due every **{['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][current_day]}** at **{current_hour:02d}:{current_minute:02d}** with **{current_grace}** hour grace period")
        with st.form("deadline_settings"):
            st.write("Set when weekly reports are due:")
            col1, col2, col3 = st.columns(3)
            with col1:
                deadline_day = st.selectbox(
                    "Day of Week",
                    options=[0, 1, 2, 3, 4, 5, 6],
                    format_func=lambda x: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][x],
                    index=current_day
                )
            with col2:
                deadline_hour = st.selectbox(
                    "Hour (24-hour format)",
                    options=list(range(24)),
                    format_func=lambda x: f"{x:02d}:00",
                    index=current_hour
                )
            with col3:
                deadline_minute = st.selectbox(
                    "Minute",
                    options=[0, 15, 30, 45],
                    format_func=lambda x: f"{x:02d}",
                    index=[0, 15, 30, 45].index(current_minute) if current_minute in [0, 15, 30, 45] else 0
                )
            grace_period = st.number_input(
                "Grace Period (hours after deadline for editing)",
                min_value=0,
                max_value=72,
                value=current_grace,
                help="How many hours after the deadline staff can still edit their reports"
            )
            st.info(f"Current setting: Reports due every **{['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][deadline_day]}** at **{deadline_hour:02d}:{deadline_minute:02d}** with **{grace_period}** hour grace period")
            if st.form_submit_button("Save Deadline Settings", type="primary"):
                try:
                    new_settings = {
                        "day_of_week": deadline_day,
                        "hour": deadline_hour,
                        "minute": deadline_minute,
                        "grace_hours": grace_period
                    }
                    admin_user_id = st.session_state["user"].id
                    with st.spinner("Saving settings to database..."):
                        result = supabase.table("admin_settings").upsert({
                            "setting_name": "report_deadline",
                            "setting_value": new_settings,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                        st.write(f"Debug: Database response: {result}")
                    st.session_state["admin_deadline_settings"] = new_settings
                    st.success("✅ Deadline settings saved successfully to database!")
                    st.info(f"Saved: Reports due **{['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][deadline_day]}** at **{deadline_hour:02d}:{deadline_minute:02d}** with **{grace_period}** hour grace period")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save settings: {e}")

    with tab2:
        st.subheader("Submission Tracking Dashboard")
        st.write("Track when reports are submitted and identify late submissions.")
        try:
            recent_reports = supabase.table("reports").select("*").eq("status", "finalized").order("submitted_at", desc=True).limit(50).execute()
            if recent_reports.data:
                deadline_config = get_deadline_settings(supabase)
                submission_data = []
                for report in recent_reports.data:
                    if not isinstance(report, dict):
                        continue
                    submitted_at = report.get("submitted_at") if isinstance(report.get, type(lambda: None)) else None
                    week_ending_val = report.get("week_ending_date") if isinstance(report.get, type(lambda: None)) else None
                    try:
                        if isinstance(submitted_at, str):
                            submission_time = pd.to_datetime(submitted_at)
                        else:
                            submission_time = None
                    except Exception:
                        submission_time = None
                    try:
                        if isinstance(week_ending_val, str):
                            week_ending = pd.to_datetime(week_ending_val)
                        else:
                            week_ending = None
                    except Exception:
                        week_ending = None
                    deadline_day = deadline_config.get("day_of_week", 0)
                    deadline_hour = deadline_config.get("hour", 16)
                    deadline_minute = deadline_config.get("minute", 0)
                    days_after_saturday = (deadline_day - 5) % 7 + (1 if deadline_day <= 5 else 0)
                    if week_ending:
                        deadline_date = week_ending + timedelta(days=days_after_saturday)
                        deadline_datetime = datetime.combine(deadline_date.date(), datetime.min.time().replace(hour=deadline_hour, minute=deadline_minute))
                        deadline_datetime = deadline_datetime.replace(tzinfo=ZoneInfo("America/Chicago"))
                    else:
                        deadline_datetime = None
                    was_on_time = submission_time and deadline_datetime and submission_time <= deadline_datetime
                    was_in_grace = submission_time and deadline_datetime and submission_time <= (deadline_datetime + timedelta(hours=deadline_config.get("grace_hours", 16)))
                    if was_on_time:
                        status = "✅ On Time"
                    elif was_in_grace:
                        status = "⚠️ Grace Period"
                    else:
                        status = "❌ Late"
                    staff_member = report.get("team_member", "Unknown") if isinstance(report.get, type(lambda: None)) else "Unknown"
                    week_ending_str = week_ending_val if week_ending_val else "Unknown"
                    submitted_str = submission_time.strftime("%Y-%m-%d %H:%M:%S") if submission_time else "Unknown"
                    day_of_week_str = submission_time.strftime("%A") if submission_time else "Unknown"
                    time_str = submission_time.strftime("%H:%M") if submission_time else "Unknown"
                    deadline_str = deadline_datetime.strftime("%Y-%m-%d %H:%M") if deadline_datetime else "Unknown"
                    admin_created = "Yes" if (isinstance(report.get, type(lambda: None)) and (report.get("status") == "admin_created" or report.get("created_by_admin"))) else "No"
                    submission_data.append({
                        "Staff Member": staff_member,
                        "Week Ending": week_ending_str,
                        "Submitted": submitted_str,
                        "Day of Week": day_of_week_str,
                        "Time": time_str,
                        "Deadline": deadline_str,
                        "Status": status,
                        "Admin Created": admin_created
                    })
                if submission_data:
                    df = pd.DataFrame(submission_data)
                    st.dataframe(df, use_container_width=True)
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        on_time = len([s for s in submission_data if s["Status"] == "✅ On Time"])
                        st.metric("On Time", on_time)
                    with col2:
                        grace = len([s for s in submission_data if s["Status"] == "⚠️ Grace Period"])
                        st.metric("Grace Period", grace)
                    with col3:
                        late = len([s for s in submission_data if s["Status"] == "❌ Late"])
                        st.metric("Late", late)
                    with col4:
                        if submission_data:
                            rate = (on_time / len(submission_data)) * 100
                            st.metric("On-Time Rate", f"{rate:.1f}%")
                else:
                    st.info("No submission data available yet.")
            else:
                st.info("No reports found.")
        except Exception as e:
            st.error(f"Error loading submission data: {e}")

    with tab3:
        st.subheader("Email Configuration")
        st.write("Configure email settings for sending UND LEADS summaries.")
        st.info("""
        **Email Setup Instructions:**
        To enable email functionality, you need to configure email settings in your Streamlit secrets.
        **FOR GMAIL (Recommended):**
        1. **Enable 2-Step Verification** on your Gmail account:
           - Go to myaccount.google.com → Security → 2-Step Verification
           - Follow the setup process
        2. **Generate an App Password**:
           - Go to myaccount.google.com → Security → 2-Step Verification → App passwords
           - Select 'Mail' and your device
           - Copy the 16-digit password (e.g., 'abcd efgh ijkl mnop')
        3. **Update your secrets.toml**:
        ```toml
        EMAIL_ADDRESS = 'your-gmail@gmail.com'
        EMAIL_PASSWORD = 'abcd efgh ijkl mnop'  # 16-digit app password
        SMTP_SERVER = 'smtp.gmail.com'
        ```
        **FOR UND/Office 365 Email:**
        ```toml
        EMAIL_ADDRESS = 'your-email@und.edu'
        EMAIL_PASSWORD = 'your-regular-password'
        SMTP_SERVER = 'smtp.office365.com'
        ```
        **IMPORTANT:**
        - Never use your regular Gmail password - only use App Passwords
        - Restart Streamlit after updating secrets.toml
        - Never commit secrets.toml to version control!
        """)
        st.subheader("Test Email Configuration")
        with st.form("test_email"):
            test_email = st.text_input("Send test email to:", placeholder="your-email@und.edu")
            if st.form_submit_button("📧 Send Test Email"):
                if test_email:
                    test_subject = "UND Housing Reports - Email Test"
                    test_body = """This is a test email from the UND Housing Leadership Reports system.\n\nIf you received this email, your email configuration is working correctly!\n\nTest sent at: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with st.spinner("Sending test email..."):
                        success = send_email(test_email, test_subject, test_body)
                        if success:
                            st.success(f"✅ Test email sent successfully to {test_email}")
                        else:
                            st.error("❌ Failed to send test email. Please check your configuration.")
                else:
                    st.error("Please enter an email address for testing.")
        st.subheader("Configuration Status")
        try:
            st.write("🔍 **Debug Information:**")
            current_dir = os.getcwd()
            secrets_path = os.path.join(current_dir, ".streamlit", "secrets.toml")
            st.info(f"**Secrets file location:** `{secrets_path}`")
            st.info(f"**File exists:** {os.path.exists(secrets_path)}")
            try:
                secrets_keys = list(st.secrets.keys()) if hasattr(st.secrets, 'keys') else []
                st.write(f"Available secrets keys: {secrets_keys}")
            except Exception as e:
                st.write(f"Error accessing secrets keys: {e}")
            try:
                email_address = st.secrets["EMAIL_ADDRESS"]
                if email_address.startswith("your-") or "placeholder" in email_address.lower():
                    st.error(f"❌ EMAIL_ADDRESS still contains placeholder: {email_address}")
                    st.warning("Please update your .streamlit/secrets.toml with your real Gmail address")
                else:
                    st.success("✅ Email Address Found")
                    st.text(f"From: {email_address}")
            except KeyError:
                st.error("❌ EMAIL_ADDRESS key not found in secrets")
            except Exception as e:
                st.error(f"❌ Error accessing EMAIL_ADDRESS: {e}")
            try:
                email_password = st.secrets["EMAIL_PASSWORD"]
                if email_password.startswith("your-") or "placeholder" in email_password.lower() or len(email_password) != 16:
                    st.error(f"❌ EMAIL_PASSWORD appears to be placeholder or wrong length (should be 16 chars)")
                    st.warning("Please update your .streamlit/secrets.toml with your real Gmail App Password")
                else:
                    st.success("✅ Email Password Found")
                    st.text("Password: [HIDDEN - 16 characters detected]")
            except KeyError:
                st.error("❌ EMAIL_PASSWORD key not found in secrets")
            except Exception as e:
                st.error(f"❌ Error accessing EMAIL_PASSWORD: {e}")
            try:
                smtp_server = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
                st.success("✅ SMTP Server Available")
                st.text(f"Server: {smtp_server}")
            except Exception as e:
                st.error(f"❌ Error accessing SMTP_SERVER: {e}")
        except Exception as e:
            st.error(f"Error checking configuration: {e}")
        st.subheader("Troubleshooting")
        st.warning("""
        **Common Issues:**
        1. **File Location**: Make sure `.streamlit/secrets.toml` is in your project root directory
        2. **File Format**: Ensure the file uses TOML format with quotes around values
        3. **Restart Required**: Restart Streamlit after modifying secrets.toml
        4. **File Permissions**: Check that the secrets file is readable
        **Example secrets.toml:**
        ```toml
        EMAIL_ADDRESS = "your-email@und.edu"
        EMAIL_PASSWORD = "your-password"
        SMTP_SERVER = "smtp.office365.com"
        ```
        """)
