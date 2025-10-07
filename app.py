# app.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client
import google.generativeai as genai
import json
import time
from zoneinfo import ZoneInfo
from collections import Counter

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
ASCEND_VALUES = ["Accountability", "Service", "Community", "Excellence", "Nurture", "Development", "N/A"]
GUIDING_NORTH_PILLARS = ["Nurturing Student Success & Development", "Operational Excellence & Efficiency", "Resource Stewardship & Sustainability", "Transformative & Inclusive Environments", "Holistic Well-being & Safety", "N/A"]
CORE_SECTIONS = {
    "students": "Students/Stakeholders", "projects": "Projects", "collaborations": "Collaborations",
    "responsibilities": "General Job Responsibilities", "staffing": "Staffing/Personnel", "kpis": "KPIs"
}

# --- Helper function to clear form state ---
def clear_form_state():
    keys_to_clear = ['draft_report', 'report_to_edit', 'last_summary']
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    for section_key in CORE_SECTIONS.keys():
        if f"{section_key}_success_count" in st.session_state: del st.session_state[f"{section_key}_success_count"]
        if f"{section_key}_challenge_count" in st.session_state: del st.session_state[f"{section_key}_challenge_count"]

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
                if user_session.user:
                    st.session_state['user'] = user_session.user
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
                if res.user:
                    new_user_id = res.user.id
                    supabase.table('profiles').update({'full_name': full_name, 'title': title}).eq('id', new_user_id).execute()
                    st.success("Signup successful! Please check your email to confirm your account.")
                else:
                    st.error("Signup failed. A user may already exist with this email.")
            except Exception as e:
                if 'already registered' in str(e):
                    st.error("This email address is already registered. Please try logging in.")
                else:
                    st.error(f"An error occurred during signup: {e}")

def logout():
    keys_to_delete = ['user', 'role', 'title', 'full_name', 'last_summary', 'report_to_edit', 'draft_report', 'is_supervisor']
    for key in keys_to_delete:
        if key in st.session_state: del st.session_state[key]
    clear_form_state()

# --- Page Definitions ---
def profile_page():
    st.title("My Profile")
    st.write(f"**Email:** {st.session_state['user'].email}")
    st.write(f"**Role:** {st.session_state.get('role', 'N/A')}")
    with st.form("update_profile"):
        current_name = st.session_state.get('full_name', '')
        new_name = st.text_input("Full Name", value=current_name)
        current_title = st.session_state.get('title', '')
        new_title = st.text_input("Position Title", value=current_title)
        submitted = st.form_submit_button("Update Profile")
        if submitted:
            try:
                user_id = st.session_state['user'].id
                update_data = {'full_name': new_name, 'title': new_title}
                supabase.table('profiles').update(update_data).eq('id', user_id).execute()
                
                st.session_state['full_name'] = new_name
                st.session_state['title'] = new_title
                st.success("Profile updated successfully!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"An error occurred: {e}")

def submit_and_edit_page():
    st.title("Submit / Edit Report")

    def show_report_list():
        st.subheader("Your Submitted Reports")
        user_id = st.session_state['user'].id
        user_reports_response = supabase.table('reports').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
        user_reports = user_reports_response.data or []
        
        now = datetime.now(ZoneInfo("America/Chicago"))
        today = now.date()
        weekday = now.weekday()  # Monday is 0, Sunday is 6

        active_saturday = None
        is_grace_period = False

        if 1 <= weekday <= 5:  # Tuesday to Saturday
            active_saturday = today + timedelta(days=5 - weekday)
        elif weekday == 6:  # Sunday
            active_saturday = today - timedelta(days=1)
            is_grace_period = True
        elif weekday == 0:  # Monday
            active_saturday = today - timedelta(days=2)
            is_grace_period = True

        deadline_is_past = (weekday == 0 and now.hour >= 16)

        if active_saturday:
            active_report_date_str = active_saturday.strftime('%Y-%m-%d')
            has_finalized_for_active_week = any(
                report['week_ending_date'] == active_report_date_str and report.get('status') == 'finalized'
                for report in user_reports
            )

            show_create_button = True
            if has_finalized_for_active_week:
                show_create_button = False
            if is_grace_period and deadline_is_past:
                show_create_button = False

            if show_create_button:
                button_label = f"📝 Create or Edit Report for week ending {active_saturday.strftime('%m/%d/%Y')}"
                if st.button(button_label, use_container_width=True, type="primary"):
                    clear_form_state()
                    existing_report = next((r for r in user_reports if r['week_ending_date'] == active_report_date_str), None)
                    st.session_state['report_to_edit'] = existing_report if existing_report else {'week_ending_date': active_report_date_str}
                    st.rerun()
            elif has_finalized_for_active_week:
                 st.info(f"You have already finalized your report for the week ending {active_saturday.strftime('%m/%d/%Y')}.")
            elif deadline_is_past:
                 st.warning(f"The submission deadline for the report ending {active_saturday.strftime('%m/%d/%Y')} has passed.")


        st.divider()
        if not user_reports:
            st.info("You have not submitted any other reports yet.")
            return
        
        st.markdown("##### All My Reports")
        for report in user_reports:
            status = report.get('status', 'draft').capitalize()
            
            with st.expander(f"Report for week ending {report['week_ending_date']} (Status: {status})"):
                if report.get('individual_summary'):
                    st.info(f"**Your AI-Generated Summary:**\n\n{report['individual_summary']}")
                
                report_body = report.get('report_body') or {}
                for section_key, section_name in CORE_SECTIONS.items():
                    section_data = report_body.get(section_key)
                    if section_data and (section_data.get('successes') or section_data.get('challenges')):
                        st.markdown(f"#### {section_name}")
                        if section_data.get('successes'):
                            st.markdown("**Successes:**")
                            for s in section_data['successes']: st.markdown(f"- {s.get('text', '')} `(ASCEND: {s.get('ascend_category', 'N/A')}, NORTH: {s.get('north_category', 'N/A')})`")
                        if section_data.get('challenges'):
                            st.markdown("**Challenges:**")
                            for c in section_data['challenges']: st.markdown(f"- {c.get('text', '')} `(ASCEND: {c.get('ascend_category', 'N/A')}, NORTH: {c.get('north_category', 'N/A')})`")
                        st.markdown("---")
                
                st.markdown("#### General Updates")
                st.markdown("**Professional Development:**")
                st.write(report.get('professional_development', ''))
                st.markdown("**Lookahead:**")
                st.write(report.get('key_topics_lookahead', ''))
                st.markdown("**Personal Check-in Details:**")
                st.write(report.get('personal_check_in', ''))
                if report.get('director_concerns'):
                    st.warning(f"**Concerns for Director:** {report.get('director_concerns')}")

                if status != 'Finalized':
                    if st.button("Edit This Report", key=f"edit_{report['id']}", use_container_width=True):
                        st.session_state['report_to_edit'] = report
                        st.rerun()

    @st.cache_data
    def process_report_with_ai(items_to_categorize):
        if not items_to_categorize: return None
        model = genai.GenerativeModel('models/gemini-2.5-pro')
        ascend_list = ", ".join(ASCEND_VALUES)
        north_list = ", ".join(GUIDING_NORTH_PILLARS)
        items_json = json.dumps(items_to_categorize)
        prompt = f"""
        You are an expert AI assistant for a university housing department. Your task is to perform two actions on a list of weekly activities:
        1.  **Categorize each activity**: For each activity, assign the single best category from the ASCEND framework and the single best category from the Guiding NORTH framework.
        2.  **Generate an individual summary**: Write a concise, 2-4 sentence professional summary of the user's key contributions based on all their activities.
        **Frameworks:**
        - ASCEND Categories: {ascend_list}
        - Guiding NORTH Categories: {north_list}
        **Input:**
        You will be given a JSON array of activity objects, each with a unique 'id' and a 'text'.
        **Output Format:**
        Return a single, valid JSON object with two top-level keys: "categorized_items" and "individual_summary".
        - "categorized_items": Should be a JSON array where each object has the original 'id', and two new keys: "ascend_category" and "north_category". If a category doesn't fit, use "N/A".
        - "individual_summary": Should be a string containing the professional summary.
        **CRITICAL INSTRUCTION:** The 'id' in each object of your returned "categorized_items" array MUST EXACTLY MATCH the 'id' from the input array for that activity. The number of objects in your output array must be the same as the input array.
        **Example Input:**
        [{{"id": 0, "text": "Organized a community event."}}, {{"id": 1, "text": "Updated the budget spreadsheet."}}]
        **Example Output:**
        {{
            "categorized_items": [
                {{"id": 0, "ascend_category": "Community", "north_category": "Nurturing Student Success & Development"}},
                {{"id": 1, "ascend_category": "Accountability", "north_category": "Resource Stewardship & Sustainability"}}
            ],
            "individual_summary": "This week, the staff member focused on community engagement by organizing a successful event. They also demonstrated strong accountability by maintaining and updating crucial budget documentation."
        }}
        **Here is the JSON array to process:**
        {items_json}
        """
        try:
            response = model.generate_content(prompt)
            clean_response = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(clean_response)
        except Exception as e:
            st.error(f"An AI error occurred during processing: {e}"); return None

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
        report_data = st.session_state['report_to_edit']; is_new_report = not bool(report_data.get('id'))
        st.subheader("Editing Report" if not is_new_report else "Creating New Report")
        with st.form(key="weekly_report_form"):
            col1, col2 = st.columns(2)
            with col1:
                team_member_name = st.session_state.get('full_name') or st.session_state.get('title') or st.session_state['user'].email
                st.text_input("Submitted By", value=team_member_name, disabled=True)
            with col2:
                default_date = pd.to_datetime(report_data.get('week_ending_date')).date()
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
                st.markdown("**Personal Well-being Check-in**")
                well_being_rating = st.radio("How are you doing this week?", options=[1, 2, 3, 4, 5], captions=["Struggling", "Tough Week", "Okay", "Good Week", "Thriving"], horizontal=True, index=report_data.get('well_being_rating', 3) - 1 if not is_new_report else 2)
                st.text_area("Personal Check-in Details (Optional)", value=report_data.get('personal_check_in', ''), key="personal_check_in", height=100)
                st.divider()
                st.subheader("Other Updates")
                st.text_area("Needs or Concerns for Director", value=report_data.get('director_concerns', ''), key="director_concerns", height=150)
                st.text_area("Professional Development", value=report_data.get('professional_development', ''), key="prof_dev", height=150)
                st.text_area("Key Topics & Lookahead", value=report_data.get('key_topics_lookahead', ''), key="lookahead", height=150)
            
            st.divider()
            col1, col2, col3 = st.columns([2,2,1])
            save_draft_button = col1.form_submit_button("Save Draft", use_container_width=True)
            review_button = col2.form_submit_button("Proceed to Review & Finalize", type="primary", use_container_width=True)

        if st.button("Cancel"):
            clear_form_state()
            st.rerun()
            
        clicked_button = None
        for key, value in add_buttons.items():
            if value: clicked_button = key; break
        if clicked_button:
            parts = clicked_button.split('_'); section, category = parts[2], parts[1]
            counter_key = f"{section}_{category}_count"
            if counter_key not in st.session_state: st.session_state[counter_key] = 1
            st.session_state[counter_key] += 1; st.rerun()

        elif save_draft_button:
            with st.spinner("Saving draft..."):
                report_body = {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()}
                for section_key in CORE_SECTIONS.keys():
                    success_texts = [st.session_state[f"{section_key}_success_{i}"] for i in range(st.session_state.get(f"{section_key}_success_count", 1)) if st.session_state.get(f"{section_key}_success_{i}")]
                    challenge_texts = [st.session_state[f"{section_key}_challenge_{i}"] for i in range(st.session_state.get(f"{section_key}_challenge_count", 1)) if st.session_state.get(f"{section_key}_challenge_{i}")]
                    report_body[section_key]['successes'] = [{"text": t} for t in success_texts]
                    report_body[section_key]['challenges'] = [{"text": t} for t in challenge_texts]
                
                draft_data = {
                    "user_id": st.session_state['user'].id, "team_member": team_member_name, "week_ending_date": str(week_ending_date),
                    "report_body": report_body, "professional_development": st.session_state.prof_dev, "key_topics_lookahead": st.session_state.lookahead,
                    "personal_check_in": st.session_state.personal_check_in, "well_being_rating": well_being_rating, "director_concerns": st.session_state.director_concerns,
                    "status": "draft"
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
                    for i in range(st.session_state.get(f"{section_key}_success_count", 1)):
                        text = st.session_state.get(f"{section_key}_success_{i}")
                        if text: items_to_process.append({"id": item_id_counter, "text": text, "section": section_key, "type": "successes"}); item_id_counter += 1
                    for i in range(st.session_state.get(f"{section_key}_challenge_count", 1)):
                        text = st.session_state.get(f"{section_key}_challenge_{i}")
                        if text: items_to_process.append({"id": item_id_counter, "text": text, "section": section_key, "type": "challenges"}); item_id_counter += 1
                
                ai_results = process_report_with_ai(items_to_process)
                
                if ai_results and "categorized_items" in ai_results and "individual_summary" in ai_results and len(ai_results['categorized_items']) == len(items_to_process):
                    categorized_lookup = {item['id']: item for item in ai_results['categorized_items']}
                    report_body = {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()}
                    for item in items_to_process:
                        item_id = item['id']
                        categories = categorized_lookup.get(item_id, {})
                        categorized_item = {"text": item['text'], "ascend_category": categories.get("ascend_category", "N/A"), "north_category": categories.get("north_category", "N/A")}
                        report_body[item['section']][item['type']].append(categorized_item)

                    st.session_state['draft_report'] = {
                        "report_id": report_data.get('id'), "team_member_name": team_member_name,
                        "week_ending_date": str(week_ending_date), "report_body": report_body,
                        "professional_development": st.session_state.prof_dev, "key_topics_lookahead": st.session_state.lookahead,
                        "personal_check_in": st.session_state.personal_check_in, "well_being_rating": well_being_rating,
                        "individual_summary": ai_results['individual_summary'],
                        "director_concerns": st.session_state.director_concerns
                    }
                    st.rerun()
                else:
                    st.error("The AI failed to process the report consistently. Please check your entries for clarity and try submitting again.")

    def show_review_form():
        st.subheader("Review Your AI-Generated Report")
        st.info("The AI has categorized your entries and generated a summary. Please review, edit if necessary, and then finalize your submission.")
        draft = st.session_state['draft_report']
        
        rating = draft.get('well_being_rating')
        if rating:
            st.metric("Your Well-being Score for this Week:", f"{rating}/5")
        st.markdown("---")

        with st.form("review_form"):
            st.markdown(f"**Report for:** {draft['team_member_name']} | **Week Ending:** {draft['week_ending_date']}")
            st.divider()
            st.markdown("### General Updates & Well-being (Review)")
            st.radio("How are you doing this week?", options=[1, 2, 3, 4, 5], captions=["Struggling", "Tough Week", "Okay", "Good Week", "Thriving"], horizontal=True, index=draft['well_being_rating'] - 1, key="review_well_being")
            st.text_area("Personal Check-in Details (Optional)", value=draft['personal_check_in'], key="review_personal_check_in", height=100)
            st.divider()
            st.text_area("Needs or Concerns for Director", value=draft['director_concerns'], key="review_director_concerns", height=150)
            st.text_area("Professional Development", value=draft['professional_development'], key="review_prof_dev", height=150)
            st.text_area("Key Topics & Lookahead", value=draft['key_topics_lookahead'], key="review_lookahead", height=150)
            st.divider()

            for section_key, section_name in CORE_SECTIONS.items():
                section_data = draft['report_body'].get(section_key)
                if section_data and (section_data.get('successes') or section_data.get('challenges')):
                    st.markdown(f"#### {section_name}")
                    for item_type in ['successes', 'challenges']:
                        if section_data.get(item_type):
                            st.markdown(f"**{item_type.capitalize()}:**")
                            for i, item in enumerate(section_data[item_type]):
                                st.markdown(f"> {item['text']}")
                                col1, col2 = st.columns(2)
                                ascend_index = ASCEND_VALUES.index(item['ascend_category']) if item['ascend_category'] in ASCEND_VALUES else len(ASCEND_VALUES) - 1
                                north_index = GUIDING_NORTH_PILLARS.index(item['north_category']) if item['north_category'] in GUIDING_NORTH_PILLARS else len(GUIDING_NORTH_PILLARS) - 1
                                col1.selectbox("ASCEND Category", options=ASCEND_VALUES, index=ascend_index, key=f"review_{section_key}_{item_type}_{i}_ascend")
                                col2.selectbox("Guiding NORTH Category", options=GUIDING_NORTH_PILLARS, index=north_index, key=f"review_{section_key}_{item_type}_{i}_north")
            st.divider()
            st.subheader("Editable Individual Summary")
            st.text_area("AI-Generated Summary", value=draft['individual_summary'], key="review_summary", height=150)
            st.divider()
            col1, col2 = st.columns([3,1])
            with col2:
                finalize_button = st.form_submit_button("Lock and Submit Report", type="primary", use_container_width=True)
        if st.button("Go Back to Edit"):
            st.session_state['report_to_edit'] = {
                "id": draft.get('report_id'), "team_member": draft.get('team_member_name'), "week_ending_date": draft.get('week_ending_date'),
                "report_body": draft.get('report_body'),
                "professional_development": st.session_state.review_prof_dev,
                "key_topics_lookahead": st.session_state.review_lookahead,
                "personal_check_in": st.session_state.review_personal_check_in,
                "well_being_rating": st.session_state.review_well_being,
                "director_concerns": st.session_state.review_director_concerns
            }
            del st.session_state['draft_report']
            st.rerun()

        if finalize_button:
            with st.spinner("Finalizing and saving your report..."):
                final_report_body = {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()}
                original_body = draft['report_body']
                for section_key in CORE_SECTIONS.keys():
                    for item_type in ['successes', 'challenges']:
                        for i, item in enumerate(original_body.get(section_key, {}).get(item_type, [])):
                            final_item = {"text": item['text'], "ascend_category": st.session_state[f"review_{section_key}_{item_type}_{i}_ascend"], "north_category": st.session_state[f"review_{section_key}_{item_type}_{i}_north"]}
                            final_report_body[section_key][item_type].append(final_item)
                
                final_data = {
                    "user_id": st.session_state['user'].id, "team_member": draft['team_member_name'], "week_ending_date": draft['week_ending_date'],
                    "report_body": final_report_body,
                    "professional_development": st.session_state.review_prof_dev,
                    "key_topics_lookahead": st.session_state.review_lookahead,
                    "personal_check_in": st.session_state.review_personal_check_in,
                    "well_being_rating": st.session_state.review_well_being,
                    "individual_summary": st.session_state.review_summary,
                    "director_concerns": st.session_state.review_director_concerns,
                    "status": "finalized"
                }
                
                try:
                    supabase.table("reports").upsert(final_data, on_conflict="user_id, week_ending_date").execute()
                    st.success("✅ Your final report has been saved successfully!")
                    
                    is_update = bool(draft.get('report_id'))
                    if is_update:
                        supabase.table('weekly_summaries').delete().eq('week_ending_date', draft['week_ending_date']).execute()
                        st.warning(f"Note: The saved team summary for {draft['week_ending_date']} has been deleted. An admin will need to regenerate it.")
                    
                    clear_form_state()
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"An error occurred while saving the final report: {e}")

    if 'draft_report' in st.session_state:
        show_review_form()
    elif 'report_to_edit' in st.session_state:
        show_submission_form()
    else:
        show_report_list()

def dashboard_page(supervisor_mode=False):
    if supervisor_mode:
        st.title("Supervisor Dashboard")
        st.write("View your team's reports, track submissions, and generate weekly summaries.")
        current_user_id = st.session_state['user'].id
        
        direct_reports_response = supabase.table('profiles').select('id').eq('supervisor_id', current_user_id).execute()
        direct_report_ids = [user['id'] for user in direct_reports_response.data]

        if not direct_report_ids:
            st.info("You do not have any direct reports assigned in the system.")
            return

        reports_response = supabase.table('reports').select('*').in_('user_id', direct_report_ids).eq('status', 'finalized').order('created_at', desc=True).execute()
        all_reports = reports_response.data
        all_staff_response = supabase.table('profiles').select('*').in_('id', direct_report_ids).execute()
        
    else: # Admin view
        st.title("Admin Dashboard")
        st.write("View reports, track submissions, and generate weekly summaries.")
        reports_response = supabase.table('reports').select('*').eq('status', 'finalized').order('created_at', desc=True).execute()
        all_reports = reports_response.data
        all_staff_response = supabase.rpc('get_all_staff_profiles').execute()
        
    if not all_reports:
        st.info("No finalized reports have been submitted for this view."); return
    
    all_dates = [report['week_ending_date'] for report in all_reports]
    unique_dates = sorted(list(set(all_dates)), reverse=True)
    
    st.divider(); st.subheader("Weekly Submission Status (Finalized Reports)")
    selected_date_for_status = st.selectbox("Select a week to check status:", options=unique_dates, key=f"status_selector_{supervisor_mode}")
    if selected_date_for_status and all_staff_response.data:
        submitted_response = supabase.table('reports').select('user_id').eq('week_ending_date', selected_date_for_status).eq('status', 'finalized').execute()
        submitted_user_ids = {item['user_id'] for item in submitted_response.data} if submitted_response.data else set()
        all_staff = all_staff_response.data; submitted_staff, missing_staff = [], []
        for staff_member in all_staff:
            email = staff_member.get('email', 'Email not found'); title = staff_member.get('title', 'No title set')
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
    selected_date_for_summary = st.selectbox("Select a week to summarize:", options=unique_dates, key=f"summary_selector_{supervisor_mode}")
    button_text = "Generate Weekly Summary Report"
    if selected_date_for_summary in saved_summaries and not supervisor_mode:
        st.info("A summary for this week already exists. Generating a new one will overwrite it.")
        with st.expander("View existing saved summary"): st.markdown(saved_summaries[selected_date_for_summary])
        button_text = "🔄 Regenerate Weekly Summary"
    if st.button(button_text, key=f"generate_summary_{supervisor_mode}"):
        with st.spinner("🤖 Analyzing reports and generating comprehensive summary..."):
            try:
                weekly_reports = [r for r in all_reports if r['week_ending_date'] == selected_date_for_summary]
                if not weekly_reports: st.warning("No reports found for the selected week.")
                else:
                    well_being_scores = [r.get('well_being_rating') for r in weekly_reports if r.get('well_being_rating') is not None]
                    average_score = round(sum(well_being_scores) / len(well_being_scores), 1) if well_being_scores else "N/A"
                    reports_text = ""
                    for r in weekly_reports:
                        reports_text += f"\n---\n**Report from: {r['team_member']}**\n"
                        reports_text += f"Well-being Score: {r.get('well_being_rating')}/5\n"; reports_text += f"Personal Check-in: {r.get('personal_check_in')}\n"; reports_text += f"Lookahead: {r.get('key_topics_lookahead')}\n"
                        if not supervisor_mode:
                            reports_text += f"Concerns for Director: {r.get('director_concerns')}\n"
                        report_body = r.get('report_body') or {}
                        for sk, sn in CORE_SECTIONS.items():
                            section_data = report_body.get(sk)
                            if section_data and (section_data.get('successes') or section_data.get('challenges')):
                                reports_text += f"\n*{sn}*:\n"
                                if section_data.get('successes'):
                                    for success in section_data['successes']: reports_text += f"- Success: {success['text']} `(ASCEND: {success.get('ascend_category', 'N/A')}, NORTH: {success.get('north_category', 'N/A')})`\n"
                                if section_data.get('challenges'):
                                    for challenge in section_data['challenges']: reports_text += f"- Challenge: {challenge['text']} `(ASCEND: {challenge.get('ascend_category', 'N/A')}, NORTH: {challenge.get('north_category', 'N/A')})`\n"
                    
                    director_section_prompt = ""
                    if not supervisor_mode:
                        director_section_prompt = """- **### For the Director's Attention:** Create this section. List any items specifically noted under "Concerns for Director," making sure to mention which staff member raised the concern. If no concerns were raised, state "No specific concerns were raised for the Director this week."
"""

                    prompt = f"""You are an executive assistant for the Director of Housing & Residence Life at UND. Your task is to synthesize multiple team reports from the week ending {selected_date_for_summary} into a single, comprehensive summary report.

The report must contain the following sections, in this order, using markdown headings:
1.  **Executive Summary**: A 2-3 sentence high-level overview of the week's key takeaways.
2.  A summary of work aligned with the ASCEND framework.
3.  A summary of work aligned with the Guiding NORTH pillars.
4.  A summary of work aligned with the UND LEADS strategic pillars.
5.  A summary of overall staff well-being.
6.  A section for items needing the Director's attention.
7.  A summary of key challenges.
8.  A summary of upcoming projects.

**Instructions for each section:**
- **### Executive Summary:** Write a 2-3 sentence paragraph that provides the most critical, high-level overview of the team's accomplishments, challenges, and overall status for the week. This should be suitable for a leader who may only have time to read this one section.
- **### ASCEND Framework Summary:** Start with the following purpose statement: "ASCEND UND Housing is a unified performance framework for the University of North Dakota's Housing and Residence Life staff. It is designed to clearly define job expectations and drive high performance across the department." Then, create a markdown heading for each relevant ASCEND category (Accountability, Service, Community, Excellence, Nurture, Development), followed by bullet points summarizing key staff activities. When summarizing an activity, refer to the staff member by name (e.g., "John Doe demonstrated Accountability by...").
- **### Guiding NORTH Pillars Summary:** Start with the following purpose statement: "Guiding NORTH is our core communication standard for UND Housing & Residence Life. It's a simple, five-principle framework that ensures every interaction with students and parents is clear, consistent, and supportive. Its purpose is to build trust and provide reliable direction, making students feel valued and well-supported throughout their housing journey." Then, create a markdown heading for each relevant Guiding NORTH pillar, followed by bullet points summarizing key staff activities. When summarizing an activity, refer to the staff member by name.
- **### UND LEADS Summary:** Start with the following purpose statement: "UND LEADS is a roadmap that outlines the university's goals and aspirations. It's built on the idea of empowering people to make a difference and passing on knowledge to future generations." Then, create a markdown heading for each relevant UND LEADS pillar (Learning, Equity, Affinity, Discovery, Service), followed by bullet points of key staff activities that fall under it. When summarizing an activity, refer to the staff member by name.
- **### Overall Staff Well-being:** Start by stating, "The average well-being score for the week was {average_score} out of 5." Then, provide a 1-2 sentence qualitative summary of the team's morale. Finally, add a subsection `#### Staff to Connect With`. Under this heading, identify by name any staff who reported a low score (1 or 2) or expressed significant negative sentiment in their comments. Briefly state the reason (e.g., "Jane Doe - reported a low score of 1/5"). If everyone is positive, state that.
{director_section_prompt}
- **### Key Challenges:** Identify and summarize in bullet points any significant or recurring challenges mentioned by the staff from the 'Challenges' sections of their reports. Where relevant, note which staff member reported the challenge.
- **### Upcoming Projects & Initiatives:** Based on the 'Lookahead' portion of the reports, list the key upcoming projects in bullet points. The tone should be professional and concise.

Here is the raw report data from all reports for the week, which includes the names of each team member and their categorized activities: {reports_text}
"""
                    model = genai.GenerativeModel('models/gemini-2.5-pro')
                    ai_response = model.generate_content(prompt)
                    st.session_state['last_summary'] = {"date": selected_date_for_summary, "text": ai_response.text}; st.rerun()
            except Exception as e:
                st.error(f"An error occurred while generating the summary: {e}")
        
        if 'last_summary' in st.session_state:
            summary_data = st.session_state['last_summary']
            if 'date' in summary_data and summary_data['date'] == selected_date_for_summary:
                st.markdown("---")
                st.subheader("Generated Summary (Editable)")
                with st.form("save_summary_form"):
                    edited_summary = st.text_area("Edit Summary:", value=summary_data['text'], height=400)
                    save_button = st.form_submit_button("Save Final Summary to Archive", type="primary")
                    if save_button:
                        try:
                            supabase.table('weekly_summaries').upsert({'week_ending_date': summary_data['date'], 'summary_text': edited_summary}, on_conflict='week_ending_date').execute()
                            st.success(f"Summary for {summary_data['date']} has been saved!")
                            st.cache_data.clear()
                            del st.session_state['last_summary']
                            time.sleep(1)
                            st.rerun()
                        except Exception as e: st.error(f"Failed to save summary: {e}")
    except Exception as e:
        st.error(f"An error occurred while fetching reports: {e}")

def supervisor_dashboard_page():
    dashboard_page(supervisor_mode=True)

def view_summaries_page():
    st.title("Annual Report Archive")
    st.write("This page contains all the saved weekly AI-generated summaries.")
    try:
        summaries_response = supabase.table('weekly_summaries').select('*').order('week_ending_date', desc=True).execute()
        all_reports_response = supabase.table('reports').select('*').eq('status', 'finalized').execute()
        summaries = summaries_response.data or []
        all_reports = all_reports_response.data or []
        if not summaries:
            st.info("No summaries have been saved yet.")
        else:
            reports_by_week = {}
            for report in all_reports:
                week = report['week_ending_date']
                if week not in reports_by_week: reports_by_week[week] = []
                reports_by_week[week].append(report)
            for summary in summaries:
                with st.expander(f"Summary for Week Ending {summary['week_ending_date']}"):
                    st.markdown("### Consolidated Team Summary")
                    st.markdown(summary['summary_text'])
                    st.divider()
                    st.markdown("### Individual Reports for this Week")
                    weekly_reports = reports_by_week.get(summary['week_ending_date'], [])
                    if not weekly_reports:
                        st.warning("No individual reports were found for this summary week.")
                    else:
                        for report in weekly_reports:
                            with st.expander(f"Report from **{report['team_member']}**"):
                                rating = report.get('well_being_rating')
                                if rating: st.metric("Well-being Score", f"{rating}/5")
                                if report.get('individual_summary'):
                                    st.info(f"**Individual AI Summary:**\n\n{report['individual_summary']}")
                                report_body = report.get('report_body') or {}
                                for sk, sn in CORE_SECTIONS.items():
                                    section_data = report_body.get(sk)
                                    if section_data and (section_data.get('successes') or section_data.get('challenges')):
                                        st.markdown(f"#### {sn}")
                                        if section_data.get('successes'):
                                            st.markdown("**Successes:**")
                                            for s in section_data['successes']: st.markdown(f"- {s.get('text', '')} `(ASCEND: {s.get('ascend_category', 'N/A')}, NORTH: {s.get('north_category', 'N/A')})`")
                                        if section_data.get('challenges'):
                                            st.markdown("**Challenges:**")
                                            for c in section_data['challenges']: st.markdown(f"- {c.get('text', '')} `(ASCEND: {c.get('ascend_category', 'N/A')}, NORTH: {c.get('north_category', 'N/A')})`")
                                        st.markdown("---")
    except Exception as e:
        st.error(f"An error occurred while fetching summaries: {e}")

def user_management_page():
    st.title("User Management")
    if st.session_state.get('role') != 'admin':
        st.error("You do not have permission to view this page.")
        return

    try:
        response = supabase.table('profiles').select('id, full_name, supervisor_id').execute()
        users = response.data
        if not users:
            st.info("No users found.")
            return
        
        supervisor_options = {user['id']: user['full_name'] for user in users if user.get('full_name')}
        supervisor_options_list = ["None"] + list(supervisor_options.values())

        st.subheader("Assign Supervisors")
        for user in sorted(users, key=lambda u: u.get('full_name') or ''):
            user_name = user.get('full_name') or f"User with ID: {user['id']}"
            current_supervisor_id = user.get('supervisor_id')
            
            current_supervisor_name = supervisor_options.get(current_supervisor_id, "None")
            
            try:
                current_supervisor_index = supervisor_options_list.index(current_supervisor_name)
            except ValueError:
                current_supervisor_index = 0

            col1, col2 = st.columns([1,2])
            with col1:
                st.markdown(f"**{user_name}**")
            with col2:
                new_supervisor_name = st.selectbox(
                    f"Supervisor for {user_name}",
                    options=supervisor_options_list,
                    index=current_supervisor_index,
                    key=f"supervisor_{user['id']}",
                    label_visibility="collapsed"
                )

            if new_supervisor_name != current_supervisor_name:
                if new_supervisor_name == "None":
                    new_supervisor_id = None
                else:
                    new_supervisor_id = [id for id, name in supervisor_options.items() if name == new_supervisor_name][0]
                
                try:
                    supabase.table('profiles').update({'supervisor_id': new_supervisor_id}).eq('id', user['id']).execute()
                    st.success(f"Updated supervisor for {user_name} to {new_supervisor_name}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to update supervisor: {e}")

    except Exception as e:
        st.error(f"An error occurred while fetching users: {e}")
        
def user_manual_page():
    st.title("User Manual")
    st.markdown("""
    Welcome to the Weekly Impact Reporting Tool. This guide will walk you through creating an account and submitting your weekly reports.
    ### 1. Getting Started
    - **Creating Your Account:** If you are a new user, select "Sign Up" from the sidebar. You will need to provide your email address, full name, position title, and create a password.
    - **Confirming Your Email:** After signing up, you will receive a confirmation email from Supabase. You **must** click the link in this email to activate your account. If you don't see the email, please check your junk or spam folder.
    - **Logging In:** Once your account is confirmed, you can log in using your email and password.

    ### 2. The Reporting Workflow
    This tool uses a "Draft, Review, Finalize" process to give you flexibility.
    - **Draft:** You can save your progress at any time without submitting the final report.
    - **Review:** When you're ready, the tool uses AI to help categorize your entries and generate a summary for your review.
    - **Finalize:** After you've reviewed and edited the AI's suggestions, you will lock in your report, which submits it for the week.

    ### 3. Step-by-Step Guide
    - **Create or Edit Your Report:** From the "Submit / Edit Report" page, click the "Create or Edit This Week's Report" button.
    - **Fill Out Your Report:** Complete the sections under the "Core Activities" and "General Updates" tabs. You can add more entries for successes and challenges as needed.
    - **Save a Draft (Optional):** If you need to stop and come back later, click the **"Save Draft"** button. Your text will be saved, and you can pick up where you left off by clicking the "Create or Edit" button again.
    - **Proceed to Review:** When your report is complete, click the **"Proceed to Review & Finalize"** button. This will send your entries to the AI for processing.
    - **Review the AI's Work:** On the review screen, you will see the categories the AI has assigned and the summary it has written. You can now:
        - Change any of the ASCEND or Guiding NORTH categories using the dropdown menus.
        - Edit the text of your individual AI-generated summary.
        - Make final adjustments to your general updates.
    - **Finalize Your Submission:** When you are satisfied with the entire report, click the **"Lock and Submit Report"** button. This is the final step and will make your report visible to the admin.
    
    ### 4. Framework Definitions
    Below are the definitions for the strategic frameworks used for categorization.
    
    #### ASCEND Framework
    - **Accountability:** Taking ownership of responsibilities, delivering on commitments, and ensuring the integrity of our processes.
    - **Service:** Providing exceptional support and creating positive experiences for our students, staff, and campus partners.
    - **Community:** Fostering a sense of belonging, inclusion, and connection among residents and staff.
    - **Excellence:** Striving for the highest quality in our work, facilities, and programs.
    - **Nurture:** Supporting the holistic well-being and personal growth of our students and team members.
    - **Development:** Creating and promoting opportunities for learning, leadership, and professional growth.

    #### Guiding NORTH Pillars
    - **Nurturing Student Success & Development:** Focusing on the academic, personal, and social success of our students.
    - **Operational Excellence & Efficiency:** Improving processes, systems, and services to be more effective and streamlined.
    - **Resource Stewardship & Sustainability:** Managing financial, environmental, and physical resources responsibly.
    - **Transformative & Inclusive Environments:** Creating welcoming, safe, and equitable spaces for all members of our community.
    - **Holistic Well-being & Safety:** Prioritizing the physical, mental, and emotional health and safety of our residents and staff.
    """)

def automated_reminders_page():
    st.title("Automated Email Reminders Setup")

    st.info("""
    This guide will walk you through the one-time setup process to enable automated email reminders for your team. The system is designed to run every Friday at noon and send a reminder to any user who has not yet submitted a finalized report for the current week.
    """)
    
    st.header("Step 0: Enable Required Database Extensions")
    st.markdown("""
    Before you can schedule tasks or send emails, you need to enable two extensions in your Supabase project.
    1.  Go to your Supabase project dashboard.
    2.  In the left-hand menu, click on **Database**.
    3.  Select **Extensions**.
    4.  In the search bar, type `cron` and enable the `pg_cron` extension.
    5.  In the search bar, type `http` and enable the `http` extension.
    """)

    st.header("Step 1: Get a Resend API Key")
    st.markdown("""
    This system uses a service called **Resend** to send emails. They offer a generous free tier that is perfect for this purpose.
    1.  Go to [resend.com](https://resend.com) and sign up for a free account.
    2.  Navigate to the **API Keys** section in your Resend dashboard.
    3.  Click **"Create API Key"**, give it a name (e.g., "Supabase Reporting Tool"), and copy the key. You will need this for the next step.
    """)

    st.header("Step 2: Add the API Key to Your Supabase Project")
    st.markdown("""
    To keep your API key secure, we will store it as a "Secret" in your Supabase project.
    1.  Go to your Supabase project dashboard.
    2.  Navigate to **Project Settings** > **Edge Functions**.
    3.  Click **"Add a new secret"**.
    4.  For the **Name**, enter `RESEND_API_KEY`.
    5.  For the **Value**, paste the API key you copied from Resend.
    6.  Click **Save**.
    """)

    st.header("Step 3: Create the Database Function")
    st.markdown("""
    This SQL function contains the logic to identify which users need a reminder. Go to the **SQL Editor** in your Supabase dashboard, click **"+ New query"**, and run the following two commands, one after the other.
    """)
    st.code("""
    -- 1. DROP the old function to ensure a clean slate
    DROP FUNCTION IF EXISTS public.send_weekly_reminders();
    """, language="sql")
    st.code("""
    -- 2. CREATE the new, corrected function
    CREATE OR REPLACE FUNCTION public.send_weekly_reminders()
    RETURNS void
    LANGUAGE plpgsql
    SECURITY DEFINER
    AS $$
    DECLARE
        user_record RECORD;
        week_end_date DATE;
    BEGIN
        SELECT (DATE_TRUNC('week', NOW()) + '5 days'::interval)::DATE INTO week_end_date;

        FOR user_record IN
            SELECT id, email FROM auth.users
            WHERE id NOT IN (
                SELECT user_id FROM public.reports
                WHERE week_ending_date = week_end_date AND status = 'finalized'
            )
        LOOP
            PERFORM extensions.http_post(
                url:='YOUR_SUPABASE_PROJECT_URL/functions/v1/send-reminder-email'::text,
                headers:='{"Content-Type": "application/json", "Authorization": "Bearer YOUR_SUPABASE_ANON_KEY"}'::jsonb,
                body:=json_build_object(
                    'email', user_record.email,
                    'week_ending_date', week_end_date
                )::jsonb
            );
        END LOOP;
    END;
    $$;
    """, language="sql")
    st.warning("Remember to replace `YOUR_SUPABASE_PROJECT_URL` and `YOUR_SUPABASE_ANON_KEY` with your actual project details from your Supabase settings.")

    st.header("Step 4: Schedule the Function to Run Weekly")
    st.markdown("""
    Finally, we will use a "Cron Job" to automatically run the function every Friday at noon. Go to the **SQL Editor**, start a new query, and run this code:
    """)
    st.code("""
    SELECT cron.schedule(
        'friday-noon-reminders',
        '0 12 * * 5', -- This is a cron expression for every Friday at 12:00 noon
        $$
        SELECT send_weekly_reminders();
        $$
    );
    """, language="sql")

    st.success("Setup Complete! Your automated email reminders are now active.")

# --- Main App Logic ---
if 'user' not in st.session_state:
    st.sidebar.header("Login or Sign Up")
    choice = st.sidebar.radio("Choose an option", ["Login", "Sign Up"])
    if choice == "Login": login_form()
    else: signup_form()
else:
    if 'role' not in st.session_state:
        try:
            user_id = st.session_state['user'].id
            profile_response = supabase.table('profiles').select('role, title, full_name').eq('id', user_id).execute()
            if profile_response.data:
                profile = profile_response.data[0]
                st.session_state['role'] = profile.get('role')
                st.session_state['title'] = profile.get('title')
                st.session_state['full_name'] = profile.get('full_name')
                
                # Check if the user is a supervisor
                supervisor_check = supabase.table('profiles').select('id', count='exact').eq('supervisor_id', user_id).execute()
                st.session_state['is_supervisor'] = supervisor_check.count > 0
            else:
                st.error("Your account is valid, but your user profile is missing. Please contact an administrator to have it created.")
                st.stop()
        except Exception as e:
            st.error(f"Could not fetch user profile: {e}")
            st.stop()
            
    st.sidebar.write(f"Welcome, **{st.session_state.get('full_name', st.session_state.get('title', st.session_state['user'].email))}**")
    pages = { 
        "My Profile": profile_page, 
        "Submit / Edit Report": submit_and_edit_page,
        "User Manual": user_manual_page
    }
    
    if st.session_state.get('is_supervisor'):
        pages["Supervisor Dashboard"] = supervisor_dashboard_page

    if st.session_state.get('role') == 'admin':
        pages["Admin Dashboard"] = dashboard_page
        pages["Annual Report Archive"] = view_summaries_page
        pages["User Management"] = user_management_page
        pages["Automated Reminders"] = automated_reminders_page
        
    st.sidebar.divider()
    selection = st.sidebar.radio("Go to", pages.keys())
    pages[selection]()
    st.sidebar.divider()
    st.sidebar.button("Logout", on_click=logout)