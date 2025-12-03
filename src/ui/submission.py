import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from datetime import timezone
    class ZoneInfo:
        def __init__(self, tz):
            self.tz = tz
        def utcoffset(self, dt):
            return timezone.utc.utcoffset(dt)
        def dst(self, dt):
            return timezone.utc.dst(dt)
        def tzname(self, dt):
            return "UTC"

from google import genai

from src.database import supabase
from src.config import CORE_SECTIONS, ASCEND_VALUES, NORTH_VALUES
from src.utils import calculate_deadline_info, clear_form_state
from src.ai import clean_summary_response

def submit_and_edit_page():
    def dynamic_entry_section(section_key, section_label, report_data):
        st.subheader(section_label)
        # Special handling for events section
        if section_key == "events":
            if "events_count" not in st.session_state:
                existing_events = report_data.get("events", {}).get("successes", [])
                st.session_state["events_count"] = len(existing_events) if existing_events else 1
            for i in range(st.session_state["events_count"]):
                col1, col2 = st.columns([2, 1])
                default_event_name = ""
                default_event_date = datetime.now().date()
                existing_events = report_data.get("events", {}).get("successes", [])
                if i < len(existing_events):
                    event_text = existing_events[i].get("text", "")
                    if " on " in event_text:
                        parts = event_text.rsplit(" on ", 1)
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
    st.title("Submit / Edit Report")

    from src.database import get_user_client

    def show_report_list():
        st.subheader("Your Submitted Reports")
        user_id = st.session_state["user"].id
        user_client = get_user_client()
        user_reports_response = user_client.table("reports").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        user_reports = getattr(user_reports_response, "data", None) or []
        # ...existing code...

        # Ensure deadline_info and related variables are defined
        try:
            now = datetime.now(ZoneInfo("America/Chicago"))
        except Exception:
            now = datetime.now()
        deadline_info = calculate_deadline_info(now, supabase)
        active_saturday = deadline_info.get("active_saturday") if deadline_info else None
        is_grace_period = deadline_info.get("is_grace_period") if deadline_info else None
        deadline_is_past = deadline_info.get("deadline_passed") if deadline_info else None
        deadline_config = deadline_info.get("config") if deadline_info else None

        if active_saturday is not None and deadline_config is not None:
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
                if st.button(button_label, use_container_width=True, type="primary", key=f"main_report_btn_{active_report_date_str}"):
                    clear_form_state()
                    existing_report = next((r for r in user_reports if r.get("week_ending_date") == active_report_date_str), None)
                    st.session_state["report_to_edit"] = existing_report if existing_report else {"week_ending_date": active_report_date_str}
                    st.rerun()
            elif has_finalized_for_active_week:
                st.info(f"You have already finalized your report for the week ending {active_saturday.strftime('%m/%d/%Y')}.")
            elif deadline_is_past:
                deadline_day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][deadline_config["day_of_week"]]
                st.warning(f"The submission deadline ({deadline_day_name} at {deadline_config['hour']:02d}:{deadline_config['minute']:02d}) for the report ending {active_saturday.strftime('%m/%d/%Y')} has passed. Contact your administrator if you need to submit a report.")

        # Option to create reports for previous weeks (single section only)
        st.divider()
        st.markdown("##### Create Report for Previous Week")
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info("💡 Need to submit a report for a previous week? Select any Saturday (week ending date) below.")
        with col2:
            if st.button("📝 Create Previous Week Report", use_container_width=True, key=f"prev_week_btn_{active_saturday.strftime('%Y-%m-%d') if active_saturday else 'unknown'}"):
                # Calculate previous Saturdays as options
                if active_saturday is not None:
                    previous_saturday_1 = active_saturday - timedelta(days=7)
                    previous_saturday_2 = active_saturday - timedelta(days=14)
                    previous_saturday_3 = active_saturday - timedelta(days=21)
                    clear_form_state()
                    st.session_state["report_to_edit"] = {
                        "week_ending_date": previous_saturday_1.strftime("%Y-%m-%d")  # Default to last week
                    }
                    st.rerun()

        st.divider()
        if not user_reports:
            st.info("You have not submitted any other reports yet.")
            return

        st.markdown("##### All My Reports")
        # Create a selectbox for week selection
        week_options = [report.get('week_ending_date','Unknown') for report in user_reports]
        selected_week = st.selectbox("Select a week to view report:", week_options)
        selected_report = next((r for r in user_reports if r.get('week_ending_date') == selected_week), None)
        if selected_report:
            status = (selected_report.get("status") or "draft").capitalize()
            from src.config import get_secret
            api_key = get_secret("GOOGLE_API_KEY")
            client = genai.Client(api_key=api_key)
            if selected_report.get("individual_summary"):
                st.info(f"**Your AI-Generated Summary:**\n\n{clean_summary_response(selected_report.get('individual_summary'))}")
            report_body = selected_report.get("report_body") or {}
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
            st.write(selected_report.get("professional_development", ""))
            st.markdown("**Lookahead:**")
            st.write(selected_report.get("key_topics_lookahead", ""))
            st.markdown("**Personal Check-in Details:**")
            st.write(selected_report.get("personal_check_in", ""))
            # Only show Director concerns to admins or the report owner
            if selected_report.get('director_concerns'):
                viewer_role = st.session_state.get('role')
                viewer_id = st.session_state['user'].id
                report_owner_id = selected_report.get('user_id')
                if viewer_role == 'admin' or report_owner_id == viewer_id:
                    st.warning(f"**Concerns for Director:** {selected_report.get('director_concerns')}")

            if status.lower() != "finalized":
                if st.button("Edit This Report", key=f"edit_{selected_report.get('id')}", use_container_width=True):
                    st.session_state["report_to_edit"] = selected_report
                    st.rerun()

    @st.cache_data
    def process_report_with_ai(items_to_categorize):
        if not items_to_categorize:
            return None

        from src.ai import generate_individual_report_summary
        individual_summary = generate_individual_report_summary(items_to_categorize)
        # Fallback for categories (can be improved to use AI in future)
        categorized_items = [
            {
                "id": item["id"],
                "ascend_category": "Development",
                "north_category": "Nurturing Student Success & Development"
            } for item in items_to_categorize
        ]
        return {
            "categorized_items": categorized_items,
            "individual_summary": individual_summary
        }

    def show_submission_form():
        report_data = st.session_state["report_to_edit"]
        from src.database import get_user_client
        user_client = get_user_client()
        is_new_report = not bool(report_data.get("id"))
        st.subheader("Editing Report" if not is_new_report else "Creating New Report")
        with st.form(key="weekly_report_form"):
            col1, col2 = st.columns(2)
            with col1:
                team_member_name = st.session_state.get("full_name") or st.session_state.get("title") or st.session_state["user"].email
                st.text_input("Submitted By", value=team_member_name, disabled=True)
            with col2:
                default_date = pd.to_datetime(report_data.get("week_ending_date")).date()
                
                # Show some recent Saturday options as help
                today = datetime.now().date()
                last_saturday = today - timedelta(days=(today.weekday() + 2) % 7)
                recent_saturdays = [
                    last_saturday - timedelta(days=7*i) for i in range(4)
                ]
                saturday_options = ", ".join([d.strftime("%m/%d") for d in recent_saturdays[:3]])
                
                week_ending_date = st.date_input(
                    "For the Week Ending", 
                    value=default_date, 
                    format="MM/DD/YYYY",
                    help=f"💡 Recent Saturdays: {saturday_options}... (Reports are for weeks ending on Saturdays)"
                )
            st.divider()
            core_activities_tab, general_updates_tab = st.tabs(["📊 Core Activities", "📝 General Updates"])
            with core_activities_tab:
                core_tab_list = st.tabs(list(CORE_SECTIONS.values()))
                add_buttons = {}
                # Ensure dynamic_entry_section is accessible
                from inspect import currentframe
                frame = currentframe()
                if "dynamic_entry_section" not in frame.f_globals:
                    frame.f_globals["dynamic_entry_section"] = dynamic_entry_section
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
                    user_client.table("reports").upsert(draft_data, on_conflict="user_id, week_ending_date").execute()
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

                # More flexible validation - allow for fallback processing
                if ai_results and "categorized_items" in ai_results and "individual_summary" in ai_results:
                    try:
                        categorized_lookup = {item["id"]: item for item in ai_results["categorized_items"]}
                        report_body = {key: {"successes": [], "challenges": []} for key in CORE_SECTIONS.keys()}
                        
                        for item in items_to_process:
                            item_id = item["id"]
                            categories = categorized_lookup.get(item_id, {})
                            categorized_item = {
                                "text": item["text"],
                                "ascend_category": categories.get("ascend_category", "Development"),  # Safe default
                                "north_category": categories.get("north_category", "Nurturing Student Success & Development"),  # Safe default
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
                    except Exception as e:
                        st.error(f"Report processing failed: {str(e)}. Please try again or contact support.")
                        st.info("💡 **Troubleshooting Tips:**\n- Check that all text entries are properly filled\n- Try refreshing the page and submitting again\n- Ensure your internet connection is stable")
                else:
                    st.error("The AI processing service is temporarily unavailable. Please try again in a few moments.")
                    st.info("💡 **If this persists:**\n- Check your internet connection\n- Try refreshing the page\n- Contact your administrator if the issue continues")

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
            # Move Regenerate AI Summary button outside the form
        # OUTSIDE st.form block
        if st.button("🔄 Regenerate AI Summary", key="regenerate_ai_summary"):
            from src.ai import generate_individual_report_summary
            # Use the current draft report_body as items_to_categorize
            items_to_categorize = []
            report_body = draft.get("report_body", {})
            for section_key, section_data in report_body.items():
                for item_type in ["successes", "challenges"]:
                    for item in section_data.get(item_type, []):
                        items_to_categorize.append({
                            "id": None,
                            "text": item.get("text", ""),
                            "section": section_key,
                            "type": item_type
                        })
            new_summary = generate_individual_report_summary(items_to_categorize)
            st.session_state["review_summary"] = new_summary
            st.success("AI summary regenerated. Please review the debug output above and the new summary below.")
            st.rerun()

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
                    "submitted_at": datetime.now().isoformat(),
                }

                try:
                    from src.database import get_user_client
                    user_client = get_user_client()
                    user_client.table("reports").upsert(final_data, on_conflict="user_id, week_ending_date").execute()
                    st.success("✅ Your final report has been saved successfully!")
                    is_update = bool(draft.get("report_id"))
                    if is_update:
                        user_client.table("weekly_summaries").delete().eq("week_ending_date", draft.get("week_ending_date")).execute()
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
