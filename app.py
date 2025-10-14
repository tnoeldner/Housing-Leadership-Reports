# app.py
import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
from supabase import create_client, Client
import google.generativeai as genai
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        from datetime import timezone
        ZoneInfo = lambda tz: timezone.utc
import time
from collections import Counter

# --- Page Configuration ---
st.set_page_config(page_title="Weekly Impact Report", page_icon="🚀", layout="wide")

# --- Connections ---
@st.cache_resource
def init_connection():
    import os
    
    # Try environment variables first (for deployment), then secrets (for local)
    url = os.getenv("SUPABASE_URL") or st.secrets.get("supabase_url")
    key = os.getenv("SUPABASE_KEY") or st.secrets.get("supabase_key") 
    api_key = os.getenv("GOOGLE_API_KEY") or st.secrets.get("google_api_key")
    
    # Validate required keys exist
    if not url or not key:
        st.error("❌ Missing Supabase configuration. Please check your secrets or environment variables.")
        st.stop()
    
    if not api_key:
        st.error("❌ Missing Google AI API key. Please check your secrets or environment variables.")
        st.stop()
    
    # Test Google AI API key validity
    try:
        genai.configure(api_key=api_key)
        # Quick test to validate the API key works
        test_model = genai.GenerativeModel("models/gemini-2.5-pro")
        # Don't actually call the API, just configure it
    except Exception as e:
        st.error(f"❌ Google AI API key configuration failed: {e}")
        st.info("Please update your Google AI API key in secrets or environment variables.")
        st.stop()
    
    return create_client(url, key)

supabase: Client = init_connection()

# --- CONSTANTS ---
ASCEND_VALUES = ["Accountability", "Service", "Community", "Excellence", "Nurture", "Development", "N/A"]
NORTH_VALUES = ["Nurturing", "Operational", "Resource", "Transformative", "Holistic", "N/A"]
CORE_SECTIONS = {
    "students": "Students/Stakeholders",
    "projects": "Projects",
    "collaborations": "Collaborations",
    "responsibilities": "General Job Responsibilities",
    "staffing": "Staffing/Personnel",
    "kpis": "KPIs",
    "events": "Campus Events/Committees",
}

# --- Helper Functions ---
def get_deadline_settings():
    """Get the current deadline configuration from admin settings"""
    try:
        # Try to get from database first (when table exists)
        settings_response = supabase.table("admin_settings").select("*").eq("setting_name", "report_deadline").execute()
        if settings_response.data:
            # JSONB is already parsed as dict, no need for json.loads
            return settings_response.data[0]["setting_value"]
    except Exception as e:
        # If there's an error, we'll use fallback
        print(f"Database settings error: {e}")  # For debugging
    
    # Check session state for temporary storage
    if "admin_deadline_settings" in st.session_state:
        return st.session_state["admin_deadline_settings"]
    
    # Default settings if nothing is configured
    return {"day_of_week": 0, "hour": 16, "minute": 0, "grace_hours": 16}

def calculate_deadline_info(now):
    """Calculate deadline information based on current time and settings"""
    deadline_config = get_deadline_settings()
    
    deadline_day = deadline_config["day_of_week"]  # 0 = Monday
    deadline_hour = deadline_config["hour"]
    deadline_minute = deadline_config["minute"]
    grace_hours = deadline_config["grace_hours"]
    
    # Handle both datetime objects and string dates
    if isinstance(now, str):
        # If it's a string date, convert to datetime and use current time as reference
        try:
            week_ending_date = datetime.strptime(now, "%Y-%m-%d").date()
            # Use current time for comparison
            current_time = datetime.now(ZoneInfo("America/Chicago"))
            current_weekday = current_time.weekday()
            
            # Calculate deadline for the specific week
            deadline_date = week_ending_date + timedelta(days=(deadline_day - 5) % 7 + (1 if deadline_day <= 5 else 0))
            deadline_datetime = datetime.combine(deadline_date, datetime.min.time().replace(hour=deadline_hour, minute=deadline_minute)).replace(tzinfo=ZoneInfo("America/Chicago"))
            grace_end_datetime = deadline_datetime + timedelta(hours=grace_hours)
            
            # Check if deadline has passed
            deadline_passed = current_time > deadline_datetime
            in_grace_period = current_time <= grace_end_datetime and current_time > deadline_datetime
            
            return {
                "active_saturday": week_ending_date,
                "deadline": deadline_datetime,
                "grace_end": grace_end_datetime,
                "deadline_passed": deadline_passed,
                "in_grace_period": in_grace_period
            }
        except ValueError:
            # If string parsing fails, fall back to current time
            now = datetime.now(ZoneInfo("America/Chicago"))
    
    # Calculate the active week ending Saturday and deadline
    current_weekday = now.weekday()  # Monday is 0, Sunday is 6
    
    # Find the active Saturday (end of reporting week)
    if current_weekday < deadline_day or (current_weekday == deadline_day and now.hour < deadline_hour + grace_hours):
        # Still in current reporting week
        days_to_saturday = 5 - current_weekday
        active_saturday = now.date() + timedelta(days=days_to_saturday)
    else:
        # Move to next reporting week
        days_to_next_saturday = (5 - current_weekday) + 7
        active_saturday = now.date() + timedelta(days=days_to_next_saturday)
    
    # Calculate actual deadline (day after Saturday at specified time)
    deadline_date = active_saturday + timedelta(days=(deadline_day - 5) % 7 + (1 if deadline_day <= 5 else 0))
    deadline_datetime = datetime.combine(deadline_date, datetime.min.time().replace(hour=deadline_hour, minute=deadline_minute))
    deadline_datetime = deadline_datetime.replace(tzinfo=ZoneInfo("America/Chicago"))
    
    # Grace period end
    grace_end = deadline_datetime + timedelta(hours=grace_hours)
    
    # Check status
    is_grace_period = deadline_datetime <= now <= grace_end
    deadline_passed = now > grace_end
    
    return {
        "active_saturday": active_saturday,
        "deadline_datetime": deadline_datetime,
        "grace_end": grace_end,
        "is_grace_period": is_grace_period,
        "deadline_passed": deadline_passed,
        "config": deadline_config
    }

def clear_form_state():
    keys_to_clear = ["draft_report", "report_to_edit", "last_summary", "events_count"]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    for section_key in CORE_SECTIONS.keys():
        if f"{section_key}_success_count" in st.session_state:
            del st.session_state[f"{section_key}_success_count"]
        if f"{section_key}_challenge_count" in st.session_state:
            del st.session_state[f"{section_key}_challenge_count"]
    
    # Clear event-related session state
    events_to_clear = [key for key in st.session_state.keys() if key.startswith("event_name_") or key.startswith("event_date_")]
    for key in events_to_clear:
        del st.session_state[key]

# --- User Authentication & Profile Functions ---
def login_form():
    st.header("Login")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        if submit:
            try:
                user_session = supabase.auth.sign_in_with_password({"email": email, "password": password})
                if getattr(user_session, "user", None):
                    st.session_state["user"] = user_session.user
                    st.rerun()
                else:
                    st.error("Login failed. Please check your credentials.")
            except Exception:
                st.error("Login failed: Invalid login credentials or unconfirmed email.")


def signup_form():
    st.header("Create a New Account")
    with st.form("signup"):
        email = st.text_input("Email")
        full_name = st.text_input("Full Name")
        title = st.text_input("Position Title")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Create Account")
        if submit:
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})
                if getattr(res, "user", None):
                    new_user_id = res.user.id
                    supabase.table("profiles").update({"full_name": full_name, "title": title}).eq("id", new_user_id).execute()
                    st.success("Signup successful! Please check your email to confirm your account.")
                else:
                    st.error("Signup failed. A user may already exist with this email.")
            except Exception as e:
                if "already registered" in str(e):
                    st.error("This email address is already registered. Please try logging in.")
                else:
                    st.error(f"An error occurred during signup: {e}")


def logout():
    keys_to_delete = ["user", "role", "title", "full_name", "last_summary", "report_to_edit", "draft_report", "is_supervisor"]
    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key]
    clear_form_state()

# --- Page Definitions ---
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


def submit_and_edit_page():
    st.title("Submit / Edit Report")

    def show_report_list():
        st.subheader("Your Submitted Reports")
        user_id = st.session_state["user"].id
        user_reports_response = supabase.table("reports").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        user_reports = getattr(user_reports_response, "data", None) or []
        
        # Check for any draft reports that were previously finalized (unlocked by admin)
        unlocked_reports = [r for r in user_reports if r.get("status") == "draft" and r.get("individual_summary")]
        admin_created_reports = [r for r in user_reports if r.get("status") == "admin_created"]
        
        if unlocked_reports:
            st.info(f"📢 **Notice:** {len(unlocked_reports)} of your previously submitted reports have been unlocked by an administrator for editing. You can now make changes and resubmit them.")
        
        if admin_created_reports:
            st.warning(f"⏰ **Missed Deadline:** {len(admin_created_reports)} report(s) were created by an administrator because you missed the deadline. Please complete and submit them as soon as possible.")

        now = datetime.now(ZoneInfo("America/Chicago"))
        deadline_info = calculate_deadline_info(now)
        
        active_saturday = deadline_info["active_saturday"]
        is_grace_period = deadline_info["is_grace_period"]
        deadline_is_past = deadline_info["deadline_passed"]
        deadline_config = deadline_info["config"]

        if active_saturday:
            active_report_date_str = active_saturday.strftime("%Y-%m-%d")
            has_finalized_for_active_week = any(
                report.get("week_ending_date") == active_report_date_str and report.get("status") == "finalized" for report in user_reports
            )
            
            # Check if user has an unlocked report for this week (admin-enabled submission)
            has_unlocked_for_active_week = any(
                report.get("week_ending_date") == active_report_date_str and report.get("status") == "unlocked" for report in user_reports
            )

            show_create_button = True
            if has_finalized_for_active_week:
                show_create_button = False
            elif is_grace_period and deadline_is_past:
                show_create_button = False
            elif deadline_is_past and not has_unlocked_for_active_week:
                show_create_button = False

            if show_create_button:
                # Show deadline information
                deadline_day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][deadline_config["day_of_week"]]
                if has_unlocked_for_active_week:
                    st.success(f"✅ Your report has been unlocked by an administrator. You can now edit and submit despite the missed deadline.")
                    button_label = f"📝 Edit Unlocked Report for week ending {active_saturday.strftime('%m/%d/%Y')}"
                elif is_grace_period:
                    st.info(f"⏰ You are in the grace period. Original deadline was {deadline_day_name} at {deadline_config['hour']:02d}:{deadline_config['minute']:02d}. Grace period ends {deadline_info['grace_end'].strftime('%A at %H:%M')}.")
                    button_label = f"📝 Create or Edit Report for week ending {active_saturday.strftime('%m/%d/%Y')}"
                else:
                    st.info(f"📅 Reports for week ending {active_saturday.strftime('%m/%d/%Y')} are due {deadline_day_name} at {deadline_config['hour']:02d}:{deadline_config['minute']:02d}")
                    button_label = f"📝 Create or Edit Report for week ending {active_saturday.strftime('%m/%d/%Y')}"
                if st.button(button_label, use_container_width=True, type="primary"):
                    clear_form_state()
                    existing_report = next((r for r in user_reports if r.get("week_ending_date") == active_report_date_str), None)
                    st.session_state["report_to_edit"] = existing_report if existing_report else {"week_ending_date": active_report_date_str}
                    st.rerun()
            elif has_finalized_for_active_week:
                st.info(f"You have already finalized your report for the week ending {active_saturday.strftime('%m/%d/%Y')}.")
            elif deadline_is_past:
                deadline_day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][deadline_config["day_of_week"]]
                st.warning(f"The submission deadline ({deadline_day_name} at {deadline_config['hour']:02d}:{deadline_config['minute']:02d}) for the report ending {active_saturday.strftime('%m/%d/%Y')} has passed. Contact your administrator if you need to submit a report.")

        st.divider()
        if not user_reports:
            st.info("You have not submitted any other reports yet.")
            return

        st.markdown("##### All My Reports")
        for report in user_reports:
            status = (report.get("status") or "draft").capitalize()
            with st.expander(f"Report for week ending {report.get('week_ending_date','Unknown')} (Status: {status})"):
                if report.get("individual_summary"):
                    st.info(f"**Your AI-Generated Summary:**\n\n{report.get('individual_summary')}")
                report_body = report.get("report_body") or {}
                for section_key, section_name in CORE_SECTIONS.items():
                    section_data = report_body.get(section_key)
                    if section_data and (section_data.get("successes") or section_data.get("challenges")):
                        st.markdown(f"#### {section_name}")
                        if section_data.get("successes"):
                            st.markdown("**Successes:**")
                            for s in section_data["successes"]:
                                st.markdown(
                                    f"- {s.get('text','')} `(ASCEND: {s.get('ascend_category','N/A')}, NORTH: {s.get('north_category','N/A')})`"
                                )
                        if section_data.get("challenges"):
                            st.markdown("**Challenges:**")
                            for c in section_data["challenges"]:
                                st.markdown(
                                    f"- {c.get('text','')} `(ASCEND: {c.get('ascend_category','N/A')}, NORTH: {c.get('north_category','N/A')})`"
                                )
                        st.markdown("---")

                st.markdown("#### General Updates")
                st.markdown("**Professional Development:**")
                st.write(report.get("professional_development", ""))
                st.markdown("**Lookahead:**")
                st.write(report.get("key_topics_lookahead", ""))
                st.markdown("**Personal Check-in Details:**")
                st.write(report.get("personal_check_in", ""))
                # Only show Director concerns to admins or the report owner
                if report.get('director_concerns'):
                    viewer_role = st.session_state.get('role')
                    viewer_id = st.session_state['user'].id
                    report_owner_id = report.get('user_id')
                    if viewer_role == 'admin' or report_owner_id == viewer_id:
                        st.warning(f"**Concerns for Director:** {report.get('director_concerns')}")

                if status.lower() != "finalized":
                    if st.button("Edit This Report", key=f"edit_{report.get('id')}", use_container_width=True):
                        st.session_state["report_to_edit"] = report
                        st.rerun()

    @st.cache_data
    def process_report_with_ai(items_to_categorize):
        if not items_to_categorize:
            return None
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        ascend_list = ", ".join(ASCEND_VALUES)
        north_list = ", ".join(NORTH_VALUES)
        items_json = json.dumps(items_to_categorize)
        prompt = f"""
        You are an expert AI assistant for a university housing department. Your task is to perform two actions on a list of weekly activities including campus events and committee participation:
        1. Categorize each activity with one ASCEND and one Guiding NORTH category.
        2. Generate a concise 2-4 sentence individual summary that includes mention of campus engagement and its alignment with frameworks.
        
        ASCEND Categories: {ascend_list}
        Guiding NORTH Categories: {north_list}

        For campus events/committee participation, consider how attendance demonstrates:
        - Community engagement and service (Community, Service)
        - Professional development and learning (Development, Excellence)
        - Supporting university initiatives (Accountability, Nurturing)
        - Building relationships with stakeholders (Service, Transformative)

        Also consider UND LEADS alignment in your summary:
        - Learning: Training, workshops, skill development, educational activities
        - Equity: Diversity events, inclusion initiatives, accessibility work
        - Affinity: Networking, relationship building, team activities, community engagement
        - Discovery: Innovation projects, research, exploring new methods, creative solutions
        - Service: Volunteer work, helping others, community service, supporting university goals

        Input JSON: {items_json}

        Return valid JSON like:
        {{
          "categorized_items":[{{"id":0,"ascend_category":"Community","north_category":"Nurturing Student Success & Development"}}],
          "individual_summary":"This week showed strong alignment with both ASCEND and NORTH frameworks through various activities and campus engagement. The work also demonstrates UND LEADS values through learning opportunities and service to the community..."
        }}
        """
        try:
            response = model.generate_content(prompt)
            clean_response = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(clean_response)
        except Exception as e:
            st.error(f"An AI error occurred during processing: {e}")
            return None

    def dynamic_entry_section(section_key, section_label, report_data):
        st.subheader(section_label)
        
        # Special handling for events section
        if section_key == "events":
            # Initialize events count if not exists
            if "events_count" not in st.session_state:
                existing_events = report_data.get("events", {}).get("successes", [])
                st.session_state["events_count"] = len(existing_events) if existing_events else 1
            
            # Display event entry fields
            for i in range(st.session_state["events_count"]):
                col1, col2 = st.columns([2, 1])
                default_event_name = ""
                default_event_date = datetime.now().date()
                
                # Load existing event data if editing - parse from text format
                existing_events = report_data.get("events", {}).get("successes", [])
                if i < len(existing_events):
                    event_text = existing_events[i].get("text", "")
                    # Try to parse "EventName on YYYY-MM-DD" format
                    if " on " in event_text:
                        parts = event_text.rsplit(" on ", 1)
                        if len(parts) == 2:
                            default_event_name = parts[0]
                            try:
                                default_event_date = pd.to_datetime(parts[1]).date()
                            except:
                                default_event_date = datetime.now().date()
                    else:
                        default_event_name = event_text
                
                with col1:
                    st.text_input(f"Event/Committee Name", value=default_event_name, key=f"event_name_{i}", placeholder="Enter event or committee name")
                with col2:
                    st.date_input(f"Event Date", value=default_event_date, key=f"event_date_{i}")
        else:
            # Regular successes/challenges format for other sections
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("##### Successes")
                s_key = f"{section_key}_success_count"
                if s_key not in st.session_state:
                    st.session_state[s_key] = len(report_data.get(section_key, {}).get("successes", [])) or 1
                for i in range(st.session_state[s_key]):
                    default = (
                        report_data.get(section_key, {}).get("successes", [{}])[i].get("text", "")
                        if i < len(report_data.get(section_key, {}).get("successes", []))
                        else ""
                    )
                    st.text_area("Success", value=default, key=f"{section_key}_success_{i}", label_visibility="collapsed", placeholder=f"Success #{i+1}")
            with col2:
                st.markdown("##### Challenges")
                c_key = f"{section_key}_challenge_count"
                if c_key not in st.session_state:
                    st.session_state[c_key] = len(report_data.get(section_key, {}).get("challenges", [])) or 1
                for i in range(st.session_state[c_key]):
                    default = (
                        report_data.get(section_key, {}).get("challenges", [{}])[i].get("text", "")
                        if i < len(report_data.get(section_key, {}).get("challenges", []))
                        else ""
                    )
                    st.text_area("Challenge", value=default, key=f"{section_key}_challenge_{i}", label_visibility="collapsed", placeholder=f"Challenge #{i+1}")

    def show_submission_form():
        report_data = st.session_state["report_to_edit"]
        is_new_report = not bool(report_data.get("id"))
        st.subheader("Editing Report" if not is_new_report else "Creating New Report")
        with st.form(key="weekly_report_form"):
            col1, col2 = st.columns(2)
            with col1:
                team_member_name = st.session_state.get("full_name") or st.session_state.get("title") or st.session_state["user"].email
                st.text_input("Submitted By", value=team_member_name, disabled=True)
            with col2:
                default_date = pd.to_datetime(report_data.get("week_ending_date")).date()
                week_ending_date = st.date_input("For the Week Ending", value=default_date, format="MM/DD/YYYY")
            st.divider()
            core_activities_tab, general_updates_tab = st.tabs(["📊 Core Activities", "📝 General Updates"])
            with core_activities_tab:
                core_tab_list = st.tabs(list(CORE_SECTIONS.values()))
                add_buttons = {}
                for i, (section_key, section_name) in enumerate(CORE_SECTIONS.items()):
                    with core_tab_list[i]:
                        dynamic_entry_section(section_key, section_name, report_data.get("report_body", {}))
                        if section_key == "events":
                            # Special handling for events - just one add button
                            add_buttons[f"add_event"] = st.form_submit_button("Add Event/Committee ➕", key=f"add_event")
                        else:
                            # Regular success/challenge buttons for other sections
                            b1, b2 = st.columns(2)
                            add_buttons[f"add_success_{section_key}"] = b1.form_submit_button("Add Success ➕", key=f"add_s_{section_key}")
                            add_buttons[f"add_challenge_{section_key}"] = b2.form_submit_button("Add Challenge ➕", key=f"add_c_{section_key}")
            with general_updates_tab:
                st.subheader("General Updates & Well-being")
                st.markdown("**Personal Well-being Check-in**")
                well_being_rating = st.radio(
                    "How are you doing this week?",
                    options=[1, 2, 3, 4, 5],
                    captions=["Struggling", "Tough Week", "Okay", "Good Week", "Thriving"],
                    horizontal=True,
                    index=(report_data.get("well_being_rating", 3) - 1) if not is_new_report else 2,
                )
                st.text_area("Personal Check-in Details (Optional)", value=report_data.get("personal_check_in", ""), key="personal_check_in", height=100)
                st.divider()
                st.subheader("Other Updates")
                st.text_area("Needs or Concerns for Director", value=report_data.get("director_concerns", ""), key="director_concerns", height=150)
                st.text_area("Professional Development", value=report_data.get("professional_development", ""), key="prof_dev", height=150)
                st.text_area("Key Topics & Lookahead", value=report_data.get("key_topics_lookahead", ""), key="lookahead", height=150)

            st.divider()
            col1, col2, col3 = st.columns([2, 2, 1])
            save_draft_button = col1.form_submit_button("Save Draft", use_container_width=True)
            review_button = col2.form_submit_button("Proceed to Review & Finalize", type="primary", use_container_width=True)

        if st.button("Cancel"):
            clear_form_state()
            st.rerun()

        clicked_button = None
        for key, value in add_buttons.items():
            if value:
                clicked_button = key
                break
        if clicked_button:
            if clicked_button == "add_event":
                # Handle add event button
                if "events_count" not in st.session_state:
                    st.session_state["events_count"] = 1
                st.session_state["events_count"] += 1
                st.rerun()
            else:
                # Handle regular success/challenge buttons
                parts = clicked_button.split("_")
                section, category = parts[2], parts[1]
                counter_key = f"{section}_{category}_count"
                if counter_key not in st.session_state:
                    st.session_state[counter_key] = 1
                st.session_state[counter_key] += 1
                st.rerun()

        elif save_draft_button:
            with st.spinner("Saving draft..."):
                report_body = {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()}
                for section_key in CORE_SECTIONS.keys():
                    success_texts = [
                        st.session_state.get(f"{section_key}_success_{i}") for i in range(st.session_state.get(f"{section_key}_success_count", 1))
                        if st.session_state.get(f"{section_key}_success_{i}")
                    ]
                    challenge_texts = [
                        st.session_state.get(f"{section_key}_challenge_{i}") for i in range(st.session_state.get(f"{section_key}_challenge_count", 1))
                        if st.session_state.get(f"{section_key}_challenge_{i}")
                    ]
                    if section_key == "events":
                        # Handle events section differently
                        event_entries = []
                        events_count = st.session_state.get("events_count", 1)
                        for i in range(events_count):
                            event_name = st.session_state.get(f"event_name_{i}", "")
                            event_date = st.session_state.get(f"event_date_{i}")
                            if event_name and event_date:
                                event_entries.append({"text": f"{event_name} on {event_date}"})
                        report_body[section_key]["successes"] = event_entries
                        report_body[section_key]["challenges"] = []
                    else:
                        # Handle regular sections
                        report_body[section_key]["successes"] = [{"text": t} for t in success_texts]
                        report_body[section_key]["challenges"] = [{"text": t} for t in challenge_texts]

                draft_data = {
                    "user_id": st.session_state["user"].id,
                    "team_member": team_member_name,
                    "week_ending_date": str(week_ending_date),
                    "report_body": report_body,
                    "professional_development": st.session_state.get("prof_dev", ""),
                    "key_topics_lookahead": st.session_state.get("lookahead", ""),
                    "personal_check_in": st.session_state.get("personal_check_in", ""),
                    "well_being_rating": well_being_rating,
                    "director_concerns": st.session_state.get("director_concerns", ""),
                    "status": "draft",
                }
                try:
                    supabase.table("reports").upsert(draft_data, on_conflict="user_id, week_ending_date").execute()
                    st.success("Draft saved successfully!")
                    clear_form_state()
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"An error occurred while saving the draft: {e}")

        elif review_button:
            with st.spinner("Generating AI draft..."):
                items_to_process = []
                item_id_counter = 0
                for section_key in CORE_SECTIONS.keys():
                    if section_key == "events":
                        # Handle events section
                        events_count = st.session_state.get("events_count", 1)
                        for i in range(events_count):
                            event_name = st.session_state.get(f"event_name_{i}", "")
                            event_date = st.session_state.get(f"event_date_{i}")
                            if event_name and event_date:
                                items_to_process.append({
                                    "id": item_id_counter, 
                                    "text": f"Attended campus event/committee: {event_name} on {event_date}", 
                                    "section": section_key, 
                                    "type": "successes"
                                })
                                item_id_counter += 1
                    else:
                        # Handle regular sections
                        for i in range(st.session_state.get(f"{section_key}_success_count", 1)):
                            text = st.session_state.get(f"{section_key}_success_{i}")
                            if text:
                                items_to_process.append({"id": item_id_counter, "text": text, "section": section_key, "type": "successes"})
                                item_id_counter += 1
                        for i in range(st.session_state.get(f"{section_key}_challenge_count", 1)):
                            text = st.session_state.get(f"{section_key}_challenge_{i}")
                            if text:
                                items_to_process.append({"id": item_id_counter, "text": text, "section": section_key, "type": "challenges"})
                                item_id_counter += 1
                


                ai_results = process_report_with_ai(items_to_process)

                if ai_results and "categorized_items" in ai_results and "individual_summary" in ai_results and len(
                    ai_results["categorized_items"]
                ) == len(items_to_process):
                    categorized_lookup = {item["id"]: item for item in ai_results["categorized_items"]}
                    report_body = {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()}
                    
                    for item in items_to_process:
                        item_id = item["id"]
                        categories = categorized_lookup.get(item_id, {})
                        categorized_item = {
                            "text": item["text"],
                            "ascend_category": categories.get("ascend_category", "N/A"),
                            "north_category": categories.get("north_category", "N/A"),
                        }
                        report_body[item["section"]][item["type"]].append(categorized_item)

                    st.session_state["draft_report"] = {
                        "report_id": report_data.get("id"),
                        "team_member_name": team_member_name,
                        "week_ending_date": str(week_ending_date),
                        "report_body": report_body,
                        "professional_development": st.session_state.get("prof_dev", ""),
                        "key_topics_lookahead": st.session_state.get("lookahead", ""),
                        "personal_check_in": st.session_state.get("personal_check_in", ""),
                        "well_being_rating": well_being_rating,
                        "individual_summary": ai_results["individual_summary"],
                        "director_concerns": st.session_state.get("director_concerns", ""),
                    }
                    st.rerun()
                else:
                    st.error("The AI failed to process the report consistently. Please check your entries and try again.")

    def show_review_form():
        st.subheader("Review Your AI-Generated Report")
        st.info("The AI has categorized your entries and generated a summary. Please review, edit if necessary, and then finalize your submission.")
        draft = st.session_state["draft_report"]

        rating = draft.get("well_being_rating")
        if rating:
            st.metric("Your Well-being Score for this Week:", f"{rating}/5")
        st.markdown("---")

        with st.form("review_form"):
            st.markdown(f"**Report for:** {draft.get('team_member_name','Unknown')} | **Week Ending:** {draft.get('week_ending_date','Unknown')}")
            st.divider()
            st.markdown("### General Updates & Well-being (Review)")
            st.radio(
                "How are you doing this week?",
                options=[1, 2, 3, 4, 5],
                captions=["Struggling", "Tough Week", "Okay", "Good Week", "Thriving"],
                horizontal=True,
                index=max(0, (draft.get("well_being_rating") or 3) - 1),
                key="review_well_being",
            )
            st.text_area("Personal Check-in Details (Optional)", value=draft.get("personal_check_in", ""), key="review_personal_check_in", height=100)
            st.divider()
            st.text_area("Needs or Concerns for Director", value=draft.get("director_concerns", ""), key="review_director_concerns", height=150)
            st.text_area("Professional Development", value=draft.get("professional_development", ""), key="review_prof_dev", height=150)
            st.text_area("Key Topics & Lookahead", value=draft.get("key_topics_lookahead", ""), key="review_lookahead", height=150)
            st.divider()

            for section_key, section_name in CORE_SECTIONS.items():
                section_data = draft.get("report_body", {}).get(section_key, {})
                if section_data and (section_data.get("successes") or section_data.get("challenges")):
                    st.markdown(f"#### {section_name}")
                    for item_type in ["successes", "challenges"]:
                        if section_data.get(item_type):
                            st.markdown(f"**{item_type.capitalize()}:**")
                            for i, item in enumerate(section_data[item_type]):
                                st.markdown(f"> {item.get('text','')}")
                                col1, col2 = st.columns(2)
                                ascend_index = ASCEND_VALUES.index(item.get("ascend_category")) if item.get("ascend_category") in ASCEND_VALUES else len(ASCEND_VALUES) - 1
                                north_index = NORTH_VALUES.index(item.get("north_category")) if item.get("north_category") in NORTH_VALUES else len(NORTH_VALUES) - 1
                                col1.selectbox("ASCEND Category", options=ASCEND_VALUES, index=ascend_index, key=f"review_{section_key}_{item_type}_{i}_ascend")
                                col2.selectbox("Guiding NORTH Category", options=NORTH_VALUES, index=north_index, key=f"review_{section_key}_{item_type}_{i}_north")
            st.divider()
            st.subheader("Editable Individual Summary")
            st.text_area("AI-Generated Summary", value=draft.get("individual_summary", ""), key="review_summary", height=150)
            st.divider()
            col1, col2 = st.columns([3, 1])
            with col2:
                finalize_button = st.form_submit_button("Lock and Submit Report", type="primary", use_container_width=True)

        if st.button("Go Back to Edit"):
            st.session_state["report_to_edit"] = {
                "id": draft.get("report_id"),
                "team_member": draft.get("team_member_name"),
                "week_ending_date": draft.get("week_ending_date"),
                "report_body": draft.get("report_body"),
                "professional_development": st.session_state.get("review_prof_dev", ""),
                "key_topics_lookahead": st.session_state.get("review_lookahead", ""),
                "personal_check_in": st.session_state.get("review_personal_check_in", ""),
                "well_being_rating": st.session_state.get("review_well_being", 3),
                "director_concerns": st.session_state.get("review_director_concerns", ""),
            }
            if "draft_report" in st.session_state:
                del st.session_state["draft_report"]
            st.rerun()

        if finalize_button:
            with st.spinner("Finalizing and saving your report..."):
                final_report_body = {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()}
                original_body = draft.get("report_body", {})
                for section_key in CORE_SECTIONS.keys():
                    for item_type in ["successes", "challenges"]:
                        for i, item in enumerate(original_body.get(section_key, {}).get(item_type, [])):
                            final_item = {
                                "text": item.get("text", ""),
                                "ascend_category": st.session_state.get(f"review_{section_key}_{item_type}_{i}_ascend", "N/A"),
                                "north_category": st.session_state.get(f"review_{section_key}_{item_type}_{i}_north", "N/A"),
                            }
                            final_report_body[section_key][item_type].append(final_item)

                final_data = {
                    "user_id": st.session_state["user"].id,
                    "team_member": draft.get("team_member_name"),
                    "week_ending_date": draft.get("week_ending_date"),
                    "report_body": final_report_body,
                    "professional_development": st.session_state.get("review_prof_dev", ""),
                    "key_topics_lookahead": st.session_state.get("lookahead", ""),
                    "personal_check_in": st.session_state.get("review_personal_check_in", ""),
                    "well_being_rating": st.session_state.get("review_well_being", 3),
                    "individual_summary": st.session_state.get("review_summary", ""),
                    "director_concerns": st.session_state.get("review_director_concerns", ""),
                    "status": "finalized",
                    "submitted_at": datetime.now(ZoneInfo("America/Chicago")).isoformat(),
                }

                try:
                    supabase.table("reports").upsert(final_data, on_conflict="user_id, week_ending_date").execute()
                    st.success("✅ Your final report has been saved successfully!")
                    is_update = bool(draft.get("report_id"))
                    if is_update:
                        supabase.table("weekly_summaries").delete().eq("week_ending_date", draft.get("week_ending_date")).execute()
                        st.warning(f"Note: The saved team summary for {draft.get('week_ending_date')} has been deleted. An admin will need to regenerate it.")
                    clear_form_state()
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"An error occurred while saving the final report: {e}")

    if "draft_report" in st.session_state:
        show_review_form()
    elif "report_to_edit" in st.session_state:
        show_submission_form()
    else:
        show_report_list()


def dashboard_page(supervisor_mode=False):
    # Ensure we always have the current user's id available (used for RPC/save logic)
    current_user_id = st.session_state['user'].id

    if supervisor_mode:
        st.title("Supervisor Dashboard")
        st.write("View your team's reports, track submissions, and generate weekly summaries.")

        # Get the direct reports (defensive)
        direct_reports_response = supabase.table("profiles").select("id, full_name, title").eq("supervisor_id", current_user_id).execute()
        direct_reports = getattr(direct_reports_response, "data", None) or []
        direct_report_ids = [u.get("id") for u in direct_reports if u.get("id")]

        st.caption(f"Found {len(direct_report_ids)} direct report(s).")
        if direct_reports:
            names = ", ".join([dr.get("full_name") or dr.get("title") or dr.get("id") for dr in direct_reports])
            st.write("Direct reports:", names)

        if not direct_report_ids:
            st.info("You do not have any direct reports assigned in the system.")
            return

        # Use RPC to fetch finalized reports for this supervisor (works with RLS)
        rpc_resp = supabase.rpc('get_finalized_reports_for_supervisor', {'sup_id': current_user_id}).execute()
        all_reports = rpc_resp.data or []

        st.caption(f"Found {len(all_reports)} finalized report(s) for your direct reports.")

        # Get staff records for display (only the supervisor's direct reports)
        all_staff_response = supabase.table('profiles').select('*').in_('id', direct_report_ids).execute()
        all_staff = getattr(all_staff_response, "data", None) or []

    else:
        st.title("Admin Dashboard")
        st.write("View reports, track submissions, and generate weekly summaries.")
        reports_response = supabase.table("reports").select("*").eq("status", "finalized").order("created_at", desc=True).execute()
        all_reports = getattr(reports_response, "data", None) or []
        all_staff_response = supabase.rpc("get_all_staff_profiles").execute()
        all_staff = getattr(all_staff_response, "data", None) or []

    if not all_reports:
        st.info("No finalized reports have been submitted yet.")
        return

    # Normalize week_ending_date values to ISO 'YYYY-MM-DD' so comparisons are consistent
    normalized_reports = []
    for r in all_reports:
        raw_week = r.get('week_ending_date')
        try:
            norm_week = pd.to_datetime(raw_week).date().isoformat()
        except Exception:
            norm_week = str(raw_week)
        r['_normalized_week'] = norm_week
        normalized_reports.append(r)

    st.caption(f"Found {len(normalized_reports)} finalized report(s) for this view.")

    all_dates = [r['_normalized_week'] for r in normalized_reports]
    unique_dates = sorted(list(set(all_dates)), reverse=True)

    st.divider()
    st.subheader("Weekly Submission Status (Finalized Reports)")
    selected_date_for_status = st.selectbox("Select a week to check status:", options=unique_dates)
    if selected_date_for_status and all_staff_response.data:
        # If supervisor_mode, use the reports we already fetched (RPC) to avoid RLS blocking a direct query.
        if supervisor_mode:
            submitted_user_ids = {r['user_id'] for r in normalized_reports if r.get('_normalized_week') == selected_date_for_status}
        else:
            submitted_response = supabase.table('reports').select('user_id').eq('week_ending_date', selected_date_for_status).eq('status', 'finalized').execute()
            submitted_user_ids = {item['user_id'] for item in submitted_response.data} if submitted_response.data else set()
        all_staff = all_staff_response.data; submitted_staff, missing_staff = [], []
        for staff_member in all_staff:
            name = staff_member.get("full_name") or staff_member.get("email") or staff_member.get("id")
            title = staff_member.get("title")
            display_info = f"{name} ({title})" if title else name
            if staff_member.get("id") in submitted_user_ids:
                submitted_staff.append(display_info)
            else:
                missing_staff.append(display_info)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"#### ✅ Submitted ({len(submitted_staff)})")
            for person in sorted(submitted_staff):
                st.markdown(f"- {person}")
        with col2:
            st.markdown(f"#### ❌ Missing ({len(missing_staff)})")
            for person in sorted(missing_staff):
                st.markdown(f"- {person}")

    st.divider()
    # Fetch saved summaries including creator info
    summaries_response = supabase.table('weekly_summaries').select('week_ending_date, summary_text, created_by').execute()
    # Map week -> (text, created_by)
    saved_summaries_raw = {s['week_ending_date']: (s['summary_text'], s.get('created_by')) for s in (summaries_response.data or [])}

    # If in supervisor mode, only show summaries that were created_by this supervisor (exclude admin/all-staff archived summaries)
    if supervisor_mode:
        saved_summaries = {week: text for week, (text, creator) in saved_summaries_raw.items() if creator == current_user_id}
    else:
        # Admin/Director sees all saved summaries
        saved_summaries = {week: text for week, (text, creator) in saved_summaries_raw.items()}
    
    # If in supervisor mode, restrict visible saved summaries to weeks that include at least one direct-report report
    if supervisor_mode:
        saved_summaries = {
            week: text
            for week, text in saved_summaries.items()
            if any(r.get('_normalized_week') == week for r in normalized_reports)
        }

    st.divider()
    st.subheader("Unlock Submitted Reports")
    
    # Only show for admin, not supervisor
    if not supervisor_mode:
        st.write("Unlock finalized reports to allow staff to make edits before the deadline.")
        
        # Get all finalized reports for the selected week
        # Fetch ALL reports to get comprehensive date list
        all_reports_response = supabase.table("reports").select("*").order("created_at", desc=True).execute()
        all_reports_comprehensive = getattr(all_reports_response, "data", None) or []
        
        # Use all report dates, not just those visible in current view
        all_report_dates = [r.get("week_ending_date") for r in all_reports_comprehensive if r.get("week_ending_date")]
        all_unique_dates = sorted(list(set(all_report_dates)), reverse=True)
        unlock_week = st.selectbox("Select week to unlock reports:", options=all_unique_dates, key="unlock_week_select")
        
        if unlock_week:
            # Get finalized reports for this week
            finalized_reports = [r for r in all_reports_comprehensive if r.get("week_ending_date") == unlock_week and r.get("status") == "finalized"]
            
            if finalized_reports:
                st.write(f"Found {len(finalized_reports)} finalized report(s) for week ending {unlock_week}:")
                
                # Display reports with unlock buttons
                for report in finalized_reports:
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.write(f"**{report.get('team_member', 'Unknown')}**")
                    
                    with col2:
                        st.write(f"Submitted: {report.get('created_at', '')[:10] if report.get('created_at') else 'Unknown'}")
                    
                    with col3:
                        if st.button("🔓 Unlock", key=f"unlock_{report.get('id')}", help="Change status to draft so staff can edit"):
                            try:
                                # Change status from finalized back to draft
                                supabase.table("reports").update({"status": "draft"}).eq("id", report.get('id')).execute()
                                st.success(f"Report unlocked for {report.get('team_member')}!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to unlock report: {e}")
                
                # Bulk unlock option
                st.divider()
                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button("🔓 Unlock All Reports for This Week", type="secondary"):
                        try:
                            # Unlock all finalized reports for this week
                            supabase.table("reports").update({"status": "draft"}).eq("week_ending_date", unlock_week).eq("status", "finalized").execute()
                            st.success(f"All reports for week ending {unlock_week} have been unlocked!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to unlock reports: {e}")
            else:
                st.info("No finalized reports found for this week.")

    st.divider()
    st.subheader("Enable Submission for Draft Reports")
    
    # Only show for admin, not supervisor
    if not supervisor_mode:
        st.write("Allow staff to submit draft reports that were blocked due to missed deadlines.")
        
        # Fetch ALL reports (including drafts) for admin functions
        all_reports_response = supabase.table("reports").select("*").order("created_at", desc=True).execute()
        all_reports_including_drafts = getattr(all_reports_response, "data", None) or []
        
        st.caption(f"Debug: Found {len(all_reports_including_drafts)} total reports (all statuses)")
        
        # Get all unique dates from ALL reports (not just finalized ones)
        all_report_dates = [r.get("week_ending_date") for r in all_reports_including_drafts if r.get("week_ending_date")]
        all_unique_dates = sorted(list(set(all_report_dates)), reverse=True)
        
        # Show summary of draft reports
        draft_reports_total = [r for r in all_reports_including_drafts if r.get("status") == "draft"]
        if draft_reports_total:
            draft_weeks = {}
            for report in draft_reports_total:
                week = report.get("week_ending_date")
                if week not in draft_weeks:
                    draft_weeks[week] = 0
                draft_weeks[week] += 1
            
            st.info(f"📝 Found {len(draft_reports_total)} total draft reports across {len(draft_weeks)} weeks: " + 
                   ", ".join([f"{week} ({count} reports)" for week, count in sorted(draft_weeks.items(), reverse=True)]))
        
        # Get all draft reports for the selected week
        draft_unlock_week = st.selectbox("Select week to enable draft submissions:", options=all_unique_dates, key="draft_unlock_week_select")
        
        if draft_unlock_week:
            # Get deadline info for this week
            deadline_info = calculate_deadline_info(draft_unlock_week)
            deadline_passed = deadline_info["deadline_passed"]
            
            # Get draft reports for this week
            draft_reports = [r for r in all_reports_including_drafts if r.get("week_ending_date") == draft_unlock_week and r.get("status") == "draft"]
            
            if draft_reports:
                st.write(f"Found {len(draft_reports)} draft report(s) for week ending {draft_unlock_week}:")
                if deadline_passed:
                    st.warning("⏰ The deadline for this week has passed. These reports are currently blocked from submission.")
                else:
                    st.info("✅ The deadline for this week has not passed yet. These reports can already be submitted normally.")
                
                # Display reports with enable submission buttons
                for report in draft_reports:
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.write(f"**{report.get('team_member', 'Unknown')}**")
                    
                    with col2:
                        created_date = report.get('created_at', '')[:10] if report.get('created_at') else 'Unknown'
                        st.write(f"Started: {created_date}")
                    
                    with col3:
                        if deadline_passed:
                            if st.button("⏰ Enable Submission", key=f"enable_{report.get('id')}", help="Allow this draft report to be submitted despite missed deadline"):
                                try:
                                    # Change status to "unlocked" which bypasses deadline check
                                    supabase.table("reports").update({
                                        "status": "unlocked",
                                        "admin_note": f"Submission enabled by administrator after deadline. Enabled on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
                                    }).eq("id", report.get('id')).execute()
                                    st.success(f"Submission enabled for {report.get('team_member')}! They can now finalize their report.")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to enable submission: {e}")
                        else:
                            st.write("✅ Can submit")
                
                # Bulk enable option for past deadline reports
                if deadline_passed and draft_reports:
                    st.divider()
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.button("⏰ Enable All Draft Submissions for This Week", type="secondary"):
                            try:
                                # Enable submission for all draft reports for this week
                                supabase.table("reports").update({
                                    "status": "unlocked",
                                    "admin_note": f"Submission enabled by administrator after deadline. Bulk enabled on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
                                }).eq("week_ending_date", draft_unlock_week).eq("status", "draft").execute()
                                st.success(f"Submission enabled for all {len(draft_reports)} draft reports for week ending {draft_unlock_week}!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to enable submissions: {e}")
            else:
                st.info("No draft reports found for this week.")

    st.divider()
    st.subheader("Missed Deadline Management")
    
    # Only show for admin, not supervisor
    if not supervisor_mode:
        st.write("Create reports for staff who missed the deadline.")
        
        # Get deadline settings using the helper function
        deadline_config = get_deadline_settings()
        
        # Get all unique dates from all reports for missed deadline management
        all_report_dates = [r.get("week_ending_date") for r in all_reports if r.get("week_ending_date")]
        all_unique_dates = sorted(list(set(all_report_dates)), reverse=True)
        missed_week = st.selectbox("Select week with missed deadlines:", options=all_unique_dates, key="missed_deadline_week")
        
        if missed_week:
            # Get all staff and check who hasn't submitted or has non-finalized reports
            all_staff_ids = [staff.get("id") for staff in all_staff]
            # Check for any existing reports (not just finalized ones)
            existing_reports_response = supabase.table("reports").select("user_id, status").eq("week_ending_date", missed_week).execute()
            existing_user_ids = {r['user_id'] for r in existing_reports_response.data}
            finalized_user_ids = {r['user_id'] for r in existing_reports_response.data if r.get('status') == 'finalized'}
            
            # Staff who need attention: no report at all OR have non-finalized reports
            missing_staff = [staff for staff in all_staff if staff.get("id") not in finalized_user_ids]
            
            if missing_staff:
                finalized_count = len(finalized_user_ids)
                total_staff = len(all_staff)
                st.write(f"**{len(missing_staff)} staff member(s) need attention for week ending {missed_week}** ({finalized_count}/{total_staff} finalized):")
                
                for staff in missing_staff:
                    col1, col2, col3 = st.columns([3, 2, 2])
                    
                    with col1:
                        staff_name = staff.get("full_name") or staff.get("title") or staff.get("email", "Unknown")
                        st.write(f"**{staff_name}**")
                    
                    with col2:
                        st.write(staff.get("title", "No title"))
                    
                    with col3:
                        # Check if report already exists for this user and week
                        existing_report_response = supabase.table("reports").select("*").eq("user_id", staff.get("id")).eq("week_ending_date", missed_week).execute()
                        existing_report = existing_report_response.data[0] if existing_report_response.data else None
                        
                        if existing_report:
                            # Report exists - offer to unlock or update it
                            current_status = existing_report.get("status", "draft")
                            if current_status == "finalized":
                                if st.button("� Unlock Report", key=f"unlock_{staff.get('id')}_{missed_week}", help="Unlock this finalized report for editing"):
                                    try:
                                        supabase.table("reports").update({
                                            "status": "unlocked",
                                            "admin_note": f"Report unlocked by administrator for editing. Unlocked on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
                                        }).eq("id", existing_report["id"]).execute()
                                        st.success(f"Report unlocked for {staff_name}. They can now edit and resubmit it.")
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to unlock report: {e}")
                            else:
                                st.write(f"📝 Report exists ({current_status})")
                        else:
                            # No report exists - offer to create one
                            if st.button("�📝 Create Report", key=f"create_{staff.get('id')}_{missed_week}", help="Create empty report for this staff member"):
                                try:
                                    # Create a basic report template for the staff member
                                    empty_report = {
                                        "user_id": staff.get("id"),
                                        "team_member": staff_name,
                                        "week_ending_date": missed_week,
                                        "report_body": {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()},
                                        "professional_development": "",
                                        "key_topics_lookahead": "",
                                        "personal_check_in": "",
                                        "well_being_rating": 3,
                                        "director_concerns": "",
                                        "status": "admin_created",
                                        "created_by_admin": st.session_state["user"].id,
                                        "admin_note": f"Report created by administrator due to missed deadline. Created on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
                                    }
                                    
                                    supabase.table("reports").insert(empty_report).execute()
                                    st.success(f"Empty report created for {staff_name}. They can now edit and submit it.")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to create report: {e}")
                
                # Bulk create option
                truly_missing_staff = []
                for staff in missing_staff:
                    existing_check = supabase.table("reports").select("id").eq("user_id", staff.get("id")).eq("week_ending_date", missed_week).execute()
                    if not existing_check.data:
                        truly_missing_staff.append(staff)
                
                if len(truly_missing_staff) > 1:
                    st.divider()
                    if st.button(f"📝 Create Empty Reports for All {len(truly_missing_staff)} Staff (No Existing Reports)", type="secondary"):
                        try:
                            bulk_reports = []
                            created_count = 0
                            for staff in truly_missing_staff:
                                staff_name = staff.get("full_name") or staff.get("title") or staff.get("email", "Unknown")
                                empty_report = {
                                    "user_id": staff.get("id"),
                                    "team_member": staff_name,
                                    "week_ending_date": missed_week,
                                    "report_body": {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()},
                                    "professional_development": "",
                                    "key_topics_lookahead": "",
                                    "personal_check_in": "",
                                    "well_being_rating": 3,
                                    "director_concerns": "",
                                    "status": "admin_created",
                                    "created_by_admin": st.session_state["user"].id,
                                    "admin_note": f"Report created by administrator due to missed deadline. Created on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
                                }
                                bulk_reports.append(empty_report)
                            
                            if bulk_reports:
                                supabase.table("reports").insert(bulk_reports).execute()
                                st.success(f"Empty reports created for {len(bulk_reports)} staff members!")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.info("No reports to create - all staff already have reports for this week.")
                        except Exception as e:
                            st.error(f"Failed to create bulk reports: {e}")
            else:
                st.success("✅ All staff have submitted reports for this week!")

    st.divider()
    st.subheader("Generate or Regenerate Weekly Summary")
    selected_date_for_summary = st.selectbox("Select a week to summarize:", options=unique_dates)
    button_text = "Generate Weekly Summary Report"
    if selected_date_for_summary in saved_summaries:
        st.info("A summary for this week already exists. Generating a new one will overwrite it.")
        with st.expander("View existing saved summary"): st.markdown(saved_summaries[selected_date_for_summary])
        button_text = "🔄 Regenerate Weekly Summary"
    if st.button(button_text):
        with st.spinner("🤖 Analyzing reports and generating comprehensive summary..."):
            try:
                weekly_reports = [r for r in all_reports if r.get("week_ending_date") == selected_date_for_summary]
                if not weekly_reports:
                    st.warning("No reports found for the selected week.")
                else:
                    well_being_scores = [r.get("well_being_rating") for r in weekly_reports if r.get("well_being_rating") is not None]
                    average_score = round(sum(well_being_scores) / len(well_being_scores), 1) if well_being_scores else "N/A"
                    reports_text = ""
                    all_events_summary = []  # Collect all events for admin summary
                    
                    for r in weekly_reports:
                        reports_text += f"\n---\n**Report from: {r.get('team_member','Unknown')}**\n"
                        reports_text += f"Well-being Score: {r.get('well_being_rating')}/5\n"
                        reports_text += f"Personal Check-in: {r.get('personal_check_in')}\n"
                        reports_text += f"Lookahead: {r.get('key_topics_lookahead')}\n"
                        if not supervisor_mode:
                            reports_text += f"Concerns for Director: {r.get('director_concerns')}\n"
                        

                        
                        report_body = r.get("report_body") or {}
                        for sk, sn in CORE_SECTIONS.items():
                            section_data = report_body.get(sk)
                            if section_data and (section_data.get("successes") or section_data.get("challenges")):
                                reports_text += f"\n*{sn}*:\n"
                                if section_data.get("successes"):
                                    for success in section_data["successes"]:
                                        reports_text += f"- Success: {success.get('text')} `(ASCEND: {success.get('ascend_category','N/A')}, NORTH: {success.get('north_category','N/A')})`\n"
                                        # If this is the events section, also collect for summary
                                        if sk == "events":
                                            # Parse event text to extract name and date
                                            event_text = success.get('text', '')
                                            event_name = event_text
                                            event_date = ""
                                            
                                            if " on " in event_text:
                                                parts = event_text.rsplit(" on ", 1)
                                                if len(parts) == 2:
                                                    event_name = parts[0]
                                                    event_date = parts[1]
                                            
                                            all_events_summary.append({
                                                "event_name": event_name,
                                                "event_date": event_date,
                                                "attendee": r.get('team_member', 'Unknown'),
                                                "ascend_category": success.get('ascend_category', 'N/A'),
                                                "north_category": success.get('north_category', 'N/A'),
                                                "alignment": f"ASCEND: {success.get('ascend_category', 'N/A')}, NORTH: {success.get('north_category', 'N/A')}"
                                            })
                                if section_data.get("challenges"):
                                    for challenge in section_data["challenges"]:
                                        reports_text += f"- Challenge: {challenge.get('text')} `(ASCEND: {challenge.get('ascend_category','N/A')}, NORTH: {challenge.get('north_category','N/A')})`\n"

                    director_section = ""
                    if not supervisor_mode:
                        director_section = """
- **### For the Director's Attention:** Create this section. List any items specifically noted under "Concerns for Director," making sure to mention which staff member raised the concern. If no concerns were raised, state "No specific concerns were raised for the Director this week."
"""

                    # Unified prompt for both Admin and Supervisor summaries:
                    prompt = f"""
You are an executive assistant for the Director of Housing & Residence Life at UND. Your task is to synthesize multiple team reports from the week ending {selected_date_for_summary} into a single, comprehensive summary report.

The report MUST contain the following sections, in this order, using markdown headings exactly as shown:
 1.  **Executive Summary**: A 2-3 sentence high-level overview of the week's key takeaways.
 2.  **ASCEND Framework Summary**: Summarize work aligned with the ASCEND framework (Accountability, Service, Community, Excellence, Nurture, Development). Start this section with the purpose statement: "ASCEND UND Housing is a unified performance framework for the University of North Dakota's Housing and Residence Life staff. It is designed to clearly define job expectations and drive high performance across the department." For each ASCEND category include a heading and bullet points that reference staff by name.
 3.  **Guiding NORTH Pillars Summary**: Summarize work aligned with the Guiding NORTH pillars. Start with the purpose statement: "Guiding NORTH is our core communication standard for UND Housing & Residence Life. It's a simple, five-principle framework that ensures every interaction with students and parents is clear, consistent, and supportive. Its purpose is to build trust and provide reliable direction, making students feel valued and well-supported throughout their housing journey." For each pillar include a heading and bullet points that reference staff by name.
 4.  **UND LEADS Summary**: Start with the purpose statement: "UND LEADS is a roadmap that outlines the university's goals and aspirations. It's built on the idea of empowering people to make a difference and passing on knowledge to future generations." Analyze all activities and categorize them under these UND LEADS pillars with staff names:
   - **Learning**: Professional development, training, skill building, educational initiatives, mentoring
   - **Equity**: Diversity initiatives, inclusive practices, accessibility improvements, fair treatment efforts
   - **Affinity**: Community building, relationship development, team cohesion, campus connections
   - **Discovery**: Research, innovation, new approaches, creative problem-solving, exploration of best practices
   - **Service**: Community service, helping others, volunteer work, supporting university initiatives
 5.  **Overall Staff Well-being**: Start by stating, "The average well-being score for the week was {average_score} out of 5." Provide a 1-2 sentence qualitative summary and a subsection `#### Staff to Connect With` listing staff who reported low scores or concerning comments, with a brief reason.
 6.  **Campus Events Summary**: Create a markdown table with the exact format below:
   
   | Event/Committee | Date | Attendees | Alignment |
   |-----------------|------|-----------|-----------|
   | Event Name | YYYY-MM-DD | Staff Member Name | ASCEND: Category, NORTH: Category |
   
   Include all campus events and committee meetings attended by staff this week. Group multiple attendees for the same event in one row.
 7.  **For the Director's Attention**: A clear list of items that require director-level attention; mention the staff member who raised each item. If none, state "No specific concerns were raised for the Director this week."
 8.  **Key Challenges**: Bullet-point summary of significant or recurring challenges reported by staff, noting who reported them where relevant.
 9.  **Upcoming Projects & Initiatives**: Bullet-point list of key upcoming projects based on the 'Lookahead' sections of the reports.
 
 Additional instructions:
 - Use markdown headings and subheadings exactly as listed above.
 - When summarizing activities under each framework/pillar, reference the team member name (e.g., "Ashley Vandal demonstrated Accountability by...").
 - For UND LEADS, actively look for activities that demonstrate Learning (training, development), Equity (diversity, inclusion), Affinity (relationship building), Discovery (innovation, research), and Service (helping others, community engagement).
 - Be concise and professional. Executive Summary must be 2-3 sentences. Other sections should use short paragraphs and bullets.
 - Ensure every staff member's activities are analyzed for UND LEADS alignment - do not leave this section empty.
Here is the raw report data from all reports for the week, which includes the names of each team member and their categorized activities: {reports_text}
"""
                    model = genai.GenerativeModel("models/gemini-2.5-pro")
                    ai_response = model.generate_content(prompt)
                    st.session_state['last_summary'] = {"date": selected_date_for_summary, "text": ai_response.text}; st.rerun()
            except Exception as e:
                st.error(f"An error occurred while generating the summary: {e}")

    if "last_summary" in st.session_state:
        summary_data = st.session_state["last_summary"]
        if summary_data.get("date") == selected_date_for_summary:
            st.markdown("---")
            st.subheader("Generated Summary (Editable)")
            with st.form("save_summary_form"):
                edited_summary = st.text_area("Edit Summary:", value=summary_data.get("text", ""), height=400)
                save_button = st.form_submit_button("Save Final Summary to Archive", type="primary")
                if save_button:
                    try:
                        if supervisor_mode:
                            # Save into supervisor-specific archive
                            supabase.rpc('save_supervisor_summary', {
                                'p_week': summary_data['date'],
                                'p_text': edited_summary,
                                'p_super': current_user_id,
                                'p_team_ids': []  # optional: pass team member ids if available
                            }).execute()
                        else:
                            # Admin/Director: save global summary
                            supabase.rpc('save_weekly_summary', {
                                'p_week': summary_data['date'],
                                'p_text': edited_summary,
                                'p_creator': current_user_id
                            }).execute()
                        st.success(f"Summary for {summary_data['date']} has been saved!")
                        st.cache_data.clear()
                        del st.session_state['last_summary']
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save summary: {e}")

    if not supervisor_mode:  # Only for admin dashboard
        st.divider()
        st.subheader("🏆 Weekly Staff Recognition")
        
        if st.button("Generate Staff Recognition"):
            with st.spinner("🤖 Evaluating staff performance against ASCEND and NORTH criteria..."):
                weekly_reports = [r for r in all_reports if r.get("week_ending_date") == selected_date_for_summary]
                if weekly_reports:
                    rubrics = load_rubrics()
                    if rubrics:
                        recognition = evaluate_staff_performance(weekly_reports, rubrics)
                        if recognition:
                            st.session_state['staff_recognition'] = {
                                "date": selected_date_for_summary,
                                "data": recognition
                            }
                            st.rerun()

        # Display recognition results
        if "staff_recognition" in st.session_state:
            recognition_data = st.session_state["staff_recognition"]
            if recognition_data.get("date") == selected_date_for_summary:
                st.markdown("### Staff Recognition Results")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    ascend_rec = recognition_data["data"].get("ascend_recognition", {})
                    if ascend_rec:
                        st.markdown("#### 🌟 ASCEND Recognition")
                        st.success(f"**{ascend_rec.get('staff_member')}** - {ascend_rec.get('category')}")
                        st.write(f"**Reasoning:** {ascend_rec.get('reasoning')}")
                        st.metric("Performance Score", f"{ascend_rec.get('score', 0)}/10")
                
                with col2:
                    north_rec = recognition_data["data"].get("north_recognition", {})
                    if north_rec:
                        st.markdown("#### 🧭 NORTH Recognition")
                        st.success(f"**{north_rec.get('staff_member')}** - {north_rec.get('category')}")
                        st.write(f"**Reasoning:** {north_rec.get('reasoning')}")
                        st.metric("Performance Score", f"{north_rec.get('score', 0)}/10")

@st.cache_data
def load_rubrics():
    """Load ASCEND and NORTH rubrics from files"""
    rubrics = {}
    try:
        with open('rubrics-integration/rubrics/ascend_rubric.md', 'r', encoding='utf-8') as f:
            rubrics['ascend'] = f.read()
        with open('rubrics-integration/rubrics/north_rubric.md', 'r', encoding='utf-8') as f:
            rubrics['north'] = f.read()
        with open('rubrics-integration/rubrics/staff_evaluation_prompt.txt', 'r', encoding='utf-8') as f:
            rubrics['evaluation_prompt'] = f.read()
    except FileNotFoundError as e:
        st.error(f"Rubric file not found: {e}")
        return None
    return rubrics

@st.cache_data
def evaluate_staff_performance(weekly_reports, rubrics):
    """Use AI to evaluate staff performance against ASCEND and NORTH criteria"""
    if not weekly_reports or not rubrics:
        return None
    
    model = genai.GenerativeModel("models/gemini-2.5-pro")
    
    # Build staff performance data
    staff_data = []
    for report in weekly_reports:
        staff_info = {
            "name": report.get('team_member', 'Unknown'),
            "well_being_score": report.get('well_being_rating', 0),
            "activities": []
        }
        
        report_body = report.get("report_body", {})
        for section_key, section_data in report_body.items():
            if section_data:
                for success in section_data.get("successes", []):
                    staff_info["activities"].append({
                        "type": "success",
                        "text": success.get("text", ""),
                        "ascend_category": success.get("ascend_category", "N/A"),
                        "north_category": success.get("north_category", "N/A")
                    })
        staff_data.append(staff_info)
    
    staff_json = json.dumps(staff_data, indent=2)
    
    prompt = f"""
{rubrics['evaluation_prompt']}

ASCEND Rubric:
{rubrics['ascend']}

NORTH Rubric:
{rubrics['north']}

Staff Performance Data:
{staff_json}

Return JSON with:
{{
  "ascend_recognition": {{
    "staff_member": "Name",
    "category": "ASCEND Category", 
    "reasoning": "Why they exemplify this category",
    "score": 1-10
  }},
  "north_recognition": {{
    "staff_member": "Name", 
    "category": "NORTH Pillar",
    "reasoning": "Why they exemplify this pillar",
    "score": 1-10
  }}
}}
"""
    
    try:
        response = model.generate_content(prompt)
        clean_response = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_response)
    except Exception as e:
        st.error(f"AI evaluation error: {e}")
        return None

def supervisor_summaries_page():
    st.title("My Saved Team Summaries")
    st.write("Saved summaries you've generated for your team.")
    try:
        resp = supabase.rpc('get_supervisor_summaries', {'p_super': st.session_state['user'].id}).execute()
        summaries = resp.data or []
        if not summaries:
            st.info("You have no saved team summaries yet.")
            return
        for s in summaries:
            with st.expander(f"Week Ending {s['week_ending_date']} — Saved {s['created_at']}"):
                st.markdown(s['summary_text'])
    except Exception as e:
        st.error(f"Failed to fetch supervisor summaries: {e}")

def admin_settings_page():
    st.title("Administrator Settings")
    st.write("Configure system settings and deadlines.")
    
    tab1, tab2 = st.tabs(["📅 Deadline Settings", "📊 Submission Tracking"])
    
    with tab1:
        st.subheader("Weekly Report Deadline Configuration")
        
        # Get current deadline settings using the proper function
        deadline_config = get_deadline_settings()
        current_day = deadline_config.get("day_of_week", 0)  # 0 = Monday
        current_hour = deadline_config.get("hour", 16)  # 4 PM
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
                        # Save to admin_settings table in database
                        result = supabase.table("admin_settings").upsert({
                            "setting_name": "report_deadline",
                            "setting_value": new_settings,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                        
                        st.write(f"Debug: Database response: {result}")  # Debug info
                    
                    # Also update session state for immediate use
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
        
        # Get recent submissions with timing data
        try:
            recent_reports = supabase.table("reports").select("*").eq("status", "finalized").order("submitted_at", desc=True).limit(50).execute()
            if recent_reports.data:
                
                # Get current deadline settings for analysis using helper function
                deadline_config = get_deadline_settings()
                
                # Create submission analysis
                submission_data = []
                for report in recent_reports.data:
                    submitted_at = report.get("submitted_at")
                    if submitted_at:
                        submission_time = pd.to_datetime(submitted_at)
                        
                        # Calculate if submission was on time based on deadline settings
                        week_ending = pd.to_datetime(report.get("week_ending_date"))
                        # Calculate deadline for that week
                        deadline_day = deadline_config["day_of_week"]
                        deadline_hour = deadline_config["hour"] 
                        deadline_minute = deadline_config["minute"]
                        
                        # Deadline is typically the Monday after the Saturday week ending
                        days_after_saturday = (deadline_day - 5) % 7 + (1 if deadline_day <= 5 else 0)
                        deadline_date = week_ending + timedelta(days=days_after_saturday)
                        deadline_datetime = datetime.combine(deadline_date.date(), 
                                                           datetime.min.time().replace(hour=deadline_hour, minute=deadline_minute))
                        deadline_datetime = deadline_datetime.replace(tzinfo=ZoneInfo("America/Chicago"))
                        
                        # Compare submission time to deadline
                        was_on_time = submission_time <= deadline_datetime
                        was_in_grace = submission_time <= (deadline_datetime + timedelta(hours=deadline_config["grace_hours"]))
                        
                        if was_on_time:
                            status = "✅ On Time"
                        elif was_in_grace:
                            status = "⚠️ Grace Period"
                        else:
                            status = "❌ Late"
                        
                        submission_data.append({
                            "Staff Member": report.get("team_member", "Unknown"),
                            "Week Ending": report.get("week_ending_date", "Unknown"), 
                            "Submitted": submission_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "Day of Week": submission_time.strftime("%A"),
                            "Time": submission_time.strftime("%H:%M"),
                            "Deadline": deadline_datetime.strftime("%Y-%m-%d %H:%M"),
                            "Status": status,
                            "Admin Created": "Yes" if report.get("status") == "admin_created" or report.get("created_by_admin") else "No"
                        })
                
                if submission_data:
                    df = pd.DataFrame(submission_data)
                    st.dataframe(df, use_container_width=True)
                    
                    # Summary stats
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

def admin_summaries_page():
    st.title("All Saved Weekly Summaries")
    st.write("View all saved weekly summaries from the entire department.")
    
    try:
        # Get all saved summaries
        summaries_response = supabase.table('weekly_summaries').select('*').order('week_ending_date', desc=True).execute()
        summaries = summaries_response.data or []
        
        if not summaries:
            st.info("No weekly summaries have been saved yet.")
            return
        
        # Group summaries by year for better organization
        summaries_by_year = {}
        for summary in summaries:
            try:
                year = pd.to_datetime(summary['week_ending_date']).year
                if year not in summaries_by_year:
                    summaries_by_year[year] = []
                summaries_by_year[year].append(summary)
            except:
                # If date parsing fails, group under "Unknown"
                if "Unknown" not in summaries_by_year:
                    summaries_by_year["Unknown"] = []
                summaries_by_year["Unknown"].append(summary)
        
        # Display summaries by year
        for year in sorted(summaries_by_year.keys(), reverse=True):
            st.subheader(f"📅 {year}")
            year_summaries = summaries_by_year[year]
            
            for summary in year_summaries:
                week_date = summary.get('week_ending_date', 'Unknown')
                created_date = summary.get('created_at', '')[:10] if summary.get('created_at') else 'Unknown'
                created_by = summary.get('created_by', 'Unknown')
                
                # Get creator name if possible
                creator_name = "Unknown"
                if created_by and created_by != 'Unknown':
                    try:
                        profile_resp = supabase.table('profiles').select('full_name, title').eq('id', created_by).execute()
                        if profile_resp.data:
                            profile = profile_resp.data[0]
                            creator_name = profile.get('full_name') or profile.get('title') or 'Unknown'
                    except:
                        creator_name = "Unknown"
                
                with st.expander(f"Week Ending {week_date} — Created {created_date} by {creator_name}"):
                    st.markdown(summary.get('summary_text', ''))
                    
                    # Add download button for each summary
                    if st.button(f"📄 Download as Text", key=f"download_{summary.get('id', week_date)}"):
                        st.download_button(
                            label="Download Summary",
                            data=summary.get('summary_text', ''),
                            file_name=f"weekly_summary_{week_date}.txt",
                            mime="text/plain"
                        )
        
    except Exception as e:
        st.error(f"Failed to fetch summaries: {e}")

def user_manual_page():
    st.title("User Manual")
    st.markdown("""
    This manual describes how to use the Weekly Impact Reporting Tool and explains differences between regular users, supervisors, and admins.

    ## 1. Account & Access
    - Sign Up: Use "Sign Up" in the sidebar. Provide email, full name, position title, and password.
    - Email Confirmation: After sign up you must confirm your email (Supabase confirmation link).
    - Login: Use "Login" in the sidebar. After logging in the sidebar shows pages available to your role.
    - Roles:
      - Regular staff: Submit and view your own reports.
      - Supervisor: Submit/view own reports; view team reports for direct reports; generate and save team summaries (supervisor-scoped).
      - Admin/Director: Full access to all finalized reports and archived weekly summaries.

    ## 2. Report Workflow (Draft → Review → Finalize)
    1. Go to "Submit / Edit Report".
    2. Create or edit the report for the active week (app calculates the current week and grace period).
    3. Fill Core Activities tabs and General Updates:
       - Core Activities: Sections include Students/Stakeholders, Projects, Collaborations, General Job Responsibilities, Staffing, KPIs.
       - For each section add Successes and Challenges; you can add multiple entries.
       - General Updates: Personal check-in, Professional development, Lookahead, and optional Director concerns (see privacy rules below).
    4. Save Draft: Saves your progress as a draft (you can come back later).
    5. Proceed to Review: The app sends your entries to the AI to categorize each item using ASCEND and Guiding NORTH, and to generate a concise individual summary.
    6. Review Screen: Edit categories, adjust the AI summary, confirm well-being score and general updates.
    7. Lock and Submit: Finalizes the report and marks it "finalized". Finalized reports cannot be edited without supervisor/admin assistance.

    ## 3. Privacy and Visibility Rules
    - Row-Level Security (RLS) is enforced: users only see rows they are permitted to view.
    - Regular staff can only view their own reports.
    - Supervisors can view finalized reports for their direct reports only.
    - Director concerns (the "Concerns for Director" field) are shown only to:
      - The report owner, or
      - Admin/Director accounts.
      Supervisors and other staff will not see director concerns for another person's report.
    - Admin/Director accounts have access to all reports and global weekly summaries.

    ## 4. Troubleshooting & Tips
    - If the app shows unexpected behavior, restart the app and check Streamlit logs for exceptions.
    - Missing finalized reports in the supervisor view: Confirm the report is finalized and profile.supervisor_id is set correctly.
    - AI errors: Simplify long or ambiguous entries and retry "Proceed to Review".
    """, unsafe_allow_html=False)

# --- MAIN APPLICATION LOGIC ---
def main():
    # Remove debug messages for production
    # st.write("Debug: App is loading...")
    # st.write("Debug: Supabase connected")
    
    # Check if user is logged in
    if "user" not in st.session_state:
        # Show login/signup forms
        st.sidebar.title("Welcome")
        tab1, tab2 = st.sidebar.tabs(["Login", "Sign Up"])
        
        with tab1:
            login_form()
        
        with tab2:
            signup_form()
        
        # Show welcome message on main page
        st.title("Weekly Impact Reporting Tool")
        st.write("Please login or create an account using the sidebar.")
        return
    
    # User is logged in - fetch profile info
    try:
        user_id = st.session_state["user"].id
        profile_response = supabase.table("profiles").select("*").eq("id", user_id).execute()
        profile_data = getattr(profile_response, "data", None)
        
        if profile_data:
            profile = profile_data[0]
            st.session_state["role"] = profile.get("role", "staff")
            st.session_state["full_name"] = profile.get("full_name", "")
            st.session_state["title"] = profile.get("title", "")
            st.session_state["is_supervisor"] = bool(profile.get("supervisor_id"))
            
            # Check if user is a supervisor
            supervisor_check = supabase.table("profiles").select("id").eq("supervisor_id", user_id).execute()
            if getattr(supervisor_check, "data", []):
                st.session_state["is_supervisor"] = True
    except Exception as e:
        st.error(f"Error fetching profile: {e}")
        return
    
    # Show sidebar with user info and logout
    st.sidebar.title("Navigation")
    st.sidebar.write(f"Welcome, {st.session_state.get('full_name') or st.session_state['user'].email}!")
    st.sidebar.write(f"Role: {st.session_state.get('role', 'staff').title()}")
    
    if st.sidebar.button("Logout"):
        logout()
        st.rerun()
    
    # Build pages based on user role
    pages = {
        "My Profile": profile_page,
        "Submit / Edit Report": submit_and_edit_page,
        "User Manual": user_manual_page
    }
    
    # Add role-specific pages
    if st.session_state.get("role") == "admin":
        pages["Admin Dashboard"] = lambda: dashboard_page(supervisor_mode=False)
        pages["Admin Settings"] = admin_settings_page
        pages["All Weekly Summaries"] = admin_summaries_page
    
    if st.session_state.get("is_supervisor"):
        pages["Supervisor Dashboard"] = lambda: dashboard_page(supervisor_mode=True)
        pages["My Team Summaries"] = supervisor_summaries_page
    
    # Page selection
    selected_page = st.sidebar.selectbox("Choose a page:", list(pages.keys()))
    
    # Run selected page
    if selected_page in pages:
        pages[selected_page]()

# Run the main application
if __name__ == "__main__":
    main()
