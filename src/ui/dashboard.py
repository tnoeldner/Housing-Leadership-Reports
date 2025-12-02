import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime, timedelta
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

        # Use RPC to fetch finalized reports for this supervisor (works with RLS)
        rpc_resp = supabase.rpc('get_finalized_reports_for_supervisor', {'sup_id': current_user_id}).execute()
        rpc_data = getattr(rpc_resp, 'data', None)
        if not isinstance(rpc_data, list):
            rpc_data = []
        all_reports = [r for r in rpc_data if isinstance(r, dict)]

        st.caption(f"Found {len(all_reports)} finalized report(s) for your direct reports.")

        # Get staff records for display (only the supervisor's direct reports)
        all_staff_response = supabase.table('profiles').select('*').in_('id', direct_report_ids).execute()
        staff_data = getattr(all_staff_response, "data", None)
        if not isinstance(staff_data, list):
            staff_data = []
        all_staff = [s for s in staff_data if isinstance(s, dict)]

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

    st.divider()
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
    st.subheader("Unlock Submitted Reports")
    
    # Only show for admin, not supervisor
    if not supervisor_mode:
        st.write("Unlock finalized reports to allow staff to make edits before the deadline.")
        
        # Get all finalized reports for the selected week
        # Fetch ALL reports to get comprehensive date list using admin client to bypass RLS
        all_reports_response = admin_supabase.table("reports").select("*").order("created_at", desc=True).execute()
        all_reports_comprehensive = getattr(all_reports_response, "data", None) or []
        
        # Use all report dates, not just those visible in current view
        all_report_dates = [r.get("week_ending_date") for r in all_reports_comprehensive if r.get("week_ending_date")]
        all_unique_dates = sorted(list(set([d for d in all_report_dates if d is not None])), reverse=True)
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
                                admin_supabase.table("reports").update({"status": "draft"}).eq("id", report.get('id')).execute()
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
                            admin_supabase.table("reports").update({"status": "draft"}).eq("week_ending_date", unlock_week).eq("status", "finalized").execute()
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
        all_reports_response = admin_supabase.table("reports").select("*").order("created_at", desc=True).execute()
        all_reports_including_drafts = getattr(all_reports_response, "data", None) or []
        
        # ...existing code...
        
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
            deadline_info = calculate_deadline_info(draft_unlock_week, admin_supabase)
            deadline_passed = deadline_info["deadline_passed"]
            
            # Get all draft reports for this week, including admin-created and status 'admin created'
            draft_reports = [
                r for r in all_reports_including_drafts
                if r.get("week_ending_date") == draft_unlock_week and r.get("status") in ["draft", "admin created"]
            ]
            
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
                                        "admin_note": f"Submission enabled by administrator after deadline. Enabled on {datetime.now().astimezone(get_central_tz()).strftime('%Y-%m-%d %H:%M:%S')}"
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
                                    "admin_note": f"Submission enabled by administrator after deadline. Bulk enabled on {datetime.now().astimezone(get_central_tz()).strftime('%Y-%m-%d %H:%M:%S')}"
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
        deadline_config = get_deadline_settings(admin_supabase)
        
        # Get all unique dates from all reports for missed deadline management
        all_report_dates = [r.get("week_ending_date") for r in all_reports if isinstance(r, dict) and r.get("week_ending_date")]
        all_unique_dates = sorted([d for d in set(all_report_dates) if d is not None], reverse=True)
        missed_week = st.selectbox("Select week with missed deadlines:", options=all_unique_dates, key="missed_deadline_week")
        if missed_week:
            # Get all profiles to check against
            profiles_response = admin_supabase.table("profiles").select("*").execute()
            all_staff = profiles_response.data if hasattr(profiles_response, 'data') and isinstance(profiles_response.data, list) else []

            # Get all reports for this week (any status)
            all_reports_response = admin_supabase.table("reports").select("user_id, status").eq("week_ending_date", missed_week).execute()
            all_reports_for_week = all_reports_response.data if hasattr(all_reports_response, 'data') and isinstance(all_reports_response.data, list) else []
            finalized_user_ids = {str(r.get("user_id")) for r in all_reports_for_week if isinstance(r, dict) and r.get("status") == "finalized" and r.get("user_id") is not None}
            draft_user_ids = {str(r.get("user_id")) for r in all_reports_for_week if isinstance(r, dict) and r.get("status") == "draft" and r.get("user_id") is not None}
            all_user_ids_with_report = {str(r.get("user_id")) for r in all_reports_for_week if isinstance(r, dict) and r.get("user_id") is not None}

            finalized_staff = [s for s in all_staff if isinstance(s, dict) and str(s.get("id")) in finalized_user_ids and s.get("role") != "admin"]
            draft_staff = [s for s in all_staff if isinstance(s, dict) and str(s.get("id")) in draft_user_ids and s.get("role") != "admin"]
            # Only consider staff missing if they do not have a finalized or draft report for the week
            missing_staff = [s for s in all_staff if isinstance(s, dict) and str(s.get("id")) not in finalized_user_ids and str(s.get("id")) not in draft_user_ids and s.get("role") != "admin"]

            st.info(f"Submission status for {missed_week}:")
            with st.expander("✅ Finalized Reports"):
                for staff in finalized_staff:
                    st.write(f"- {staff.get('full_name') or staff.get('email')}")
            with st.expander("📝 Draft Reports"):
                for staff in draft_staff:
                    st.write(f"- {staff.get('full_name') or staff.get('email')}")
            with st.expander("❌ No Report Started"):
                for staff in missing_staff:
                    st.write(f"- {staff.get('full_name') or staff.get('email')}")

            st.divider()
            if missing_staff:
                if st.button(f"📝 Create Empty Reports for All {len(missing_staff)} Missing Staff", type="secondary"):
                    try:
                        bulk_reports = []
                        for staff in missing_staff:
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
                                "status": "draft",
                                "created_by_admin": st.session_state["user"].id,
                                "admin_note": f"Report created by administrator due to missed deadline. Created on {datetime.now().astimezone(get_central_tz()).strftime('%Y-%m-%d %H:%M:%S')}"
                            }
                            bulk_reports.append(empty_report)
                        if bulk_reports:
                            admin_supabase.table("reports").insert(bulk_reports).execute()
                            st.success(f"Empty reports created for {len(bulk_reports)} staff members!")
                            time.sleep(2)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create bulk reports: {e}")

    st.divider()
    st.subheader("Generate or Regenerate Weekly Summary")
    selected_date_for_summary = st.selectbox("Select a week to summarize:", options=unique_dates)
    button_text = "Generate Weekly Summary Report"
    if selected_date_for_summary in saved_summaries:
        st.info("A summary for this week already exists. Generating a new one will overwrite it.")
        with st.expander("View existing saved summary"): st.markdown(clean_summary_response(saved_summaries[selected_date_for_summary]))
        button_text = "🔄 Regenerate Weekly Summary"
    if st.button(button_text):

        with st.spinner("🤖 Analyzing reports and generating comprehensive summary..."):
            try:
                weekly_reports = [r for r in all_reports if isinstance(r, dict) and r.get("week_ending_date") == selected_date_for_summary]
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
                            name = report.get('team_member', 'Unknown')
                            if report.get('created_by_admin'):
                                name += " (Admin Created)"
                            st.write(f"**{name}**")
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
                                            "admin_note": f"Submission enabled by administrator after deadline. Enabled on {datetime.now().astimezone(get_central_tz()).strftime('%Y-%m-%d %H:%M:%S')}"
                                        }).eq("id", report.get('id')).execute()
                                        st.success(f"Submission enabled for {report.get('team_member')}! They can now finalize their report.")
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to enable submission: {e}")
                            else:
                                st.write("✅ Can submit")

                    director_section = ""
                    if not supervisor_mode:
                        director_section = """
- **### For the Director's Attention:** Create this section. List any items specifically noted under "Concerns for Director," making sure to mention which staff member raised the concern. If no concerns were raised, state "No specific concerns were raised for the Director this week."
"""

                    # Check for saved weekly duty reports to integrate (filter by selected week)
                    duty_reports_section = ""
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
                                duty_reports_section += duty_report.get('summary', '')
                                duty_reports_section += "\n" + "="*50 + "\n"
                        else:
                            st.warning("⚠️ No duty analysis found for this week. None will be included in the summary.")
                    else:
                        st.info("ℹ️ No duty analyses are loaded in session. None will be included in the summary.")

                    # Check for saved weekly engagement reports to integrate
                    engagement_reports_section = ""
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

                    from src.ai import generate_admin_dashboard_summary
                    cleaned_text = generate_admin_dashboard_summary(
                        selected_date_for_summary=selected_date_for_summary,
                        reports_text=reports_text,
                        duty_reports_section=duty_reports_section,
                        engagement_reports_section=engagement_reports_section,
                        average_score=average_score
                    )
                    st.session_state['last_summary'] = {"date": selected_date_for_summary, "text": cleaned_text}; st.rerun()
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
                    except Exception as e:
                        st.error(f"Failed to generate summary: {e}")




