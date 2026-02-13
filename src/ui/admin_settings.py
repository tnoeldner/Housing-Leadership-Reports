import time
import os
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from src.database import supabase, get_admin_client
from src.utils import get_deadline_settings
from src.email_service import send_email
import streamlit as st

def admin_settings_page():
    if "user" not in st.session_state:
        st.warning("You must be logged in to view this page.")
        st.stop()
    st.title("Administrator Settings")
    st.write("Configure system settings and deadlines.")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📅 Deadline Settings", "📊 Submission Tracking", "📧 Email Configuration", "👥 User Management", "📝 AI Prompt Templates"])
    
    with tab4:
        st.subheader("User Management")
        
        # Admin-only access
        user_role = st.session_state.get('role', 'user')
        if user_role != 'admin':
            st.error("❌ Access Denied: Only admins can manage users.")
            st.stop()
        
        st.write("Manage user roles and permissions.")
        
        # Load all users
        try:
            # Fetch profiles including email (now saves during signup)
            # Use admin client to bypass RLS and get all profiles
            try:
                admin_client = get_admin_client()
                users_response = admin_client.table("profiles").select("id,full_name,title,role,supervisor_id,email").order("full_name").execute()
            except Exception as admin_error:
                st.warning(f"Admin client unavailable, using regular client: {admin_error}")
                users_response = supabase.table("profiles").select("id,full_name,title,role,supervisor_id,email").order("full_name").execute()
            
            users = users_response.data if users_response else []
            
            with st.expander("🔍 Debug: Email Status", expanded=False):
                st.write(f"Loaded {len(users)} profiles")
                
                # Count profiles with email
                users_with_email = [u for u in users if u.get("email")]
                st.write(f"Profiles with email: {len(users_with_email)}")
                
                if users_with_email:
                    st.success("✅ Email sync working - emails are stored in profiles")
                else:
                    st.warning("⚠️ No emails found in profiles - only new signups will have emails")
                    
        except Exception as e:
            st.error(f"Error loading users: {e}")
            users = []
        
        if users:
            st.subheader("Staff Directory")
            
            # Create a dataframe for display
            user_data = []
            for user in users:
                supervisor_id = user.get("supervisor_id")
                supervisor_name = "Not Assigned"
                if supervisor_id:
                    # Find the supervisor's name
                    supervisor = next((u for u in users if u.get("id") == supervisor_id), None)
                    if supervisor:
                        supervisor_name = supervisor.get("full_name", "Unknown")
                
                user_data.append({
                    "Email": user.get("email", ""),
                    "Name": user.get("full_name", ""),
                    "Title": user.get("title", ""),
                    "Role": user.get("role", "user").capitalize(),
                    "Assigned To": supervisor_name,
                })
            
            df = pd.DataFrame(user_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.divider()
            st.subheader("Edit User")
            
            # Get list of staff names for selection
            staff_names = [user.get("full_name", "") for user in users if user.get("full_name")]
            selected_name = st.selectbox("Select Staff Member", options=staff_names, key="user_select")
            
            if selected_name:
                # Find the selected user from already-loaded users
                selected_user = next((u for u in users if u.get("full_name") == selected_name), None)
                
                if selected_user:
                    st.subheader(f"Editing: {selected_name}")
                    
                    # Email field - allow editing
                    current_email = selected_user.get('email', '')
                    new_email = st.text_input(
                        "Email (Login)",
                        value=current_email,
                        key=f"email_{selected_name}",
                        help="Email address for this staff member"
                    )
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        new_role = st.selectbox(
                            "Role",
                            options=["user", "admin"],
                            index=0 if selected_user.get("role", "user") == "user" else 1,
                            key=f"role_{selected_name}"
                        )
                    
                    with col2:
                        new_title = st.text_input(
                            "Title/Position",
                            value=selected_user.get("title", ""),
                            key=f"title_{selected_name}"
                        )
                    
                    st.divider()
                    st.subheader("Assign Supervisor")
                    supervisor_options = ["Not Assigned"] + [u.get("full_name", "") for u in users if u.get("id") != selected_user.get("id")]
                    
                    current_supervisor_id = selected_user.get("supervisor_id")
                    current_supervisor_name = "Not Assigned"
                    if current_supervisor_id:
                        supervisor = next((u for u in users if u.get("id") == current_supervisor_id), None)
                        if supervisor:
                            current_supervisor_name = supervisor.get("full_name", "Not Assigned")
                    
                    selected_supervisor_name = st.selectbox(
                        "Select Supervisor",
                        options=supervisor_options,
                        index=supervisor_options.index(current_supervisor_name) if current_supervisor_name in supervisor_options else 0,
                        key=f"supervisor_{selected_name}"
                    )
                    
                    new_supervisor_id = None
                    if selected_supervisor_name != "Not Assigned":
                        supervisor = next((u for u in users if u.get("full_name") == selected_supervisor_name), None)
                        if supervisor:
                            new_supervisor_id = supervisor.get("id")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("💾 Save Changes", key=f"save_{selected_name}"):
                            try:
                                with st.spinner("Updating user..."):
                                    # Only include fields that should be updated
                                    update_data = {
                                        "role": new_role,
                                        "title": new_title,
                                        "supervisor_id": new_supervisor_id
                                    }
                                    
                                    # Only add email if it was actually entered
                                    if new_email and new_email.strip():
                                        update_data["email"] = new_email
                                    
                                    user_id = selected_user.get("id")
                                    
                                    # Debug output
                                    with st.expander("Debug Info"):
                                        st.write(f"User ID: {user_id}")
                                        st.write(f"Update Data: {update_data}")
                                        st.write(f"Supervisor Name Selected: {selected_supervisor_name}")
                                        st.write(f"Supervisor ID to Save: {new_supervisor_id}")
                                        st.write(f"Email Input Value: '{new_email}'")
                                    
                                    # Use admin client to bypass RLS (admins have this authority)
                                    try:
                                        admin_client = get_admin_client()
                                        result = admin_client.table("profiles").update(update_data).eq("id", user_id).execute()
                                    except Exception as admin_error:
                                        st.warning(f"Admin client failed, trying regular client: {admin_error}")
                                        result = supabase.table("profiles").update(update_data).eq("id", user_id).execute()
                                    
                                    st.write(f"Raw result: {result}")
                                    st.write(f"Result data: {result.data if result else 'None'}")
                                    st.write(f"Result count: {result.count if result else 'None'}")
                                    
                                    if result and result.data and len(result.data) > 0:
                                        st.success(f"✅ User {selected_name} updated! Changes saved to database.")
                                        time.sleep(1)
                                        st.rerun()
                                    elif result:
                                        st.warning(f"Update may have succeeded but returned no data. Result: {result}")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"Update failed - no result returned")
                            except Exception as e:
                                st.error(f"Failed to update user: {str(e)}")
                                import traceback
                                st.error(traceback.format_exc())
                    
                    with col2:
                        email_to_reset = selected_user.get('email', '')
                        if email_to_reset and email_to_reset != "Email not set":
                            if st.button("🔐 Send Password Reset", key=f"reset_{selected_name}"):
                                try:
                                    supabase.auth.admin.send_recovery_email(email=email_to_reset)
                                    st.success(f"✅ Reset email sent to {email_to_reset}")
                                except Exception as e:
                                    st.error(f"Failed to send reset: {e}")
                        else:
                            st.button("🔐 Email Not Available", disabled=True)
        else:
            st.info("No users found in the system.")

    with tab5:
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
        # Duty analysis and staff recognition prompt defaults
        from pathlib import Path
        def load_file_or_default(path, default):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                return default

        default_weekly_duty_prompt = """
You are a senior residence life administrator. Analyze the following weekly duty reports and provide a comprehensive summary for leadership, including key incidents, trends, staff response effectiveness, and recommendations for improvement. Use clear markdown with sections for Executive Summary, Incident Analysis, Operational Insights, Facility & Maintenance, and Recommendations. Include actionable insights and highlight any urgent issues.
{reports_text}
"""
        default_standard_duty_prompt = """
You are a residence life supervisor. Review the following standard duty reports and summarize key events, staff actions, and any policy or safety concerns. Provide a concise summary for the leadership team.
{reports_text}
"""
        default_staff_recognition_prompt = """
You are writing a weekly staff recognition summary. From the following staff reports, identify and highlight outstanding contributions, teamwork, and positive impact. Use a warm, professional tone and format as a list of recognitions with staff names and specific actions.
{reports_text}
"""
        # Rubric defaults from files
        ascend_rubric_path = Path("rubrics-integration/rubrics/ascend_rubric.md")
        north_rubric_path = Path("rubrics-integration/rubrics/north_rubric.md")
        staff_eval_rubric_path = Path("rubrics-integration/rubrics/staff_evaluation_prompt.txt")
        default_ascend_rubric = load_file_or_default(ascend_rubric_path, "ASCEND rubric not found.")
        default_north_rubric = load_file_or_default(north_rubric_path, "NORTH rubric not found.")
        default_staff_eval_rubric = load_file_or_default(staff_eval_rubric_path, "Staff evaluation rubric not found.")
        # Load from DB or use defaults
        def get_setting_or_default(setting_name, default):
            try:
                row = supabase.table("admin_settings").select("setting_value").eq("setting_name", setting_name).single().execute()
                if row.data and row.data.get("setting_value"):
                    return row.data.get("setting_value", default)
            except Exception:
                pass
            return default
        weekly_duty_prompt = get_setting_or_default("weekly_duty_prompt", default_weekly_duty_prompt)
        standard_duty_prompt = get_setting_or_default("standard_duty_prompt", default_standard_duty_prompt)
        staff_recognition_prompt = get_setting_or_default("staff_recognition_prompt", default_staff_recognition_prompt)
        ascend_rubric = get_setting_or_default("ascend_rubric", default_ascend_rubric)
        north_rubric = get_setting_or_default("north_rubric", default_north_rubric)
        staff_eval_rubric = get_setting_or_default("staff_eval_rubric", default_staff_eval_rubric)
        with st.form("ai_prompt_templates_form"):
            dashboard_prompt_edit = st.text_area("Admin Dashboard Summary Prompt", value=dashboard_prompt, height=200)
            individual_prompt_edit = st.text_area("Individual Report Summary Prompt", value=individual_prompt, height=200)
            weekly_duty_prompt_edit = st.text_area("Weekly Duty Analysis Prompt", value=weekly_duty_prompt, height=200)
            standard_duty_prompt_edit = st.text_area("Standard Duty Analysis Prompt", value=standard_duty_prompt, height=200)
            staff_recognition_prompt_edit = st.text_area("Weekly Staff Recognition Prompt", value=staff_recognition_prompt, height=200)
            ascend_rubric_edit = st.text_area("ASCEND Rubric (Markdown)", value=ascend_rubric, height=200)
            north_rubric_edit = st.text_area("NORTH Rubric (Markdown)", value=north_rubric, height=200)
            staff_eval_rubric_edit = st.text_area("Staff Evaluation Rubric/Prompt", value=staff_eval_rubric, height=200)
            if st.form_submit_button("Save AI Prompts & Rubrics", type="primary"):
                admin_user_id = st.session_state["user"].id
                try:
                    with st.spinner("Saving AI prompts and rubrics to database..."):
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
                        supabase.table("admin_settings").upsert({
                            "setting_name": "weekly_duty_prompt",
                            "setting_value": weekly_duty_prompt_edit,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                        supabase.table("admin_settings").upsert({
                            "setting_name": "standard_duty_prompt",
                            "setting_value": standard_duty_prompt_edit,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                        supabase.table("admin_settings").upsert({
                            "setting_name": "staff_recognition_prompt",
                            "setting_value": staff_recognition_prompt_edit,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                        supabase.table("admin_settings").upsert({
                            "setting_name": "ascend_rubric",
                            "setting_value": ascend_rubric_edit,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                        supabase.table("admin_settings").upsert({
                            "setting_name": "north_rubric",
                            "setting_value": north_rubric_edit,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                        supabase.table("admin_settings").upsert({
                            "setting_name": "staff_eval_rubric",
                            "setting_value": staff_eval_rubric_edit,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                    st.success("✅ AI prompt templates and rubrics saved successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save AI prompts or rubrics: {e}")

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
