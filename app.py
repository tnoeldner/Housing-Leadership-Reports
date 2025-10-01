# app.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client
import google.generativeai as genai
import json

# --- Page Configuration ---
st.set_page_config(page_title="Weekly Impact Report", page_icon="🚀", layout="wide")

# --- Connections ---
@st.cache_resource
def init_connection():
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    genai.configure(api_key=st.secrets["google_api_key"])
    return create_client(url, key)

supabase: Client = init_connection()

# --- CONSTANTS ---
LEADERSHIP_TEAM = ["Troy Noeldner", "Mathew Muston", "Jane Doe", "John Smith"]
ASCEND_VALUES = ["Accountability", "Service", "Community", "Excellence", "Nurture", "Development"]
GUIDING_NORTH_PILLARS = ["Nurturing Student Success & Development", "Operational Excellence & Efficiency", "Resource Stewardship & Sustainability", "Transformative & Inclusive Environments", "Holistic Well-being & Safety"]
CORE_SECTIONS = {
    "students": "Students/Stakeholders", "projects": "Projects", "collaborations": "Collaborations",
    "responsibilities": "General Job Responsibilities", "staffing": "Staffing/Personnel", "kpis": "KPIs"
}

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
                st.session_state['user'] = user_session.user
                user_id = user_session.user.id
                profile = supabase.table('profiles').select('role', 'title').eq('id', user_id).single().execute()
                st.session_state['role'] = profile.data.get('role')
                st.session_state['title'] = profile.data.get('title')
                st.rerun()
            except Exception: st.error("Login failed: Invalid login credentials.")

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
            except Exception as e: st.error(f"Signup failed: {e}")

def logout():
    keys_to_delete = ['user', 'role', 'title', 'last_summary', 'report_to_edit']
    for section_key in CORE_SECTIONS.keys():
        if f"{section_key}_success_count" in st.session_state: del st.session_state[f"{section_key}_success_count"]
        if f"{section_key}_challenge_count" in st.session_state: del st.session_state[f"{section_key}_challenge_count"]
    for key in keys_to_delete:
        if key in st.session_state: del st.session_state[key]
    st.rerun()

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
            except Exception as e: st.error(f"An error occurred: {e}")

# --- Submission and Editing Page ---
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
    user_reports = user_reports_response.data or []
    today = datetime.today().date()
    current_week_saturday = today + timedelta((5 - today.weekday() + 7) % 7)
    current_week_end_date_str = current_week_saturday.strftime('%Y-%m-%d')
    has_submitted_for_current_week = any(report['week_ending_date'] == current_week_end_date_str for report in user_reports)
    if not has_submitted_for_current_week:
        if st.button("📝 Create New Report for week ending " + current_week_saturday.strftime('%m/%d/%Y'), use_container_width=True, type="primary"):
            st.session_state['report_to_edit'] = {}; st.rerun()
    else:
        st.info("You have already submitted your report for the current week. You can edit it below.")
    st.divider()
    if not user_reports:
        st.info("You have not submitted any other reports yet."); return
    st.markdown("##### Past Reports")
    for report in user_reports:
        is_locked = report['week_ending_date'] in locked_weeks
        cols = st.columns([4, 1])
        with cols[0]:
            st.markdown(f"**Week Ending:** {report['week_ending_date']}"); st.caption(f"Status: {'🔒 Locked' if is_locked else '✅ Editable'}")
        with cols[1]:
            if not is_locked:
                if st.button("Edit", key=f"edit_{report['id']}", use_container_width=True):
                    st.session_state['report_to_edit'] = report; st.rerun()

@st.cache_data
def get_ai_batch_categories(items_to_categorize):
    if not items_to_categorize: return {}
    model = genai.GenerativeModel('models/gemini-2.5-pro')
    ascend_list = ", ".join(ASCEND_VALUES)
    north_list = ", ".join(GUIDING_NORTH_PILLARS)
    items_json = json.dumps(items_to_categorize)
    prompt = f"""You are an expert in organizational frameworks for a university housing department. Your task is to categorize a list of activities based on two separate frameworks: ASCEND and Guiding NORTH. The ASCEND categories are: {ascend_list}. The Guiding NORTH categories are: {north_list}. Below is a JSON array of activity objects, each with a unique 'id' and a 'text'. For each object, determine the single best category from each framework. If an activity doesn't clearly fit, return "N/A" for that category's value. Return a single, valid JSON array of objects, where each object has the original 'id', and two new keys: "ascend_category" and "north_category". Here is the JSON array to process: {items_json}"""
    try:
        response = model.generate_content(prompt)
        clean_response = response.text.strip().replace("```json", "").replace("```", "")
        categorized_list = json.loads(clean_response)
        return {item['id']: item for item in categorized_list}
    except Exception as e:
        st.error(f"An AI error occurred during batch categorization: {e}"); return None

def dynamic_entry_section(section_key, section_label, report_data):
    st.subheader(section_label)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Successes")
        s_key = f"{section_key}_success_count"
        if s_key not in st.session_state: st.session_state[s_key] = len(report_data.get(section_key, {}).get('successes', [])) or 1
        for i in range(st.session_state[s_key]):
            default = (report_data.get(section_key, {}).get('successes', [{}])[i].get('text', '')) if i < len(report_data.get(section_key, {}).get('successes', [])) else ""
            st.text_area("Success", value=default, key=f"{section_key}_success_{i}", label_visibility="collapsed", placeholder=f"Success #{i+1}")
    with col2:
        st.markdown("##### Challenges")
        c_key = f"{section_key}_challenge_count"
        if c_key not in st.session_state: st.session_state[c_key] = len(report_data.get(section_key, {}).get('challenges', [])) or 1
        for i in range(st.session_state[c_key]):
            default = (report_data.get(section_key, {}).get('challenges', [{}])[i].get('text', '')) if i < len(report_data.get(section_key, {}).get('challenges', [])) else ""
            st.text_area("Challenge", value=default, key=f"{section_key}_challenge_{i}", label_visibility="collapsed", placeholder=f"Challenge #{i+1}")

def show_submission_form():
    report_data = st.session_state['report_to_edit']; is_new_report = not bool(report_data)
    st.subheader("Editing Report" if not is_new_report else "Creating New Report")
    with st.form(key="weekly_report_form"):
        col1, col2 = st.columns(2)
        with col1: team_member = st.selectbox("Select Your Name", options=LEADERSHIP_TEAM, index=LEADERSHIP_TEAM.index(report_data['team_member']) if not is_new_report and report_data.get('team_member') in LEADERSHIP_TEAM else 0)
        with col2:
            today = datetime.today()
            default_date = pd.to_datetime(report_data['week_ending_date']).date() if not is_new_report else today + timedelta((5 - today.weekday() + 7) % 7)
            week_ending_date = st.date_input("For the Week Ending", value=default_date, format="MM/DD/YYYY")
        st.divider()
        core_activities_tab, general_updates_tab = st.tabs(["📊 Core Activities", "📝 General Updates"])
        with core_activities_tab:
            core_tab_list = st.tabs(list(CORE_SECTIONS.values()))
            add_buttons = {}
            for i, (section_key, section_name) in enumerate(CORE_SECTIONS.items()):
                with core_tab_list[i]:
                    dynamic_entry_section(section_key, section_name, report_data.get('report_body', {}))
                    b1, b2 = st.columns(2)
                    add_buttons[f"add_success_{section_key}"] = b1.form_submit_button("Add Success ➕", key=f"add_s_{section_key}")
                    add_buttons[f"add_challenge_{section_key}"] = b2.form_submit_button("Add Challenge ➕", key=f"add_c_{section_key}")
        with general_updates_tab:
            st.subheader("General Updates & Well-being")
            well_being_rating = st.radio("How are you doing this week?", options=[1, 2, 3, 4, 5], captions=["Struggling", "Tough Week", "Okay", "Good Week", "Thriving"], horizontal=True, index=report_data.get('well_being_rating', 3) - 1 if not is_new_report else 2)
            st.text_area("Personal Check-in Details (Optional)", value=report_data.get('personal_check_in', ''), key="personal_check_in", height=100)
            st.divider()
            st.text_area("Professional Development", value=report_data.get('professional_development', ''), key="prof_dev", height=150)
            st.text_area("Key Topics & Lookahead", value=report_data.get('key_topics_lookahead', ''), key="lookahead", height=150)
        st.divider()
        final_submit_button = st.form_submit_button("Save and Submit Final Report", type="primary")
    if st.button("Cancel"):
        del st.session_state['report_to_edit']
        for sk in CORE_SECTIONS.keys():
            if f"{sk}_success_count" in st.session_state: del st.session_state[f"{sk}_success_count"]
            if f"{sk}_challenge_count" in st.session_state: del st.session_state[f"{sk}_challenge_count"]
        st.rerun()

    clicked_button = None
    for key, value in add_buttons.items():
        if value: clicked_button = key; break
    if clicked_button:
        parts = clicked_button.split('_'); section, category = parts[2], parts[1]
        counter_key = f"{section}_{category}_count"
        if counter_key not in st.session_state: st.session_state[counter_key] = 1
        st.session_state[counter_key] += 1; st.rerun()
    elif final_submit_button:
        with st.spinner("Processing report with AI... This may take a moment."):
            items_to_categorize = []
            item_id_counter = 0
            for section_key in CORE_SECTIONS.keys():
                for i in range(st.session_state.get(f"{section_key}_success_count", 1)):
                    text = st.session_state.get(f"{section_key}_success_{i}")
                    if text: items_to_categorize.append({"id": item_id_counter, "text": text, "section": section_key, "type": "successes"}); item_id_counter += 1
                for i in range(st.session_state.get(f"{section_key}_challenge_count", 1)):
                    text = st.session_state.get(f"{section_key}_challenge_{i}")
                    if text: items_to_categorize.append({"id": item_id_counter, "text": text, "section": section_key, "type": "challenges"}); item_id_counter += 1
            categorized_results = get_ai_batch_categories(items_to_categorize)
            if categorized_results is not None:
                report_body = {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()}
                for item in items_to_categorize:
                    item_id = item['id']; categories = categorized_results.get(item_id, {})
                    report_body[item['section']][item['type']].append({"text": item['text'], "ascend_category": categories.get("ascend_category", "N/A"), "north_category": categories.get("north_category", "N/A")})
                upsert_data = {
                    "user_id": st.session_state['user'].id, "team_member": team_member, "week_ending_date": str(week_ending_date),
                    "report_body": report_body, "professional_development": st.session_state.prof_dev, "key_topics_lookahead": st.session_state.lookahead,
                    "personal_check_in": st.session_state.personal_check_in, "well_being_rating": well_being_rating
                }
                if not is_new_report: upsert_data['id'] = report_data['id']
                try:
                    supabase.table("reports").upsert(upsert_data).execute()
                    st.success("✅ Your report has been categorized and saved successfully!")
                    if 'report_to_edit' in st.session_state: del st.session_state['report_to_edit']
                    for sk in CORE_SECTIONS.keys():
                        if f"{sk}_success_count" in st.session_state: del st.session_state[f"{sk}_success_count"]
                        if f"{sk}_challenge_count" in st.session_state: del st.session_state[f"{sk}_challenge_count"]
                except Exception as e: st.error(f"An error occurred: {e}")

def dashboard_page():
    st.title("Admin Dashboard")
    st.write("View reports, track submissions, and generate weekly summaries.")
    try:
        reports_response = supabase.table('reports').select('week_ending_date', count='exact').execute()
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
            submitted_staff, missing_staff = [], []
            for staff_member in all_staff:
                email = staff_member.get('email', 'Email not found')
                title = staff_member.get('title', 'No title set')
                display_info = f"**{title}** ({email})" if title else email
                if staff_member['id'] in submitted_user_ids: submitted_staff.append(display_info)
                else: missing_staff.append(display_info)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"#### ✅ Submitted ({len(submitted_staff)})")
                for person in sorted(submitted_staff): st.markdown(f"- {person}")
            with col2:
                st.markdown(f"#### ❌ Missing ({len(missing_staff)})")
                for person in sorted(missing_staff): st.markdown(f"- {person}")
        
        st.divider()
        summaries_response = supabase.table('weekly_summaries').select('*').execute()
        saved_summaries = {s['week_ending_date']: s['summary_text'] for s in summaries_response.data} if summaries_response.data else {}
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
                    full_response = supabase.table('reports').select('*').eq('week_ending_date', selected_date_for_summary).execute()
                    weekly_reports = full_response.data
                    if not weekly_reports: st.warning("No reports found for the selected week.")
                    else:
                        reports_text = ""
                        for r in weekly_reports:
                            reports_text += f"\n---\n**Report from: {r['team_member']}**\n"
                            reports_text += f"Well-being Score: {r.get('well_being_rating')}/5\n"
                            reports_text += f"Personal Check-in: {r.get('personal_check_in')}\n"
                            reports_text += f"Lookahead: {r.get('key_topics_lookahead')}\n"
                            report_body = r.get('report_body') or {}
                            for section_key, section_name in CORE_SECTIONS.items():
                                section_data = report_body.get(section_key)
                                if section_data and (section_data.get('successes') or section_data.get('challenges')):
                                    reports_text += f"\n*{section_name}*:\n"
                                    if section_data.get('successes'):
                                        for success in section_data['successes']: reports_text += f"- Success: {success['text']}\n"
                                    if section_data.get('challenges'):
                                        for challenge in section_data['challenges']: reports_text += f"- Challenge: {challenge['text']}\n"
                        prompt = f"""You are an executive assistant for the Director of Housing & Residence Life at UND. Your task is to synthesize multiple team reports from the week ending {selected_date_for_summary} into a single, comprehensive summary report. The report must contain the following sections, in this order, using markdown headings: 1. A summary of work aligned with the UND LEADS strategic pillars (Learning, Equity, Affinity, Discovery, Service). 2. A summary of overall staff well-being. 3. A summary of key challenges. 4. A summary of upcoming projects. **Instructions for each section:** - **UND LEADS Summary:** Create a markdown heading for each relevant UND LEADS pillar, followed by bullet points of key staff activities that fall under it. - **### Overall Staff Well-being:** Start by stating, "The average well-being score for the week was {round(sum([r.get('well_being_rating') for r in weekly_reports if r.get('well_being_rating') is not None]) / len([r.get('well_being_rating') for r in weekly_reports if r.get('well_being_rating') is not None]), 1) if [r.get('well_being_rating') for r in weekly_reports if r.get('well_being_rating') is not None] else 'N/A'} out of 5." Then, provide a 1-2 sentence qualitative summary of the team's morale. Finally, add a subsection `#### Staff to Connect With`. Under this heading, identify by name any staff who reported a low score (1 or 2) or expressed significant negative sentiment in their comments. Briefly state the reason (e.g., "Jane Doe - reported a low score of 1/5"). If everyone is positive, state that. - **### Key Challenges:** Identify and summarize in bullet points any significant or recurring challenges mentioned by the staff. - **### Upcoming Projects & Initiatives:** Based on the 'Lookahead' portion of the reports, list the key upcoming projects in bullet points. The tone should be professional and concise. Here is the raw data from all reports for the week: {reports_text}"""
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
                        st.success(f"Summary for {summary_data['date']} has been saved!"); del st.session_state['last_summary']; st.rerun()
                    except Exception as e: st.error(f"Failed to save summary: {e}")
        
        st.divider(); st.subheader("All Submitted Individual Reports")
        all_reports_response = supabase.table('reports').select('*').order('created_at', desc=True).execute()
        all_reports = all_reports_response.data
        if all_reports:
            for report in all_reports:
                created_date = pd.to_datetime(report['created_at']).strftime('%b %d, %Y')
                with st.expander(f"Report from **{report['team_member']}** for week ending **{report['week_ending_date']}** (Submitted: {created_date})"):
                    rating = report.get('well_being_rating')
                    if rating: st.metric("Well-being Score", f"{rating}/5")
                    report_body = report.get('report_body') or {}
                    for section_key, section_name in CORE_SECTIONS.items():
                        section_data = report_body.get(section_key)
                        if section_data and (section_data.get('successes') or section_data.get('challenges')):
                            st.markdown(f"#### {section_name}")
                            if section_data.get('successes'):
                                st.markdown("**Successes:**")
                                for success in section_data['successes']: st.markdown(f"- {success['text']} `(ASCEND: {success['ascend_category']}, NORTH: {success['north_category']})`")
                            if section_data.get('challenges'):
                                st.markdown("**Challenges:**")
                                for challenge in section_data['challenges']: st.markdown(f"- {challenge['text']} `(ASCEND: {challenge['ascend_category']}, NORTH: {challenge['north_category']})`")
                            st.markdown("---")
                    st.markdown("#### General Updates")
                    st.markdown("**Professional Development:**"); st.write(report['professional_development'])
                    st.markdown("**Lookahead:**"); st.write(report['key_topics_lookahead'])
                    st.markdown("**Personal Check-in Details:**"); st.write(report['personal_check_in'])
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
    pages = { "My Profile": profile_page, "Submit / Edit Report": submit_and_edit_page }
    if st.session_state.get('role') == 'admin':
        pages["Admin Dashboard"] = dashboard_page
        pages["Annual Report Archive"] = view_summaries_page
    st.sidebar.divider()
    selection = st.sidebar.radio("Go to", pages.keys())
    pages[selection]()
    st.sidebar.divider()
    st.sidebar.button("Logout", on_click=logout)