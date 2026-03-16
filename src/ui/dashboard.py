import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime, timedelta, date
try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    def get_central_tz():
        return _ZoneInfo('America/Chicago')
except ImportError:
    import pytz
    def get_central_tz():
        return pytz.timezone('America/Chicago')

from google import genai

from src.database import supabase, safe_db_query, get_admin_client
admin_supabase = get_admin_client()

from src.config import CORE_SECTIONS
from src.ai import clean_summary_response
from src.utils import get_deadline_settings, calculate_deadline_info

def dashboard_page(supervisor_mode=False):
    # Persistent debug: show if about to call AI summary function
    if st.session_state.get('debug_about_to_call_ai_summary'):
        st.info("DEBUG: About to call generate_admin_dashboard_summary (persistent checkpoint)")
    # Persistent debug: show if summary generation button was pressed
    if st.session_state.get('debug_summary_button_pressed'):
        st.info("DEBUG: Summary generation button was pressed. This message persists across reruns.")
    # Persistent debug: after weekly_reports filter
    if st.session_state.get('debug_after_weekly_reports'):
        st.info("DEBUG: After filtering weekly_reports (persistent checkpoint)")
    # Persistent debug: after draft_reports check
    if st.session_state.get('debug_after_draft_reports'):
        st.info("DEBUG: After draft_reports check (persistent checkpoint)")
    # Persistent debug: after duty_reports_section prep
    if st.session_state.get('debug_after_duty_reports_section'):
        st.info("DEBUG: After duty_reports_section prep (persistent checkpoint)")
    # Persistent debug: after engagement_reports_section prep
    if st.session_state.get('debug_after_engagement_reports_section'):
        st.info("DEBUG: After engagement_reports_section prep (persistent checkpoint)")
    # Persistent debug: after reports_text prep
    if st.session_state.get('debug_after_reports_text'):
        st.info("DEBUG: After reports_text prep (persistent checkpoint)")

    # Auto-load all saved duty analyses into session state if not already set
    if 'weekly_duty_reports' not in st.session_state or not st.session_state['weekly_duty_reports']:
        duty_admin_client = get_admin_client()
        duty_analyses_response = duty_admin_client.table("saved_duty_analyses").select("*").order("created_at", desc=True).execute()
        st.session_state['weekly_duty_reports'] = getattr(duty_analyses_response, "data", None) or []
    # Defensive: always assign all_reports and all_staff as lists of dicts
    all_reports = []
    all_staff = []
    if "user" not in st.session_state:
        st.warning("You must be logged in to view this page.")
        st.stop()
    # Only allow admin users to view admin dashboard
    if not supervisor_mode and st.session_state.get("role") != "admin":
        st.warning("You do not have permission to view the Admin Dashboard.")
        st.stop()
    # Ensure we always have the current user's id available (used for RPC/save logic)
    current_user_id = st.session_state['user'].id

    if supervisor_mode:
        st.title("Supervisor Dashboard")
        st.write("View your team's reports, track submissions, and generate weekly summaries.")

        # Get the direct reports (defensive)
        direct_reports_response = supabase.table("profiles").select("id, full_name, title").eq("supervisor_id", current_user_id).execute()
        direct_reports = getattr(direct_reports_response, "data", None)
        if not isinstance(direct_reports, list):
            direct_reports = []
        direct_report_ids = [u.get("id") for u in direct_reports if isinstance(u, dict) and u.get("id")]

        st.caption(f"Found {len(direct_report_ids)} direct report(s).")
        if direct_reports:
            names = ", ".join([str(dr.get("full_name") or dr.get("title") or dr.get("id") or "") for dr in direct_reports if isinstance(dr, dict)])
            st.write("Direct reports:", names)

        if not direct_report_ids:
            st.info("You do not have any direct reports assigned in the system.")
            return
        # Fetch finalized reports and staff once for downstream tabs
        rpc_resp = supabase.rpc('get_finalized_reports_for_supervisor', {'sup_id': current_user_id}).execute()
        rpc_data = getattr(rpc_resp, 'data', None)
        if not isinstance(rpc_data, list):
            rpc_data = []
        all_reports = [r for r in rpc_data if isinstance(r, dict)]

        all_staff_response = supabase.table('profiles').select('*').in_('id', direct_report_ids).execute()
        staff_data = getattr(all_staff_response, "data", None)
        if not isinstance(staff_data, list):
            staff_data = []
        all_staff = [s for s in staff_data if isinstance(s, dict)]

        tabs = st.tabs(["Submission Tracking", "Weekly Status", "Weekly Summary"])

        with tabs[0]:
            st.subheader("Submission Tracking (Direct Reports)")
            st.write("See who submitted each week and who missed, for your team only.")

            today = datetime.now().date()
            default_start = today - timedelta(days=56)
            col_st1, col_st2 = st.columns(2)
            with col_st1:
                start_date = st.date_input("Start week range", value=default_start, key="sup_submission_start")
            with col_st2:
                end_date = st.date_input("End week range", value=today, key="sup_submission_end")

            if start_date > end_date:
                st.error("Start date cannot be after end date.")
            else:
                def nearest_saturday(d: date) -> date:
                    return d + timedelta(days=(5 - d.weekday()) % 7)

                start_week = nearest_saturday(start_date)
                end_week = nearest_saturday(end_date)

                weeks = []
                cur = start_week
                while cur <= end_week:
                    weeks.append(cur)
                    cur += timedelta(days=7)

                # Fetch reports for direct reports within range (service role to avoid any RLS gaps)
                try:
                    reports_resp = admin_supabase.table("reports").select("id,user_id,week_ending_date,status").in_("user_id", direct_report_ids).gte("week_ending_date", start_week.isoformat()).lte("week_ending_date", end_week.isoformat()).execute()
                    reports = [r for r in (reports_resp.data or []) if isinstance(r, dict)]
                except Exception as e:
                    st.error(f"Failed to load submission data: {e}")
                    reports = []

                if not direct_reports:
                    st.info("No profiles found for your team.")
                else:
                    week_set = set(pd.to_datetime(w).date() for w in weeks)

                    def parse_date(value):
                        if isinstance(value, (datetime, date)):
                            return value.date() if isinstance(value, datetime) else value
                        if isinstance(value, str):
                            try:
                                return pd.to_datetime(value).date()
                            except Exception:
                                return None
                        return None

                    # Build report lookup by user and normalized week (nearest Saturday) so off-by-few-days submissions still count
                    rep_map = {}
                    for r in reports:
                        uid = r.get("user_id")
                        w = r.get("week_ending_date")
                        if isinstance(w, str):
                            try:
                                w = pd.to_datetime(w).date()
                            except Exception:
                                continue
                        if isinstance(w, datetime):
                            w = w.date()
                        if uid and w:
                            week_key = nearest_saturday(w)
                            rep_map.setdefault(uid, {})[week_key] = r.get("status")

                    rows = []
                    completed_pairs = 0
                    total_pairs = 0

                    # Map user id to profile info for naming
                    profile_map = {p.get("id"): p for p in direct_reports if isinstance(p, dict)}

                    for uid in direct_report_ids:
                        profile = profile_map.get(uid, {})
                        name = profile.get("full_name") or profile.get("title") or profile.get("id") or "Unknown"
                        user_weeks = rep_map.get(uid, {})
                        created_at = None
                        if user_weeks:
                            try:
                                created_at = min(user_weeks.keys())
                            except Exception:
                                created_at = None
                        creation_week = nearest_saturday(created_at) if created_at else start_week

                        eligible_weeks = {w for w in week_set if w >= creation_week}
                        completed = sum(1 for w in eligible_weeks if user_weeks.get(w) == "finalized")
                        completed_pairs += completed
                        total_pairs += len(eligible_weeks)
                        missed = len(eligible_weeks) - completed
                        last_submit = max([w for w, status in user_weeks.items() if status == "finalized"], default=None)
                        completion_pct = (round((completed / len(eligible_weeks)) * 100, 1) if eligible_weeks else "N/A")
                        rows.append({
                            "User ID": uid,
                            "Name": name,
                            "Completed": completed,
                            "Missed": missed,
                            "Completion %": completion_pct,
                            "Last Submitted": last_submit.isoformat() if last_submit else "—",
                            "Eligible Weeks": len(eligible_weeks),
                            "Creation Week": creation_week.isoformat() if creation_week else "—",
                        })

                    if total_pairs == 0:
                        st.info("No weeks in range.")
                    else:
                        overall_rate = completed_pairs / total_pairs if total_pairs else 0
                        col_s1, col_s2, col_s3 = st.columns(3)
                        with col_s1:
                            st.metric("Completion rate", f"{overall_rate*100:.1f}%")
                        with col_s2:
                            st.metric("Weeks per user", len(week_set))
                        with col_s3:
                            st.metric("Users", len(direct_report_ids))

                    df = pd.DataFrame(rows)
                    st.markdown("**Team submission summary**")
                    st.dataframe(df.drop(columns=["User ID"]), use_container_width=True, hide_index=True)

                    st.markdown("**Per-week status**")
                    matrix_rows = []
                    week_labels = [w.isoformat() for w in weeks]
                    for p in rows:
                        uid = p.get("User ID")
                        user_weeks = rep_map.get(uid, {}) if uid else {}
                        created_at = None
                        if user_weeks:
                            try:
                                created_at = min(user_weeks.keys())
                            except Exception:
                                created_at = None
                        creation_week = nearest_saturday(created_at) if created_at else start_week
                        entry = {"Name": p["Name"], "% Complete": f"{p['Completion %']}%" if isinstance(p.get("Completion %"), (int, float)) else p.get("Completion %")}
                        for w in weeks:
                            w_date = pd.to_datetime(w).date()
                            if w_date < creation_week:
                                entry[w.isoformat()] = "N/A"
                            else:
                                status = user_weeks.get(w_date)
                                entry[w.isoformat()] = "✅" if status == "finalized" else "❌"
                        matrix_rows.append(entry)
                    matrix_df = pd.DataFrame(matrix_rows)
                    st.dataframe(matrix_df[["Name", "% Complete", *week_labels]], use_container_width=True, hide_index=True)

        # Normalize data for other tabs
        normalized_reports = []
        for r in all_reports:
            if not isinstance(r, dict):
                continue
            raw_week = r.get('week_ending_date')
            try:
                if raw_week:
                    norm_week = pd.to_datetime(str(raw_week)).date().isoformat()
                else:
                    norm_week = ''
            except Exception:
                norm_week = str(raw_week)
            r['_normalized_week'] = norm_week
            normalized_reports.append(r)

        all_dates = [r['_normalized_week'] for r in normalized_reports]
        unique_dates = sorted(list(set(all_dates)), reverse=True)

        with tabs[1]:
            st.subheader("Weekly Submission Status (Finalized & Draft Reports)")
            if not normalized_reports:
                st.info("No reports found for your team.")
            else:
                selected_date_for_status = st.selectbox("Select a week to check status:", options=unique_dates, key="sup_status_week")
                if selected_date_for_status and all_staff_response.data:
                    week_reports = [r for r in normalized_reports if r.get('_normalized_week') == selected_date_for_status]
                    finalized_user_ids = {r['user_id'] for r in week_reports if r.get('status') == 'finalized'}
                    draft_user_ids = {r['user_id'] for r in week_reports if r.get('status') == 'draft'}
                    unlocked_user_ids = {r['user_id'] for r in week_reports if r.get('status') == 'unlocked'}
                    all_staff = all_staff_response.data
                    finalized_staff, draft_staff, unlocked_staff, admin_created_staff, missing_staff = [], [], [], [], []
                    admin_created_reports = [r for r in week_reports if r.get('status') == 'admin created']
                    for staff_member in all_staff:
                        name = staff_member.get("full_name") or staff_member.get("email") or staff_member.get("id")
                        title = staff_member.get("title")
                        display_info = f"{name} ({title})" if title else name
                        uid = staff_member.get("id")
                        if uid in finalized_user_ids:
                            finalized_staff.append(display_info)
                        elif uid in draft_user_ids:
                            draft_staff.append(display_info)
                        elif uid in unlocked_user_ids:
                            unlocked_staff.append(display_info)
                        else:
                            missing_staff.append(display_info)
                    admin_created_staff = []
                    for r in admin_created_reports:
                        member = r.get('team_member') or r.get('email') or r.get('user_id') or 'Unknown'
                        admin_created_staff.append(str(member))
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.markdown(f"#### ✅ Finalized ({len(finalized_staff)})")
                        for person in sorted(finalized_staff):
                            st.markdown(f"- {person}")
                    with col2:
                        st.markdown(f"#### 📝 Draft ({len(draft_staff)})")
                        for person in sorted(draft_staff):
                            st.markdown(f"- {person}")
                    with col3:
                        st.markdown(f"#### ⏰ Unlocked ({len(unlocked_staff)})")
                        for person in sorted(unlocked_staff):
                            st.markdown(f"- {person}")
                    with col4:
                        st.markdown(f"#### 🏷️ Created by Admin ({len(admin_created_staff)})")
                        for person in sorted(admin_created_staff):
                            st.markdown(f"- {person}")
                    st.markdown(f"#### ❌ Missing ({len(missing_staff)})")
                    for person in sorted(missing_staff):
                        st.markdown(f"- {person}")

        with tabs[2]:
            st.subheader("Generate or Regenerate Weekly Summary")
            if not normalized_reports:
                st.info("No reports found for your team.")
            else:
                selected_date_for_summary = st.selectbox("Select a week to summarize:", options=unique_dates, key="sup_summary_week")
                button_text = "Generate Weekly Summary Report"
                # Fetch saved summaries including creator info
                summaries_response = supabase.table('weekly_summaries').select('week_ending_date, summary_text, created_by').execute()
                saved_summaries_raw = {}
                if hasattr(summaries_response, 'data') and isinstance(summaries_response.data, list):
                    for s in summaries_response.data:
                        if isinstance(s, dict):
                            saved_summaries_raw[s.get('week_ending_date')] = (s.get('summary_text'), s.get('created_by'))

                # Only show summaries created by this supervisor
                saved_summaries = {week: text for week, (text, creator) in saved_summaries_raw.items() if creator == current_user_id}
                if selected_date_for_summary in saved_summaries:
                    st.info("A summary for this week already exists. Generating a new one will overwrite it.")
                    with st.expander("View existing saved summary"):
                        st.markdown(clean_summary_response(saved_summaries[selected_date_for_summary]))
                    button_text = "🔄 Regenerate Weekly Summary"
                if st.button(button_text, key="sup_generate_summary"):
                    st.session_state['trigger_generate_summary'] = True

                if st.session_state.get('trigger_generate_summary'):
                    with st.spinner("🤖 Analyzing reports and generating comprehensive summary..."):
                        try:
                            # Use normalized week value to avoid mismatches between date/datetime strings
                            weekly_reports = [
                                r for r in normalized_reports if r.get("_normalized_week") == selected_date_for_summary
                            ]
                            st.session_state['debug_after_weekly_reports'] = True
                            st.session_state['debug_after_draft_reports'] = True

                            director_section = ""
                            if not supervisor_mode:
                                director_section = """
- **### For the Director's Attention:** Create this section. List any items specifically noted under "Concerns for Director," making sure to mention which staff member raised the concern. If no concerns were raised, state "No specific concerns were raised for the Director this week."
"""

                            st.session_state['debug_after_draft_reports_block'] = True

                            duty_reports_section = ""
                            st.session_state['debug_after_duty_reports_section'] = True
                            if 'weekly_duty_reports' not in st.session_state:
                                st.warning("No 'weekly_duty_reports' found in session state. Duty analysis integration skipped.")
                            elif not st.session_state['weekly_duty_reports']:
                                st.warning("'weekly_duty_reports' in session state is empty. Duty analysis integration skipped.")
                            else:
                                filtered_duty_reports = []
                                for dr in st.session_state['weekly_duty_reports']:
                                    week_match = False
                                    dr_week = dr.get('week_ending_date')
                                    debug_msg = ''
                                    try:
                                        if dr_week:
                                            dr_date = pd.to_datetime(str(dr_week)).date()
                                            summary_date = pd.to_datetime(str(selected_date_for_summary)).date()
                                            diff_days = abs((dr_date - summary_date).days)
                                            debug_msg = f"Duty analysis date: {dr_date}, summary week: {summary_date}, diff: {diff_days} days. "
                                            if diff_days <= 1:
                                                week_match = True
                                                debug_msg += "INCLUDED (±1 day window)"
                                            else:
                                                debug_msg += "NOT included (outside ±1 day window)"
                                        elif dr.get('date_range'):
                                            start, end = dr['date_range'].split(' to ')
                                            start_date = pd.to_datetime(start).date()
                                            end_date = pd.to_datetime(end).date()
                                            summary_date = pd.to_datetime(str(selected_date_for_summary)).date()
                                            debug_msg = f"Duty analysis date range: {start_date} to {end_date}, summary week: {summary_date}. "
                                            if start_date <= summary_date <= end_date:
                                                week_match = True
                                                debug_msg += "INCLUDED (within date range)"
                                            else:
                                                debug_msg += "NOT included (outside date range)"
                                    except Exception as e:
                                        debug_msg = f"ERROR parsing duty analysis date: {e}"
                                    st.info(debug_msg)
                                    if week_match:
                                        filtered_duty_reports.append(dr)
                                if filtered_duty_reports:
                                    st.success("🛡️ Duty analysis FOUND for this week. It will be included in the summary.")
                                    duty_reports_section = "\n\n=== WEEKLY DUTY REPORTS INTEGRATION ===\n"
                                    for i, duty_report in enumerate(filtered_duty_reports, 1):
                                        duty_reports_section += f"\n--- DUTY REPORT {i} ---\n"
                                        duty_reports_section += json.dumps(duty_report, indent=2)
                                else:
                                    st.warning("No duty analysis found for this week (within ±1 day window or matching date range).")

                            engagement_reports_section = ""
                            st.session_state['debug_after_engagement_reports_section'] = True
                            st.session_state['debug_after_reports_text'] = True

                            reports_text = ""
                            for r in weekly_reports:
                                try:
                                    clean_body = json.dumps(r.get('report_body', {}), indent=2)
                                except Exception:
                                    clean_body = str(r.get('report_body', {}))
                                reports_text += f"\n--- REPORT FOR {r.get('team_member', 'Unknown')} (status: {r.get('status', 'unknown')}) ---\n"
                                reports_text += clean_body

                            # Build prompt
                            prompt = f"""
You are generating a comprehensive weekly summary for the supervisor's direct reports. Week ending: {selected_date_for_summary}.

Weekly staff reports:\n{reports_text}

{duty_reports_section}
{engagement_reports_section}
{director_section}
"""

                            response = admin_supabase.functions.invoke(
                                "generate_admin_dashboard_summary",
                                body={"prompt": prompt},
                                timeout=120,
                            )
                            summary_text = response.data if hasattr(response, 'data') else response
                            st.session_state['debug_summary_response'] = summary_text
                            st.success("✅ Weekly summary generated!")
                            st.markdown(clean_summary_response(summary_text))
                        except Exception as e:
                            st.error(f"Failed to generate summary: {e}")
            # end tabs[2]

        # All supervisor content is contained within tabs; avoid rendering admin sections below
        return

    else:
        # Only show admin dashboard content when explicitly called, not at the top of every page
        # Fetch both finalized and draft reports for admin dashboard
        reports_response = admin_supabase.table("reports").select("*").order("created_at", desc=True).execute()
        raw_reports = getattr(reports_response, 'data', None)
        if not isinstance(raw_reports, list):
            raw_reports = []
        all_reports = [r for r in raw_reports if isinstance(r, dict)]
        all_staff_response = admin_supabase.rpc("get_all_staff_profiles").execute()
        raw_staff = getattr(all_staff_response, 'data', None)
        if not isinstance(raw_staff, list):
            raw_staff = []
        all_staff = [s for s in raw_staff if isinstance(s, dict)]

    if not all_reports:
        # Do not show any info message; just return
        return

    # Normalize week_ending_date values to ISO 'YYYY-MM-DD' so comparisons are consistent
    normalized_reports = []
    for r in all_reports:
        if not isinstance(r, dict):
            continue
        raw_week = r.get('week_ending_date')
        try:
            if raw_week:
                norm_week = pd.to_datetime(str(raw_week)).date().isoformat()
            else:
                norm_week = ''
        except Exception:
            norm_week = str(raw_week)
        r['_normalized_week'] = norm_week
        normalized_reports.append(r)

    st.caption(f"Found {len(normalized_reports)} finalized report(s) for this view.")

    all_dates = [r['_normalized_week'] for r in normalized_reports]
    unique_dates = sorted(list(set(all_dates)), reverse=True)

    st.divider()
    st.subheader("Weekly Submission Status (Finalized & Draft Reports)")
    selected_date_for_status = st.selectbox("Select a week to check status:", options=unique_dates)
    if selected_date_for_status and all_staff_response.data:
        # Get all reports for the selected week
        week_reports = [r for r in normalized_reports if r.get('_normalized_week') == selected_date_for_status]
        finalized_user_ids = {r['user_id'] for r in week_reports if r.get('status') == 'finalized'}
        draft_user_ids = {r['user_id'] for r in week_reports if r.get('status') == 'draft'}
        unlocked_user_ids = {r['user_id'] for r in week_reports if r.get('status') == 'unlocked'}
        all_staff = all_staff_response.data
        finalized_staff, draft_staff, unlocked_staff, admin_created_staff, missing_staff = [], [], [], [], []
        # Collect admin-created reports for the selected week
        admin_created_reports = [r for r in week_reports if r.get('status') == 'admin created']
        for staff_member in all_staff:
            name = staff_member.get("full_name") or staff_member.get("email") or staff_member.get("id")
            title = staff_member.get("title")
            display_info = f"{name} ({title})" if title else name
            uid = staff_member.get("id")
            if uid in finalized_user_ids:
                finalized_staff.append(display_info)
            elif uid in draft_user_ids:
                draft_staff.append(display_info)
            elif uid in unlocked_user_ids:
                unlocked_staff.append(display_info)
            else:
                missing_staff.append(display_info)
        # Add admin-created reports to section, using team_member or fallback
        admin_created_staff = []
        for r in admin_created_reports:
            member = r.get('team_member') or r.get('email') or r.get('user_id') or 'Unknown'
            admin_created_staff.append(str(member))
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"#### ✅ Finalized ({len(finalized_staff)})")
            for person in sorted(finalized_staff):
                st.markdown(f"- {person}")
        with col2:
            st.markdown(f"#### 📝 Draft ({len(draft_staff)})")
            for person in sorted(draft_staff):
                st.markdown(f"- {person}")
        with col3:
            st.markdown(f"#### ⏰ Unlocked ({len(unlocked_staff)})")
            for person in sorted(unlocked_staff):
                st.markdown(f"- {person}")
        with col4:
            st.markdown(f"#### 🏷️ Created by Admin ({len(admin_created_staff)})")
            for person in sorted(admin_created_staff):
                st.markdown(f"- {person}")
        st.markdown(f"#### ❌ Missing ({len(missing_staff)})")
        for person in sorted(missing_staff):
            st.markdown(f"- {person}")

    # Fetch saved summaries including creator info
    summaries_response = supabase.table('weekly_summaries').select('week_ending_date, summary_text, created_by').execute()
    saved_summaries_raw = {}
    if hasattr(summaries_response, 'data') and isinstance(summaries_response.data, list):
        for s in summaries_response.data:
            if isinstance(s, dict):
                saved_summaries_raw[s.get('week_ending_date')] = (s.get('summary_text'), s.get('created_by'))

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
    st.subheader("Generate or Regenerate Weekly Summary")
    selected_date_for_summary = st.selectbox("Select a week to summarize:", options=unique_dates)
    button_text = "Generate Weekly Summary Report"
    if selected_date_for_summary in saved_summaries:
        st.info("A summary for this week already exists. Generating a new one will overwrite it.")
        with st.expander("View existing saved summary"): st.markdown(clean_summary_response(saved_summaries[selected_date_for_summary]))
        button_text = "🔄 Regenerate Weekly Summary"
    if st.button(button_text):
        st.session_state['trigger_generate_summary'] = True

    if st.session_state.get('trigger_generate_summary'):
        # --- BEGIN summary generation logic (was inside button block) ---
        with st.spinner("🤖 Analyzing reports and generating comprehensive summary..."):
            try:
                weekly_reports = [r for r in all_reports if isinstance(r, dict) and r.get("week_ending_date") == selected_date_for_summary]
                st.session_state['debug_after_weekly_reports'] = True
                st.session_state['debug_after_draft_reports'] = True

                director_section = ""
                if not supervisor_mode:
                    director_section = """
- **### For the Director's Attention:** Create this section. List any items specifically noted under "Concerns for Director," making sure to mention which staff member raised the concern. If no concerns were raised, state "No specific concerns were raised for the Director this week."
"""

                # END OF draft_reports block
                st.session_state['debug_after_draft_reports_block'] = True

                # Check for saved weekly duty reports to integrate (filter by selected week)
                duty_reports_section = ""
                st.session_state['debug_after_duty_reports_section'] = True
                if 'weekly_duty_reports' not in st.session_state:
                    st.warning("No 'weekly_duty_reports' found in session state. Duty analysis integration skipped.")
                elif not st.session_state['weekly_duty_reports']:
                    st.warning("'weekly_duty_reports' in session state is empty. Duty analysis integration skipped.")
                else:
                    # Try to match on week_ending_date or date_range
                    filtered_duty_reports = []
                    for dr in st.session_state['weekly_duty_reports']:
                        week_match = False
                        dr_week = dr.get('week_ending_date')
                        debug_msg = ''
                        try:
                            # Allow ±1 day window for matching
                            if dr_week:
                                dr_date = pd.to_datetime(str(dr_week)).date()
                                summary_date = pd.to_datetime(str(selected_date_for_summary)).date()
                                diff_days = abs((dr_date - summary_date).days)
                                debug_msg = f"Duty analysis date: {dr_date}, summary week: {summary_date}, diff: {diff_days} days. "
                                if diff_days <= 1:
                                    week_match = True
                                    debug_msg += "INCLUDED (±1 day window)"
                                else:
                                    debug_msg += "NOT included (outside ±1 day window)"
                            elif dr.get('date_range'):
                                start, end = dr['date_range'].split(' to ')
                                start_date = pd.to_datetime(start).date()
                                end_date = pd.to_datetime(end).date()
                                summary_date = pd.to_datetime(str(selected_date_for_summary)).date()
                                debug_msg = f"Duty analysis date range: {start_date} to {end_date}, summary week: {summary_date}. "
                                if start_date <= summary_date <= end_date:
                                    week_match = True
                                    debug_msg += "INCLUDED (within date range)"
                                else:
                                    debug_msg += "NOT included (outside date range)"
                        except Exception as e:
                            debug_msg = f"ERROR parsing duty analysis date: {e}"
                        st.info(debug_msg)
                        if week_match:
                            filtered_duty_reports.append(dr)
                    if filtered_duty_reports:
                        st.success(f"🛡️ Duty analysis FOUND for this week. It will be included in the summary.")
                        duty_reports_section = "\n\n=== WEEKLY DUTY REPORTS INTEGRATION ===\n"
                        for i, duty_report in enumerate(filtered_duty_reports, 1):
                            duty_reports_section += f"\n--- DUTY REPORT {i} ---\n"
                            duty_reports_section += f"Generated: {duty_report.get('date_generated', 'N/A')}\n"
                            duty_reports_section += f"Date Range: {duty_report.get('date_range', 'N/A')}\n"
                            duty_reports_section += f"Reports Analyzed: {duty_report.get('reports_analyzed', 'N/A')}\n\n"
                            # Include full analysis_text if present, otherwise fallback to analysis or summary
                            if duty_report.get('analysis_text'):
                                duty_reports_section += duty_report.get('analysis_text')
                            elif duty_report.get('analysis'):
                                duty_reports_section += duty_report.get('analysis')
                            else:
                                duty_reports_section += duty_report.get('summary', '')
                            duty_reports_section += "\n" + "="*50 + "\n"
                        st.session_state['last_duty_reports_section'] = duty_reports_section
                    else:
                        st.warning("⚠️ No duty analysis found for this week. None will be included in the summary.")

                # Check for saved weekly engagement reports to integrate
                engagement_reports_section = ""
                st.session_state['debug_after_engagement_reports_section'] = True
                if 'weekly_engagement_reports' in st.session_state and st.session_state['weekly_engagement_reports']:
                    st.info("🎉 **Including Weekly Engagement Reports:** Found saved engagement analysis reports to integrate into this summary.")
                    engagement_reports_section = "\n\n=== WEEKLY ENGAGEMENT REPORTS INTEGRATION ===\n"
                    for i, engagement_report in enumerate(st.session_state['weekly_engagement_reports'], 1):
                        engagement_reports_section += f"\n--- ENGAGEMENT REPORT {i} ---\n"
                        engagement_reports_section += f"Generated: {engagement_report['date_generated']}\n"
                        engagement_reports_section += f"Date Range: {engagement_report['date_range']}\n"
                        engagement_reports_section += f"Events Analyzed: {engagement_report['events_analyzed']}\n\n"
                        engagement_reports_section += engagement_report['summary']
                        
                        # Include upcoming events if available
                        if engagement_report.get('upcoming_events'):
                            engagement_reports_section += f"\n\n--- UPCOMING EVENTS ---\n"
                            engagement_reports_section += engagement_report['upcoming_events']
                        
                        engagement_reports_section += "\n" + "="*50 + "\n"

                st.session_state['debug_after_reports_text'] = True
                # Calculate average_score for the week
                well_being_scores = [r.get("well_being_rating") for r in weekly_reports if r.get("well_being_rating") is not None]
                average_score = round(sum(well_being_scores) / len(well_being_scores), 1) if well_being_scores else "N/A"

                # Build reports_text from weekly_reports
                reports_text = ""
                for r in weekly_reports:
                    team_member = r.get("team_member", "Unknown")
                    well_being = r.get("well_being_rating", "N/A")
                    report_body = r.get("report_body", {})
                    reports_text += f"\n---\n**Report from: {team_member}**\n"
                    reports_text += f"Well-being Score: {well_being}/5\n"
                    for section, section_data in report_body.items():
                        if section_data:
                            successes = section_data.get("successes", [])
                            challenges = section_data.get("challenges", [])
                            if successes:
                                reports_text += f"- {section} Successes:\n"
                                for s in successes:
                                    text = s.get("text", "") if isinstance(s, dict) else str(s)
                                    reports_text += f"    - {text}\n"
                            if challenges:
                                reports_text += f"- {section} Challenges:\n"
                                for c in challenges:
                                    text = c.get("text", "") if isinstance(c, dict) else str(c)
                                    reports_text += f"    - {text}\n"
                    reports_text += "\n"

                st.info("DEBUG: Entered dashboard summary generation block (before AI call)")
                print("DEBUG: Entered dashboard summary generation block (before AI call)")
                st.session_state['debug_about_to_call_ai_summary'] = True
                st.info("🟢 Generating a new admin dashboard summary with Gemini AI...")
                print("DEBUG: About to call generate_admin_dashboard_summary...")
                st.info("DEBUG: About to call generate_admin_dashboard_summary...")
                try:
                    with st.spinner("AI is generating the admin dashboard summary..."):
                        from src.ai import generate_admin_dashboard_summary
                        cleaned_text = generate_admin_dashboard_summary(
                            selected_date_for_summary=selected_date_for_summary,
                            staff_reports_text=reports_text,
                            duty_reports_section=duty_reports_section,
                            engagement_reports_section=engagement_reports_section,
                            average_score=average_score
                        )
                    print(f"DEBUG: Returned from generate_admin_dashboard_summary. cleaned_text: {repr(cleaned_text)}")
                    st.info(f"DEBUG: Returned from generate_admin_dashboard_summary. cleaned_text: {repr(cleaned_text)}")
                except Exception as exc:
                    print(f"EXCEPTION in generate_admin_dashboard_summary: {exc}")
                    st.error(f"EXCEPTION in generate_admin_dashboard_summary: {exc}")
                    cleaned_text = None
                if not cleaned_text or not str(cleaned_text).strip():
                    st.error("❌ No summary was generated. The AI may have returned an empty response or an error occurred. Please check your input data and try again.")
                    print("DEBUG: cleaned_text is empty or None after AI call.")
                elif str(cleaned_text).strip().lower().startswith("error:") or str(cleaned_text).strip().lower().startswith("ai error:"):
                    st.error(f"❌ {cleaned_text}")
                    print(f"DEBUG: cleaned_text is error: {repr(cleaned_text)}")
                else:
                    st.success("✅ Summary generated successfully.")
                    print(f"DEBUG: cleaned_text is valid summary: {repr(cleaned_text)}")
                print(f"DEBUG: Setting st.session_state['last_summary'] to: {{'date': {selected_date_for_summary}, 'text': {repr(cleaned_text)}}}")
                st.session_state['last_summary'] = {"date": selected_date_for_summary, "text": cleaned_text}
                # Fallback: If no Streamlit message was shown, show a generic error
                if not cleaned_text or not str(cleaned_text).strip():
                    st.error("❌ Fallback: No summary or debug output was generated. There may be a silent failure in the AI call or Streamlit UI. Please check logs and input data.")
            except Exception as e:
                st.error(f"An error occurred while generating the summary: {e}")

        # --- END summary generation logic ---
    if "last_summary" in st.session_state:
        summary_data = st.session_state["last_summary"]
        if summary_data.get("date") == selected_date_for_summary:
            st.markdown("---")
            st.subheader("Raw Duty Analysis Section Preview")
            # Show the raw duty_reports_section that was sent to the AI
            duty_preview = st.session_state.get('last_duty_reports_section', None)
            if duty_preview:
                st.code(duty_preview, language="markdown")
            else:
                st.info("No duty analysis section was generated for this summary.")

            st.subheader("Generated Summary (Editable)")
            # Warn if the AI output does not contain the required section
            summary_text = summary_data.get("text") or ""
            if "Operational & Safety Summary" not in summary_text:
                st.warning("⚠️ The AI output does not contain the 'Operational & Safety Summary' section. Please review the prompt and summary.")
            with st.form("save_summary_form"):
                edited_summary = st.text_area("Edit Summary:", value=summary_text, height=400)
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
                    except Exception as e:
                        st.error(f"Failed to generate summary: {e}")




