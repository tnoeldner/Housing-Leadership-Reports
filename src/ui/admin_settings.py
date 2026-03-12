import time
import os
import json
import pandas as pd
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from src.database import supabase, get_admin_client
from src.utils import get_deadline_settings
from src.email_service import send_email
from src.config import ASCEND_VALUES, NORTH_VALUES, CORE_SECTIONS, get_secret
from src.ai import generate_individual_report_summary, call_gemini_ai
import streamlit as st

def admin_settings_page():
    if "user" not in st.session_state:
        st.warning("You must be logged in to view this page.")
        st.stop()
    st.title("Administrator Settings")
    st.write("Configure system settings and deadlines.")
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["📅 Deadline Settings", "📊 Submission Tracking", "📧 Email Configuration", "👥 User Management", "📝 AI Prompt Templates", "📋 Weekly Reports Summary", "📊 Weekly Summary Generator", "💰 AI Usage"])
    
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

    with tab6:
        st.subheader("Weekly Reports Summary")
        st.markdown("""
        View all weekly reports submitted by staff across the organization. Filter by date range and staff member.
        """)
        
        from src.ui.supervisor import weekly_reports_viewer
        # Show all reports for admin (no supervisor filtering)
        weekly_reports_viewer(supervisor_id=None)

    with tab7:
        st.subheader("Generate Weekly Summary for All Staff")
        st.markdown("""
        Generate comprehensive AI-powered weekly summaries for all staff across the organization.
        This summary includes insights from all finalized and draft reports, duty analyses, and engagement data.
        """)
        
        from src.ui.dashboard import dashboard_page
        # Show the admin dashboard summary generation
        dashboard_page(supervisor_mode=False)

        st.divider()
        st.subheader("Reprocess ASCEND/NORTH Categories (Admin)")
        st.markdown("Re-run categorization for finalized reports using the latest ASCEND/NORTH rubrics. This updates stored categories and AI summaries.")

        col_a, col_b = st.columns(2)
        with col_a:
            start_date = st.date_input("Start date", value=datetime.now().date() - timedelta(days=30), key="reprocess_start")
        with col_b:
            end_date = st.date_input("End date", value=datetime.now().date(), key="reprocess_end")

        update_summaries = st.checkbox("Regenerate AI individual summaries", value=True, help="If checked, each report's summary is rebuilt after recategorizing.")

        if st.button("Reprocess ASCEND/NORTH", type="primary"):
            try:
                admin_client = get_admin_client()
            except Exception as e:
                st.error(f"Admin client unavailable: {e}")
                st.stop()

            with st.spinner("Reprocessing reports..."):
                try:
                    resp = admin_client.table("reports") \
                        .select("*") \
                        .eq("status", "finalized") \
                        .gte("week_ending_date", start_date.isoformat()) \
                        .lte("week_ending_date", end_date.isoformat()) \
                        .execute()
                    reports = resp.data or []
                except Exception as e:
                    st.error(f"Failed to fetch reports: {e}")
                    reports = []

                processed = 0
                errors = []

                def parse_ai_json(text):
                    if not text:
                        return None
                    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
                    first_bracket = min([pos for pos in [cleaned.find("[") , cleaned.find("{")] if pos != -1] or [-1])
                    if first_bracket > 0:
                        cleaned = cleaned[first_bracket:]
                    try:
                        return json.loads(cleaned)
                    except Exception:
                        return None

                def load_rubric_text(filename):
                    try:
                        base_dir = Path(__file__).resolve().parents[2] / "rubrics-integration" / "rubrics"
                        rubric_path = base_dir / filename
                        return rubric_path.read_text(encoding="utf-8")
                    except Exception:
                        return ""

                north_rubric = load_rubric_text("north_rubric.md")
                ascend_rubric = load_rubric_text("ascend_rubric.md")

                for report in reports:
                    try:
                        report_body = report.get("report_body") or {}
                        items = []
                        idx = 0
                        for section_key, section_data in (report_body.items() if isinstance(report_body, dict) else []):
                            if not isinstance(section_data, dict):
                                continue
                            for item_type in ["successes", "challenges"]:
                                for entry in section_data.get(item_type, []) or []:
                                    text = entry.get("text", "") if isinstance(entry, dict) else ""
                                    if text:
                                        items.append({
                                            "id": idx,
                                            "text": text,
                                            "section": section_key,
                                            "type": item_type,
                                        })
                                        idx += 1

                        # Build classification prompt
                        default_ascend = "Dedicated & Driven"
                        default_north = "Navigate Needs"
                        prompt = (
                            "Classify each weekly report entry into ASCEND and Guiding NORTH categories. "
                            "Return ONLY JSON as a list of objects with keys id, ascend_category, north_category. "
                            "Use EXACT values from these lists (case-insensitive match is fine): "
                            f"ASCEND = {ASCEND_VALUES}; NORTH = {NORTH_VALUES}. "
                            "Use the following rubrics to decide the best-fit category. Summaries, detailed behaviors, and intent matter more than exact wording. "
                            "ASCEND rubric (for pillar meaning):\n" + ascend_rubric + "\n"
                            "NORTH rubric (for pillar meaning):\n" + north_rubric + "\n"
                            "Items: " + json.dumps(items)
                        )

                        ai_response = call_gemini_ai(
                            prompt,
                            context="admin_reprocess_recategorize",
                        )
                        parsed = parse_ai_json(ai_response)
                        categorized_lookup = {}
                        if isinstance(parsed, list):
                            for entry in parsed:
                                if not isinstance(entry, dict):
                                    continue
                                rid = entry.get("id")
                                # normalize
                                def norm(val, allowed, default):
                                    if not val:
                                        return default
                                    s = str(val).strip()
                                    for opt in allowed:
                                        if s.lower() == opt.lower():
                                            return opt
                                    return default
                                ascend_val = norm(entry.get("ascend_category"), ASCEND_VALUES, default_ascend)
                                north_val = norm(entry.get("north_category"), NORTH_VALUES, default_north)
                                categorized_lookup[rid] = {
                                    "ascend_category": ascend_val,
                                    "north_category": north_val,
                                }

                        # Rebuild report_body with new categories
                        new_body = {k: {"successes": [], "challenges": []} for k in CORE_SECTIONS.keys()}
                        for item in items:
                            cat = categorized_lookup.get(item["id"], {})
                            new_body[item["section"]][item["type"]].append({
                                "text": item["text"],
                                "ascend_category": cat.get("ascend_category", default_ascend),
                                "north_category": cat.get("north_category", default_north),
                            })

                        update_data = {
                            "report_body": new_body,
                        }

                        if update_summaries:
                            # Temporarily set session fields for summary generation
                            backup = {}
                            for key, val in {
                                "full_name": report.get("team_member"),
                                "week_ending_date": report.get("week_ending_date"),
                                "prof_dev": report.get("professional_development", ""),
                                "lookahead": report.get("key_topics_lookahead", ""),
                                "personal_check_in": report.get("personal_check_in", ""),
                                "director_concerns": report.get("director_concerns", ""),
                                "well_being_rating": report.get("well_being_rating", ""),
                            }.items():
                                backup[key] = st.session_state.get(key)
                                st.session_state[key] = val
                            try:
                                indiv_summary = generate_individual_report_summary(items)
                                update_data["individual_summary"] = indiv_summary
                            finally:
                                # restore
                                for k, v in backup.items():
                                    if v is None and k in st.session_state:
                                        del st.session_state[k]
                                    else:
                                        st.session_state[k] = v

                        admin_client.table("reports").update(update_data).eq("id", report.get("id")).execute()
                        processed += 1
                    except Exception as e:
                        errors.append(f"Report {report.get('id')}: {e}")

                st.success(f"Reprocessed {processed} reports between {start_date} and {end_date}.")
                if errors:
                    with st.expander("View errors"):
                        for err in errors:
                            st.error(err)

    with tab8:
        st.subheader("AI Usage & Cost Tracking")
        user_role = st.session_state.get('role', 'user')
        if user_role != 'admin':
            st.error("❌ Access Denied: Only admins can view AI usage.")
            st.stop()

        today = datetime.now().date()
        default_start = today - timedelta(days=14)
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("AI Usage Start", value=default_start, key="ai_usage_start_date_input")
        with col2:
            end_date = st.date_input("AI Usage End", value=today, key="ai_usage_end_date_input")

        # Optional: run BigQuery backfill from the UI
        with st.expander("Sync from BigQuery billing export"):
            # Default from secret/env, cached in session so you don't retype
            default_bq_table = st.session_state.get("bq_table_cached") or get_secret("BQ_BILLING_TABLE") or os.getenv("BQ_BILLING_TABLE", "")
            bq_table = st.text_input("Billing table (project.dataset.table)", value=default_bq_table, key="ai_usage_bq_table", help="Example: gen-lang-client-0478633344.detailed_billing_report.gcp_billing_export_resource_v1_0188A0_7A6E35_DA34CA")
            sync_start = st.date_input("Billing start date", value=start_date, key="ai_usage_bq_start")
            sync_end = st.date_input("Billing end date", value=end_date, key="ai_usage_bq_end")
            if st.button("Run BigQuery sync", type="primary", key="ai_usage_run_bq_sync"):
                if not bq_table:
                    st.error("Please provide a billing export table path.")
                elif sync_start > sync_end:
                    st.error("Start date cannot be after end date for sync.")
                else:
                    with st.spinner("Syncing ai_usage_logs from BigQuery..."):
                        try:
                            import subprocess, sys
                            from pathlib import Path

                            # Resolve script path (repo root/backfill_ai_usage.py)
                            script_path = Path(__file__).resolve().parents[1] / "backfill_ai_usage.py"
                            if not script_path.exists():
                                script_path = Path(__file__).resolve().parents[2] / "backfill_ai_usage.py"

                            # Prepare temp GCP credentials from secrets if provided
                            gcp_sa_json = get_secret("GCP_SERVICE_ACCOUNT") or None
                            env = os.environ.copy()
                            tmp_path = None
                            if gcp_sa_json:
                                tmp_fd, tmp_name = tempfile.mkstemp(prefix="gcp_sa_", suffix=".json")
                                os.close(tmp_fd)
                                with open(tmp_name, "w", encoding="utf-8") as tf:
                                    tf.write(gcp_sa_json)
                                env["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_name
                                tmp_path = tmp_name

                            cmd = [
                                sys.executable,
                                str(script_path),
                                "--bq-table", bq_table,
                                "--start", sync_start.isoformat(),
                                "--end", sync_end.isoformat(),
                            ]
                            st.session_state["bq_table_cached"] = bq_table
                            result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
                            st.success("BigQuery sync completed.")
                            if result.stdout:
                                st.code(result.stdout[-4000:], language="text")
                            if result.stderr:
                                st.info("stderr:")
                                st.code(result.stderr[-2000:], language="text")
                            if tmp_path:
                                try:
                                    os.remove(tmp_path)
                                except Exception:
                                    pass
                        except subprocess.CalledProcessError as e:
                            st.error(f"Sync failed: {e}")
                            st.code((e.stdout or "") + "\n" + (e.stderr or ""), language="text")
                        except Exception as e:
                            st.error(f"Sync failed: {e}")

        if start_date > end_date:
            st.error("Start date cannot be after end date.")
            st.stop()

        try:
            admin_client = get_admin_client()
            end_exclusive = end_date + timedelta(days=1)
            resp = admin_client.table("ai_usage_logs") \
                .select("*") \
                .gte("created_at", start_date.isoformat()) \
                .lt("created_at", end_exclusive.isoformat()) \
                .execute()
            logs = resp.data or []
        except Exception as e:
            st.error(f"Failed to load AI usage logs: {e}")
            logs = []

        if not logs:
            st.info("No AI usage records found for the selected range.")
        else:
            df = pd.DataFrame(logs)
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
            # Localize to America/Chicago for display alongside UTC dates
            local_tz = "America/Chicago"
            try:
                if df["created_at"].dt.tz is None:
                    df["created_local"] = df["created_at"].dt.tz_localize("UTC").dt.tz_convert(local_tz)
                else:
                    df["created_local"] = df["created_at"].dt.tz_convert(local_tz)
            except Exception:
                df["created_local"] = df["created_at"]
            df["date"] = df["created_at"].dt.date
            for col in ["prompt_tokens", "response_tokens", "total_tokens", "cost_usd"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            models = sorted([m for m in df.get("model", pd.Series(dtype=str)).dropna().unique()])
            contexts = sorted([c for c in df.get("context", pd.Series(dtype=str)).dropna().unique()])

            colf1, colf2 = st.columns(2)
            with colf1:
                model_filter = st.multiselect("Filter by model", options=models, default=models)
            with colf2:
                context_filter = st.multiselect("Filter by context", options=contexts, default=contexts)

            search_term = st.text_input("Search in model/context", key="ai_usage_search", placeholder="e.g., weekly_staff_recognition or gemini-2.5-pro")

            filtered = df.copy()
            if model_filter:
                filtered = filtered[filtered["model"].isin(model_filter)]
            if context_filter:
                filtered = filtered[filtered["context"].isin(context_filter)]
            if search_term:
                term = search_term.lower()
                filtered = filtered[
                    filtered["model"].fillna("").str.lower().str.contains(term)
                    | filtered["context"].fillna("").str.lower().str.contains(term)
                ]

            if filtered.empty:
                st.info("No records match the selected filters.")
            else:
                total_cost = filtered["cost_usd"].sum() if "cost_usd" in filtered else 0
                prompt_tokens = filtered["prompt_tokens"].sum() if "prompt_tokens" in filtered else 0
                response_tokens = filtered["response_tokens"].sum() if "response_tokens" in filtered else 0
                total_tokens = filtered["total_tokens"].sum() if "total_tokens" in filtered else 0

                colm1, colm2, colm3 = st.columns(3)
                with colm1:
                    st.metric("Total cost (USD)", f"${total_cost:,.4f}")
                with colm2:
                    st.metric("Prompt tokens", f"{prompt_tokens:,.0f}")
                with colm3:
                    st.metric("Response tokens", f"{response_tokens:,.0f}")

                cost_by_day = filtered.groupby("date").agg(
                    cost_usd=("cost_usd", "sum"),
                    calls=("id", "count") if "id" in filtered.columns else ("cost_usd", "count")
                ).reset_index()
                st.markdown("**Cost by day**")
                st.dataframe(cost_by_day, use_container_width=True, hide_index=True)

                if "model" in filtered.columns:
                    by_model = filtered.groupby("model").agg(
                        cost_usd=("cost_usd", "sum"),
                        calls=("id", "count") if "id" in filtered.columns else ("cost_usd", "count"),
                        prompt_tokens=("prompt_tokens", "sum"),
                        response_tokens=("response_tokens", "sum"),
                        total_tokens=("total_tokens", "sum")
                    ).reset_index()
                    st.markdown("**Cost by model**")
                    st.dataframe(by_model, use_container_width=True, hide_index=True)

                if "context" in filtered.columns:
                    by_context = filtered.groupby("context").agg(
                        cost_usd=("cost_usd", "sum"),
                        calls=("id", "count") if "id" in filtered.columns else ("cost_usd", "count"),
                        prompt_tokens=("prompt_tokens", "sum"),
                        response_tokens=("response_tokens", "sum"),
                        total_tokens=("total_tokens", "sum")
                    ).reset_index()
                    st.markdown("**Cost by context**")
                    st.dataframe(by_context, use_container_width=True, hide_index=True)

                # Raw log table (user-friendly view)
                st.markdown("**Raw usage records**")
                display_cols = [
                    col
                    for col in [
                        "created_local",
                        "model",
                        "context",
                        "user_email",
                        "user_id",
                        "cost_usd",
                        "prompt_tokens",
                        "response_tokens",
                        "total_tokens",
                        "id",
                    ]
                    if col in filtered.columns
                ]
                raw_sorted = filtered.sort_values("created_at", ascending=False)
                st.dataframe(raw_sorted[display_cols], use_container_width=True, hide_index=True)

        # --- Reconciliation: BigQuery vs app logs ---
        with st.expander("Reconcile AI usage vs BigQuery and activity logs"):
            tol = st.number_input("Cost tolerance (USD)", min_value=0.0, value=0.05, step=0.01, key="ai_recon_tol")
            if st.button("Run reconciliation", type="primary", key="ai_usage_reconcile_btn"):
                end_exclusive = end_date + timedelta(days=1)

                # Load app AI usage
                try:
                    admin_client = get_admin_client()
                    resp_ai = admin_client.table("ai_usage_logs") \
                        .select("*") \
                        .gte("created_at", start_date.isoformat()) \
                        .lt("created_at", end_exclusive.isoformat()) \
                        .execute()
                    ai_rows = resp_ai.data or []
                except Exception as e:
                    st.error(f"Failed to load ai_usage_logs for reconciliation: {e}")
                    ai_rows = []

                # Load activity logs (ai_call)
                try:
                    admin_client = get_admin_client()
                    resp_act = admin_client.table("user_activity_logs") \
                        .select("*") \
                        .eq("event_type", "ai_call") \
                        .gte("created_at", start_date.isoformat()) \
                        .lt("created_at", end_exclusive.isoformat()) \
                        .execute()
                    act_rows = resp_act.data or []
                except Exception as e:
                    st.error(f"Failed to load user_activity_logs: {e}")
                    act_rows = []

                # BigQuery daily costs
                bq_rows = []
                bq_error = None
                if not bq_table:
                    bq_error = "Billing table not provided. Set BQ_BILLING_TABLE or fill the input above."
                else:
                    try:
                        from google.cloud import bigquery
                        gcp_sa_json = get_secret("GCP_SERVICE_ACCOUNT") or None
                        tmp_path = None
                        if gcp_sa_json:
                            tmp_fd, tmp_name = tempfile.mkstemp(prefix="gcp_sa_", suffix=".json")
                            os.close(tmp_fd)
                            with open(tmp_name, "w", encoding="utf-8") as tf:
                                tf.write(gcp_sa_json)
                            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_name
                            tmp_path = tmp_name

                        client = bigquery.Client()
                        query = f"""
                            WITH base AS (
                                SELECT DATE(usage_start_time) AS usage_day, cost AS cost_usd
                                FROM `{bq_table}`
                            )
                            SELECT usage_day, SUM(cost_usd) AS cost_usd
                            FROM base
                            WHERE usage_day BETWEEN @start AND @end
                            GROUP BY usage_day
                            ORDER BY usage_day
                        """
                        job = client.query(
                            query,
                            job_config=bigquery.QueryJobConfig(
                                query_parameters=[
                                    bigquery.ScalarQueryParameter("start", "DATE", start_date.isoformat()),
                                    bigquery.ScalarQueryParameter("end", "DATE", end_date.isoformat()),
                                ]
                            ),
                        )
                        bq_rows = [
                            {"date": r.get("usage_day"), "bq_cost_usd": float(r.get("cost_usd", 0.0))}
                            for r in job
                        ]
                    except Exception as e:
                        bq_error = str(e)
                    finally:
                        if tmp_path:
                            try:
                                os.remove(tmp_path)
                            except Exception:
                                pass

                # Build DataFrames
                ai_df = pd.DataFrame(ai_rows)
                act_df = pd.DataFrame(act_rows)
                bq_df = pd.DataFrame(bq_rows)

                if not ai_df.empty:
                    ai_df["created_at"] = pd.to_datetime(ai_df["created_at"], errors="coerce")
                    ai_df["date"] = ai_df["created_at"].dt.date
                if not act_df.empty:
                    act_df["created_at"] = pd.to_datetime(act_df["created_at"], errors="coerce")
                    act_df["date"] = act_df["created_at"].dt.date
                if not bq_df.empty:
                    bq_df["date"] = pd.to_datetime(bq_df["date"], errors="coerce").dt.date
                    if "bq_cost_usd" in bq_df.columns and "cost_usd" not in bq_df.columns:
                        bq_df["cost_usd"] = bq_df["bq_cost_usd"]

                # Show a combined transaction view so every source row is visible
                if ai_df.empty and bq_df.empty:
                    st.info("No AI usage or BigQuery billing rows in this range.")
                else:
                    local_tz = "America/Chicago"

                    app_trans = ai_df.copy()
                    if not app_trans.empty:
                        app_trans["source"] = "app_ai_usage"
                        app_trans["created_at"] = pd.to_datetime(app_trans["created_at"], errors="coerce")
                        try:
                            if app_trans["created_at"].dt.tz is None:
                                app_trans["created_local"] = app_trans["created_at"].dt.tz_localize("UTC").dt.tz_convert(local_tz)
                            else:
                                app_trans["created_local"] = app_trans["created_at"].dt.tz_convert(local_tz)
                        except Exception:
                            app_trans["created_local"] = app_trans["created_at"]
                        app_trans["record_id"] = app_trans["id"] if "id" in app_trans.columns else None
                    else:
                        app_trans = pd.DataFrame(columns=["date", "source", "model", "context", "cost_usd", "prompt_tokens", "response_tokens", "total_tokens", "user_email", "user_id", "created_local", "created_at", "record_id"])

                    bq_trans = pd.DataFrame(columns=["date", "source", "model", "context", "cost_usd", "prompt_tokens", "response_tokens", "total_tokens", "user_email", "user_id", "created_local", "created_at", "record_id"])
                    if not bq_df.empty:
                        bq_trans = bq_df.copy()
                        bq_trans["source"] = "bigquery"
                        bq_trans["model"] = "gemini_billing_export"
                        bq_trans["context"] = "bq_billing_rollup"
                        bq_trans["user_email"] = None
                        bq_trans["user_id"] = None
                        bq_trans["prompt_tokens"] = None
                        bq_trans["response_tokens"] = None
                        bq_trans["total_tokens"] = None
                        bq_trans["record_id"] = None
                        bq_trans["created_at"] = pd.to_datetime(bq_trans["date"], errors="coerce")
                        try:
                            if bq_trans["created_at"].dt.tz is None:
                                bq_trans["created_local"] = bq_trans["created_at"].dt.tz_localize("UTC").dt.tz_convert(local_tz)
                            else:
                                bq_trans["created_local"] = bq_trans["created_at"].dt.tz_convert(local_tz)
                        except Exception:
                            bq_trans["created_local"] = bq_trans["created_at"]
                        if "cost_usd" not in bq_trans.columns:
                            bq_trans["cost_usd"] = 0.0

                    details_cols = [
                        "date",
                        "source",
                        "cost_usd",
                        "model",
                        "context",
                        "user_email",
                        "user_id",
                        "prompt_tokens",
                        "response_tokens",
                        "total_tokens",
                        "created_local",
                        "record_id",
                        "created_at",
                    ]
                    details = pd.concat([app_trans, bq_trans], ignore_index=True)
                    details = details[details_cols]

                    if details.empty:
                        st.info("No reconciliation transactions to display.")
                    else:
                        # Normalize types to avoid pandas categorical sort errors
                        details["created_at"] = pd.to_datetime(details["created_at"], errors="coerce")
                        details["date"] = pd.to_datetime(details["date"], errors="coerce").dt.date
                        details["source"] = details["source"].astype(str)
                        details = details.sort_values(["date", "source", "created_at"], ascending=[False, True, False])

                        st.markdown("**Reconciliation transactions (app AI logs and BigQuery imports)**")
                        display_cols = [
                            "date",
                            "source",
                            "cost_usd",
                            "model",
                            "context",
                            "user_email",
                            "user_id",
                            "created_local",
                            "record_id",
                        ]
                        st.dataframe(details[display_cols], use_container_width=True, hide_index=True)

                # Cost reconciliation (ai_usage_logs vs BigQuery)
                if ai_df.empty:
                    st.warning("No ai_usage_logs in range to reconcile.")
                else:
                    daily_app = ai_df.groupby("date")["cost_usd"].sum().reset_index(name="app_cost_usd")
                    daily_cost = daily_app
                    if not bq_df.empty:
                        daily_cost = daily_app.merge(bq_df, on="date", how="outer").fillna({"app_cost_usd": 0.0, "bq_cost_usd": 0.0})
                    else:
                        daily_cost["bq_cost_usd"] = 0.0
                    daily_cost["delta_usd"] = daily_cost["app_cost_usd"] - daily_cost["bq_cost_usd"]
                    mism = daily_cost[daily_cost["delta_usd"].abs() > tol]
                    st.markdown("**Cost reconciliation (per day)**")
                    st.dataframe(daily_cost.sort_values("date"), use_container_width=True, hide_index=True)
                    if bq_error:
                        st.warning(f"BigQuery not compared: {bq_error}")
                    if mism.empty:
                        st.success(f"No cost mismatches above ${tol:.2f}.")
                    else:
                        st.error(f"Mismatches above ${tol:.2f} (rows below):")
                        st.dataframe(mism.sort_values("date"), use_container_width=True, hide_index=True)

                # Activity reconciliation (ai_usage_logs vs user_activity_logs ai_call)
                if ai_df.empty and act_df.empty:
                    st.warning("No data to reconcile for activity logs.")
                else:
                    app_counts = ai_df.groupby("date")["id" if "id" in ai_df.columns else "cost_usd"].count().reset_index(name="ai_usage_count") if not ai_df.empty else pd.DataFrame(columns=["date", "ai_usage_count"])
                    act_counts = act_df.groupby("date")["id" if "id" in act_df.columns else "event_type"].count().reset_index(name="activity_count") if not act_df.empty else pd.DataFrame(columns=["date", "activity_count"])
                    daily_counts = app_counts.merge(act_counts, on="date", how="outer").fillna({"ai_usage_count": 0, "activity_count": 0})
                    daily_counts["delta_count"] = daily_counts["ai_usage_count"] - daily_counts["activity_count"]
                    st.markdown("**AI call count reconciliation (per day)**")
                    st.dataframe(daily_counts.sort_values("date"), use_container_width=True, hide_index=True)
                    mism_counts = daily_counts[daily_counts["delta_count"] != 0]
                    if mism_counts.empty:
                        st.success("AI usage rows and activity logs align by day.")
                    else:
                        st.error("Mismatched counts (rows below):")
                        st.dataframe(mism_counts.sort_values("date"), use_container_width=True, hide_index=True)

        # --- User Activity Logs ---
        st.markdown("---")
        st.subheader("User Activity Logs (login & AI calls)")
        act_start = st.date_input("Activity Start", value=start_date, key="activity_start")
        act_end = st.date_input("Activity End", value=end_date, key="activity_end")
        # Quick admin debug helper to verify inserts work
        if st.button("Insert test activity (admin)", key="activity_test_insert"):
            try:
                admin_client = get_admin_client()
                test_payload = {
                    "event_type": "debug_test",
                    "context": "admin_settings",
                    "user_email": getattr(st.session_state.get("user"), "email", None) if st.session_state.get("user") else None,
                    "metadata": {"source": "admin test button"},
                }
                resp_test = admin_client.table("user_activity_logs").insert(test_payload).execute()
                new_id = resp_test.data[0]["id"] if resp_test and resp_test.data else "unknown"
                st.success(f"Inserted test activity row (id={new_id}).")
            except Exception as e:
                st.error(f"Test insert failed: {e}")
        if act_start > act_end:
            st.error("Activity start date cannot be after end date.")
        else:
            try:
                admin_client = get_admin_client()
                end_exclusive = act_end + timedelta(days=1)
                resp_act = admin_client.table("user_activity_logs") \
                    .select("*") \
                    .gte("created_at", act_start.isoformat()) \
                    .lt("created_at", end_exclusive.isoformat()) \
                    .order("created_at", desc=True) \
                    .execute()
                acts = resp_act.data or []
            except Exception as e:
                st.error(f"Failed to load activity logs: {e}")
                acts = []

            if not acts:
                st.info("No activity records in the selected range.")
            else:
                adf = pd.DataFrame(acts)
                adf["created_at"] = pd.to_datetime(adf["created_at"], errors="coerce")
                # Show local time (America/Chicago) alongside UTC
                local_tz = "America/Chicago"
                try:
                    if adf["created_at"].dt.tz is None:
                        adf["created_local"] = adf["created_at"].dt.tz_localize("UTC").dt.tz_convert(local_tz)
                    else:
                        adf["created_local"] = adf["created_at"].dt.tz_convert(local_tz)
                except Exception:
                    # If already tz-aware or conversion fails, fall back to created_at
                    adf["created_local"] = adf["created_at"]
                event_types = sorted(adf.get("event_type", pd.Series(dtype=str)).dropna().unique())
                contexts = sorted(adf.get("context", pd.Series(dtype=str)).dropna().unique())

                col_a1, col_a2, col_a3 = st.columns(3)
                with col_a1:
                    ev_filter = st.multiselect("Filter by event", options=event_types, default=event_types)
                with col_a2:
                    ctx_filter = st.multiselect("Filter by context", options=contexts, default=contexts)
                with col_a3:
                    user_search = st.text_input("Search user/email", key="activity_user_search", placeholder="email or part of it")

                af = adf.copy()
                if ev_filter:
                    af = af[af["event_type"].isin(ev_filter)]
                if ctx_filter:
                    af = af[af["context"].isin(ctx_filter)]
                if user_search:
                    term = user_search.lower()
                    af = af[
                        af["user_email"].fillna("").str.lower().str.contains(term)
                        | af["context"].fillna("").str.lower().str.contains(term)
                    ]

                if af.empty:
                    st.info("No activity records match the filters.")
                else:
                    st.markdown("**Activity records**")
                    disp_cols = [c for c in ["created_local", "event_type", "context", "user_email", "user_id", "metadata"] if c in af.columns]
                    st.dataframe(af.sort_values("created_at", ascending=False)[disp_cols], use_container_width=True, hide_index=True)

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
                            # Localize to Chicago for display
                            local_tz = "America/Chicago"
                            if submission_time.tzinfo is None:
                                submission_time_local = submission_time.tz_localize("UTC").tz_convert(local_tz)
                            else:
                                submission_time_local = submission_time.tz_convert(local_tz)
                        else:
                            submission_time = None
                            submission_time_local = None
                    except Exception:
                        submission_time = None
                        submission_time_local = None
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
                    submitted_str = submission_time_local.strftime("%Y-%m-%d %H:%M:%S %Z") if submission_time_local is not None else "Unknown"
                    day_of_week_str = submission_time_local.strftime("%A") if submission_time_local is not None else "Unknown"
                    time_str = submission_time_local.strftime("%H:%M") if submission_time_local is not None else "Unknown"
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
