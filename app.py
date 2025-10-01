# app.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client
import google.generativeai as genai

# --- Page Configuration ---
st.set_page_config(page_title="Weekly Impact Report", page_icon="🚀", layout="centered")

# --- Connections ---
@st.cache_resource
def init_connection():
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    genai.configure(api_key=st.secrets["google_api_key"])
    return create_client(url, key)

supabase: Client = init_connection()

# --- User Authentication Functions ---
def login_form():
    st.header("Login")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        if submit:
            try:
                user_session = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state['user'] = user_session.user
                user_id = user_session.user.id
                profile = supabase.table('profiles').select('role', 'title').eq('id', user_id).single().execute()
                st.session_state['role'] = profile.data.get('role')
                st.session_state['title'] = profile.data.get('title')
                st.rerun()
            except Exception:
                st.error("Login failed: Invalid login credentials.")

def signup_form():
    st.header("Sign Up")
    with st.form("signup"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign Up")
        if submit:
            try:
                supabase.auth.sign_up({"email": email, "password": password})
                st.success("Signup successful! Please check your email to confirm your account.")
            except Exception as e:
                st.error(f"Signup failed: {e}")

def logout():
    keys_to_delete = ['user', 'role', 'title', 'last_summary', 'report_to_edit']
    for key in keys_to_delete:
        if key in st.session_state: del st.session_state[key]
    st.rerun()

# --- Page Definitions ---

def profile_page():
    st.title("My Profile")
    st.write(f"**Email:** {st.session_state['user'].email}")
    st.write(f"**Role:** {st.session_state.get('role', 'N/A')}")
    with st.form("update_profile"):
        current_title = st.session_state.get('title', '')
        new_title = st.text_input("Position Title", value=current_title)
        submitted = st.form_submit_button("Update Profile")
        if submitted:
            try:
                user_id = st.session_state['user'].id
                supabase.table('profiles').update({'title': new_title}).eq('id', user_id).execute()
                st.session_state['title'] = new_title
                st.success("Profile updated successfully!")
            except Exception as e:
                st.error(f"An error occurred: {e}")

def submit_and_edit_page():
    st.title("Submit / Edit Report")
    if 'report_to_edit' not in st.session_state:
        show_report_list()
    else:
        show_submission_form()

def show_report_list():
    st.subheader("Your Submitted Reports")
    user_id = st.session_state['user'].id
    locked_weeks_response = supabase.table('weekly_summaries').select('week_ending_date').execute()
    locked_weeks = {item['week_ending_date'] for item in locked_weeks_response.data} if locked_weeks_response.data else set()
    user_reports_response = supabase.table('reports').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
    user_reports = user_reports_response.data

    if st.button("📝 Create New Report", use_container_width=True):
        st.session_state['report_to_edit'] = {}
        st.rerun()
    
    st.divider()

    if not user_reports:
        st.info("You have not submitted any reports yet. Click 'Create New Report' to start.")
        return

    for report in user_reports:
        is_locked = report['week_ending_date'] in locked_weeks
        cols = st.columns([4, 1])
        with cols[0]:
            st.markdown(f"**Week Ending:** {report['week_ending_date']}")
            st.caption(f"Status: {'🔒 Locked' if is_locked else '✅ Editable'}")
        with cols[1]:
            if not is_locked:
                if st.button("Edit", key=f"edit_{report['id']}", use_container_width=True):
                    st.session_state['report_to_edit'] = report
                    st.rerun()

def show_submission_form():
    report_data = st.session_state['report_to_edit']
    is_new_report = not bool(report_data)
    
    st.subheader("Editing Report" if not is_new_report else "Creating New Report")
    
    if not is_new_report:
        st.session_state.ascend_count = len(report_data.get('ascend_activities') or []) or 1
        st.session_state.gn_count = len(report_data.get('guiding_north_activities') or []) or 1
    else:
        if 'ascend_count' not in st.session_state: st.session_state.ascend_count = 1
        if 'gn_count' not in st.session_state: st.session_state.gn_count = 1

    def add_ascend(): st.session_state.ascend_count += 1
    def add_gn(): st.session_state.gn_count += 1
    
    LEADERSHIP_TEAM = ["Troy Noeldner", "Mathew Muston", "Jane Doe", "John Smith"]
    ASCEND_VALUES = ["Accountability", "Service", "Community", "Excellence", "Nurture", "Development"]
    GUIDING_NORTH_PILLARS = ["Nurturing Student Success & Development", "Operational Excellence & Efficiency", "Resource Stewardship & Sustainability", "Transformative & Inclusive Environments", "Holistic Well-being & Safety"]

    with st.form(key="weekly_report_form"):
        col1, col2 = st.columns(2)
        with col1:
            team_member = st.selectbox("Select Your Name", options=LEADERSHIP_TEAM, index=LEADERSHIP_TEAM.index(report_data['team_member']) if not is_new_report and report_data.get('team_member') in LEADERSHIP_TEAM else 0)
        with col2:
            today = datetime.today()
            default_date = pd.to_datetime(report_data['week_ending_date']).date() if not is_new_report else today + timedelta((5 - today.weekday() + 7) % 7)
            week_ending_date = st.date_input("For the Week Ending", value=default_date, format="MM/DD/YYYY")
        st.divider()
        tab1, tab2 = st.tabs(["📊 Core Activities", "📝 General Updates"])
        with tab1:
            st.subheader("ASCEND UND in Action")
            for i in range(st.session_state.ascend_count):
                st.markdown(f"**Activity #{i+1}**"); cols = st.columns([3, 1])
                activity_default = (report_data.get('ascend_activities') or [{}])[i].get('activity', '') if not is_new_report and i < len(report_data.get('ascend_activities') or []) else ""
                value_default = (report_data.get('ascend_activities') or [{}])[i].get('value', None) if not is_new_report and i < len(report_data.get('ascend_activities') or []) else None
                cols[0].text_area("Activity / Accomplishment", value=activity_default, key=f"asc_act_{i}")
                cols[1].selectbox("ASCEND Value", options=ASCEND_VALUES, index=ASCEND_VALUES.index(value_default) if value_default in ASCEND_VALUES else None, key=f"asc_val_{i}")
            st.form_submit_button("Add ASCEND Activity ➕", on_click=add_ascend, use_container_width=True)
            st.markdown("---")
            st.subheader("Progress on Guiding NORTH")
            for i in range(st.session_state.gn_count):
                st.markdown(f"**Activity #{i+1}**"); cols = st.columns([3, 1])
                activity_default = (report_data.get('guiding_north_activities') or [{}])[i].get('activity', '') if not is_new_report and i < len(report_data.get('guiding_north_activities') or []) else ""
                pillar_default = (report_data.get('guiding_north_activities') or [{}])[i].get('pillar', None) if not is_new_report and i < len(report_data.get('guiding_north_activities') or []) else None
                cols[0].text_area("Activity / Accomplishment", value=activity_default, key=f"gn_act_{i}")
                cols[1].selectbox("Guiding NORTH Pillar", options=GUIDING_NORTH_PILLARS, index=GUIDING_NORTH_PILLARS.index(pillar_default) if pillar_default in GUIDING_NORTH_PILLARS else None, key=f"gn_val_{i}")
            st.form_submit_button("Add Guiding NORTH Activity ➕", on_click=add_gn, use_container_width=True)
        with tab2:
            st.subheader("Weekly Updates & Outlook")
            st.text_area("Professional Development", value=report_data.get('professional_development', ''), key="prof_dev", height=150)
            st.text_area("Key Topics & Lookahead", value=report_data.get('key_topics_lookahead', ''), key="lookahead", height=150)
            st.text_area("Personal Check-in (Optional)", value=report_data.get('personal_check_in', ''), key="personal_check_in", height=150)
        st.divider()
        submitted = st.form_submit_button("Save and Submit Report")
    
    if st.button("Cancel"):
        del st.session_state['report_to_edit']
        st.rerun()

    if submitted:
        ascend_activities_list = [{"activity": st.session_state[f"asc_act_{i}"], "value": st.session_state[f"asc_val_{i}"]} for i in range(st.session_state.ascend_count) if st.session_state[f"asc_act_{i}"] and st.session_state[f"asc_val_{i}"]]
        gn_activities_list = [{"activity": st.session_state[f"gn_act_{i}"], "pillar": st.session_state[f"gn_val_{i}"]} for i in range(st.session_state.gn_count) if st.session_state[f"gn_act_{i}"] and st.session_state[f"gn_val_{i}"]]
        if not ascend_activities_list or not gn_activities_list:
            st.warning("Please submit at least one valid activity for both sections.")
        else:
            upsert_data = {
                "user_id": st.session_state['user'].id, "team_member": team_member, "week_ending_date": str(week_ending_date),
                "ascend_activities": ascend_activities_list, "guiding_north_activities": gn_activities_list,
                "personal_check_in": st.session_state.personal_check_in, "professional_development": st.session_state.prof_dev,
                "key_topics_lookahead": st.session_state.lookahead
            }
            if not is_new_report: upsert_data['id'] = report_data['id']
            try:
                supabase.table("reports").upsert(upsert_data).execute()
                st.success("✅ Your report has been saved successfully!")
                del st.session_state['report_to_edit']
                st.session_state.ascend_count = 1
                st.session_state.gn_count = 1
            except Exception as e:
                st.error(f"An error occurred: {e}")

def dashboard_page():
    st.title("Admin Dashboard")
    st.write("View reports, track submissions, and generate weekly summaries.")

    try:
        # --- Data Fetching ---
        reports_response = supabase.table('reports').select('week_ending_date', count='exact').execute()
        
        # --- THIS IS THE KEY CHANGE ---
        # Call the new database function to get all staff profiles
        all_staff_response = supabase.rpc('get_all_staff_profiles').execute()

        if not reports_response.data:
            st.info("No reports have been submitted yet."); return
        
        all_dates = [report['week_ending_date'] for report in reports_response.data]
        unique_dates = sorted(list(set(all_dates)), reverse=True)
        
        st.divider()
        st.subheader("Weekly Submission Status")
        selected_date_for_status = st.selectbox("Select a week to check status:", options=unique_dates)

        if selected_date_for_status and all_staff_response.data:
            submitted_response = supabase.table('reports').select('user_id').eq('week_ending_date', selected_date_for_status).execute()
            submitted_user_ids = {item['user_id'] for item in submitted_response.data} if submitted_response.data else set()

            all_staff = all_staff_response.data
            submitted_staff = []
            missing_staff = []

            for staff_member in all_staff:
                email = staff_member.get('email', 'Email not found')
                title = staff_member.get('title', 'No title set')
                display_info = f"**{title}** ({email})" if title else email
                
                if staff_member['id'] in submitted_user_ids:
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

        # --- AI Summary Generator (no changes in this section) ---
        summaries_response = supabase.table('weekly_summaries').select('*').execute()
        saved_summaries = {s['week_ending_date']: s['summary_text'] for s in summaries_response.data} if summaries_response.data else {}
        
        st.subheader("Generate or Regenerate Weekly Summary")
        selected_date_for_summary = st.selectbox("Select a week to summarize:", options=unique_dates)
        
        button_text = "Generate Weekly Summary Report"
        if selected_date_for_summary in saved_summaries:
            st.info("A summary for this week already exists. Generating a new one will overwrite it.")
            with st.expander("View existing saved summary"):
                st.markdown(saved_summaries[selected_date_for_summary])
            button_text = "🔄 Regenerate Weekly Summary"
        
        if st.button(button_text):
            with st.spinner("🤖 Analyzing reports..."):
                try:
                    full_response = supabase.table('reports').select('*').eq('week_ending_date', selected_date_for_summary).execute()
                    weekly_reports = full_response.data
                    if not weekly_reports: st.warning("No reports found for the selected week.")
                    else:
                        reports_text = ""
                        for r in weekly_reports:
                            reports_text += f"\n---\nReport from: {r['team_member']}\n"
                            ascend_activities = r.get('ascend_activities') or []
                            guiding_north_activities = r.get('guiding_north_activities') or []
                            if ascend_activities:
                                reports_text += "ASCEND Activities:\n"
                                for item in ascend_activities: reports_text += f"- {item.get('value')}: {item.get('activity')}\n"
                            if guiding_north_activities:
                                reports_text += "Guiding NORTH Activities:\n"
                                for item in guiding_north_activities: reports_text += f"- {item.get('pillar')}: {item.get('activity')}\n"
                        prompt = f"""You are an assistant for the Director of Housing & Residence Life at UND. Synthesize multiple team reports from the week ending {selected_date_for_summary} into one cohesive summary structured by the pillars of the university's strategic plan, UND LEADS (Learning, Equity, Affinity, Discovery, Service). The summary must have a markdown heading for each relevant UND LEADS pillar, followed by bullet points of key staff activities. Omit any pillar without relevant activities. The tone should be professional and suitable for a VP. Here is the raw report data: {reports_text}"""
                        model = genai.GenerativeModel('models/gemini-2.5-pro')
                        ai_response = model.generate_content(prompt)
                        st.session_state['last_summary'] = {"date": selected_date_for_summary, "text": ai_response.text}
                        st.rerun()
                except Exception as e: st.error(f"An error occurred while generating the summary: {e}")
        
        if 'last_summary' in st.session_state:
            summary_data = st.session_state['last_summary']
            if summary_data['date'] == selected_date_for_summary:
                st.markdown("---"); st.subheader(f"Newly Generated Summary for Week Ending {summary_data['date']}"); st.markdown(summary_data['text'])
                if st.button("Save this Summary to Annual Report Archive"):
                    try:
                        supabase.table('weekly_summaries').upsert({'week_ending_date': summary_data['date'], 'summary_text': summary_data['text']}, on_conflict='week_ending_date').execute()
                        st.success(f"Summary for {summary_data['date']} has been saved!")
                        del st.session_state['last_summary']; st.rerun()
                    except Exception as e: st.error(f"Failed to save summary: {e}")
        
        st.divider(); st.subheader("All Submitted Individual Reports")
        all_reports_response = supabase.table('reports').select('*').order('created_at', desc=True).execute()
        all_reports = all_reports_response.data
        if all_reports:
            for report in all_reports:
                created_date = pd.to_datetime(report['created_at']).strftime('%b %d, %Y')
                with st.expander(f"Report from **{report['team_member']}** for week ending **{report['week_ending_date']}** (Submitted: {created_date})"):
                    st.markdown("**ASCEND Activities**")
                    ascend_items = report.get('ascend_activities') or []
                    for item in ascend_items: st.markdown(f"- **{item.get('value', 'N/A')}:** *{item.get('activity', '')}*")
                    st.markdown("---")
                    st.markdown("**Guiding NORTH Activities**")
                    north_items = report.get('guiding_north_activities') or []
                    for item in north_items: st.markdown(f"- **{item.get('pillar', 'N/A')}:** *{item.get('activity', '')}*")
                    st.markdown("---")
                    st.markdown("**Professional Development:**"); st.write(report['professional_development'])
                    st.markdown("**Lookahead:**"); st.write(report['key_topics_lookahead'])
        else:
            st.warning("Could not retrieve individual reports.")
    except Exception as e:
        st.error(f"An error occurred while fetching reports: {e}")

def view_summaries_page():
    st.title("Annual Report Archive")
    st.write("This page contains all the saved weekly AI-generated summaries.")
    try:
        response = supabase.table('weekly_summaries').select('*').order('week_ending_date', desc=True).execute()
        summaries = response.data
        if not summaries:
            st.info("No summaries have been saved yet.")
        else:
            for summary in summaries:
                with st.expander(f"Summary for Week Ending {summary['week_ending_date']}"):
                    st.markdown(summary['summary_text'])
    except Exception as e:
        st.error(f"An error occurred while fetching summaries: {e}")

# --- Main App Logic ---
if 'user' not in st.session_state:
    st.sidebar.header("Login or Sign Up")
    choice = st.sidebar.radio("Choose an option", ["Login", "Sign Up"])
    if choice == "Login": login_form()
    else: signup_form()
else:
    st.sidebar.write(f"Welcome, **{st.session_state.get('title', st.session_state['user'].email)}**")
    pages = {
        "My Profile": profile_page,
        "Submit / Edit Report": submit_and_edit_page,
    }
    if st.session_state.get('role') == 'admin':
        pages["Admin Dashboard"] = dashboard_page
        pages["Annual Report Archive"] = view_summaries_page
    st.sidebar.divider()
    selection = st.sidebar.radio("Go to", pages.keys())
    pages[selection]()
    st.sidebar.divider()
    st.sidebar.button("Logout", on_click=logout)