import streamlit as st
from datetime import datetime, timedelta
from src.database import supabase, get_admin_client
from src.ai import summarize_form_submissions, create_duty_report_summary, clean_summary_response
from src.config import CORE_SECTIONS
from src.roompact import (
    fetch_roompact_forms, 
    filter_forms_by_date_and_type, 
    discover_form_types,
    get_roompact_config,
    make_roompact_request
)
from src.weekly_report import create_weekly_duty_report_summary

def supervisor_summaries_page():
    st.title("My Saved Team Summaries")
    st.write("Saved summaries you've generated for your team.")
    try:
        resp = supabase.rpc('get_supervisor_summaries', {'p_super': st.session_state['user'].id}).execute()
        summaries = resp.data if isinstance(resp.data, list) else []
        if not summaries:
            st.info("You have no saved team summaries yet.")
            return
        for s in summaries:
            if isinstance(s, dict):
                with st.expander(f"Week Ending {s.get('week_ending_date', 'Unknown')} — Saved {s.get('created_at', 'Unknown')}"):
                    st.markdown(clean_summary_response(s.get('summary_text', '')))
    except Exception as e:
        st.error(f"Failed to fetch supervisor summaries: {e}")

def supervisors_section_page():
    """Page for supervisors to view and analyze Roompact form submissions"""
    st.title("📋 Supervisors Section - Form Analysis")
    st.markdown("""
    This section provides specialized analysis tools for reviewing form submissions 
    and generating AI-powered summaries with actionable insights.
    """)
    
    # Create tabs for the analysis sections
    tab1, tab2, tab3, tab4 = st.tabs(["🛡️ Duty Analysis", "📊 General Form Analysis", "📋 Individual Reports", "📝 Weekly Reports"])
    
    with tab1:
        duty_analysis_section()
    
    with tab2:
        general_form_analysis_section()
    
    with tab3:
        individual_reports_viewer()
        
    with tab4:
        weekly_reports_viewer()

def weekly_reports_viewer():
    """View and filter weekly reports submitted via the app"""
    st.subheader("📝 Weekly Reports Viewer")
    st.markdown("""
    View weekly reports submitted by staff members through the application.
    """)
    
    # Filter controls
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input(
            "📅 Start Date",
            value=datetime.now().date() - timedelta(days=30),
            help="View reports from this date forward",
            key="weekly_start_date"
        )
    
    with col2:
        end_date = st.date_input(
            "📅 End Date",
            value=datetime.now().date(),
            help="View reports up to this date",
            key="weekly_end_date"
        )
    
    # Fetch button
    if st.button("🔄 Fetch Weekly Reports", type="primary", key="fetch_weekly_reports"):
        with st.spinner("Fetching reports from database..."):
            try:
                # Check if user is admin - if so, use admin client to bypass RLS
                role = st.session_state.get('role', 'staff')
                
                if role == 'admin':
                    try:
                        admin_client = get_admin_client()
                        db_client = admin_client
                    except Exception as e:
                        st.error(f"Failed to get admin client: {e}")
                        db_client = supabase
                else:
                    db_client = supabase
                
                # Fetch reports with date filter
                response = db_client.table("reports") \
                    .select("*") \
                    .gte("week_ending_date", start_date.isoformat()) \
                    .lte("week_ending_date", end_date.isoformat()) \
                    .order("week_ending_date", desc=True) \
                    .execute()
                
                reports = response.data or []
                
                if not reports:
                    st.warning("No reports found in the selected date range.")
                    return
                
                st.success(f"✅ Found {len(reports)} reports")
                
                # Group by week ending date
                reports_by_week = {}
                for report in reports:
                    if isinstance(report, dict):
                        week = report.get('week_ending_date')
                        if week not in reports_by_week:
                            reports_by_week[week] = []
                        reports_by_week[week].append(report)
                
                # Display reports
                for week, week_reports in reports_by_week.items():
                    with st.expander(f"Week Ending {week} ({len(week_reports)} reports)", expanded=False):
                        # Create grid layout (3 columns)
                        cols = st.columns(3)
            
                        for i, report in enumerate(week_reports):
                            with cols[i % 3]:
                                name = report.get('team_member', 'Unknown') if isinstance(report, dict) else 'Unknown'
                                status = report.get('status', 'draft').capitalize() if isinstance(report, dict) else 'Draft'
                    
                                with st.container(border=True):
                                    st.markdown(f"#### {name}")
                        
                                    # Status Badge
                                    status_lower = status.lower()
                                    status_class = "status-submitted" if status_lower == "finalized" else ("status-approved" if status_lower == "approved" else "status-draft")
                                    st.markdown(f'<div style="margin-bottom: 1rem;"><span class="status-badge {status_class}">{status}</span></div>', unsafe_allow_html=True)
                        
                                    # Well-being Metric
                                    if report.get('well_being_rating'):
                                        st.metric("Well-being", f"{report.get('well_being_rating')}/5")
                        
                                    # AI Summary Snippet
                                    summary = report.get('individual_summary') if isinstance(report, dict) else None
                                    clean_sum = None
                                    if summary:
                                        clean_sum = clean_summary_response(summary)
                                        snippet = clean_sum[:150] + "..." if len(clean_sum) > 150 else clean_sum
                                        st.info(snippet)
                        
                                    # View Details
                                    with st.expander("View Full Report"):
                                        # Full AI Summary
                                        if clean_sum:
                                            st.markdown("##### 🤖 AI Summary")
                                            st.markdown(clean_sum)
                                        # Director Concerns
                                        if isinstance(report, dict) and report.get('director_concerns'):
                                            st.error(f"**⚠️ Director Concerns:**\n{report.get('director_concerns')}")
                            
                                        # General Updates
                                        st.markdown("##### 📝 General Updates")
                                        st.markdown(f"**Professional Development:**\n{report.get('professional_development', 'None') if isinstance(report, dict) else 'None'}")
                                        st.markdown(f"**Lookahead:**\n{report.get('key_topics_lookahead', 'None') if isinstance(report, dict) else 'None'}")
                                        st.markdown(f"**Personal Check-in:**\n{report.get('personal_check_in', 'None') if isinstance(report, dict) else 'None'}")
                            
                                        st.markdown("---")
                                        st.markdown("##### 🎯 Core Activities")
                            
                                        # Report Body
                                        body = report.get('report_body', {}) if isinstance(report, dict) else {}
                            
                                        for section_key, section_name in CORE_SECTIONS.items():
                                            section_data = body.get(section_key, {}) if isinstance(body, dict) else {}
                                            if section_data and (section_data.get('successes') or section_data.get('challenges')):
                                                st.markdown(f"**{section_name}**")
                                                if section_data.get('successes'):
                                                    st.markdown("*Successes:*")
                                                    for item in section_data['successes']:
                                                        if isinstance(item, dict):
                                                            text = item.get('text', '')
                                                            ascend = item.get('ascend_category', 'N/A')
                                                            north = item.get('north_category', 'N/A')
                                                            st.markdown(f"- {text} `(ASCEND: {ascend}, NORTH: {north})`")
                                                if section_data.get('challenges'):
                                                    st.markdown("*Challenges:*")
                                                    for item in section_data['challenges']:
                                                        if isinstance(item, dict):
                                                            text = item.get('text', '')
                                                            ascend = item.get('ascend_category', 'N/A')
                                                            north = item.get('north_category', 'N/A')
                                                            st.markdown(f"- {text} `(ASCEND: {ascend}, NORTH: {north})`")
                                                st.markdown("")
                                        # --- Response Option ---
                                        # Only show for finalized reports
                                        if status_lower == "finalized":
                                            comment_key = f"comment_{report.get('id', '')}_{week}"
                                            comment = st.text_area("Add your comment:", key=comment_key)
                                            if st.button("Respond with Comments (Email)", key=f"respond_{report.get('id', '')}_{week}", help="Email this report and your comment to the author"):
                                                staff_email = report.get('email')
                                                st.write(f"[DEBUG] Staff email: {staff_email}")
                                                if not staff_email:
                                                    st.error("Could not find staff email address.")
                                                else:
                                                    sender_name = st.session_state['user'].get('full_name', 'Supervisor/Admin')
                                                    subject = f"Weekly Report Response for {week} from {sender_name}"
                                                    body = f"Hello {report.get('team_member', 'Staff')},\n\nYour weekly report for {week} is below.\n\nResponse Comments:\n{comment}\n\nReport Content:\n{json.dumps(report.get('report_body', {}), indent=2)}"
                                                    st.write(f"[DEBUG] Sending email to: {staff_email}, subject: {subject}")
                                                    try:
                                                        with st.spinner("Sending email..."):
                                                            from src.ui.dashboard import send_email
                                                            success = send_email(staff_email, subject, body)
                                                        st.write(f"[DEBUG] send_email returned: {success}")
                                                        if success:
                                                            st.success(f"Email sent to {staff_email}")
                                                        else:
                                                            st.error("Failed to send email.")
                                                    except Exception as e:
                                                        st.error(f"Exception during email send: {e}")
            
            except Exception as e:
                st.error(f"Error fetching reports: {str(e)}")

def duty_analysis_section():
    """Specialized section for duty report analysis"""
    st.subheader("🛡️ Duty Analysis")
    st.markdown("""
    **Focus:** Analyze specific duty reports from Resident Assistants, Community Assistants, RDs, and RMs.  
    **Purpose:** Monitor daily operations, incidents, and staff performance during duty shifts.
    """)
    
    # Predefined duty form types - exact names from Roompact
    DUTY_FORM_TYPES = [
        "Resident Assistant Duty",
        "Resident Assistant Duty Report",
        "CA Duty",
        "Community Assistant Duty Report",
        "RD Duty",
        "RD Duty Report",
        "Resident Manager Duty",
        "Resident Manager Duty Report",
        "RM Duty Report"
    ]
    
    # Date range selection for duty analysis
    col1, col2 = st.columns(2)
    
    with col1:
        duty_start_date = st.date_input(
            "📅 Start Date",
            value=datetime.now().date() - timedelta(days=30),
            help="Analyze duty reports from this date forward",
            key="duty_start_date"
        )
    
    with col2:
        duty_end_date = st.date_input(
            "📅 End Date", 
            value=datetime.now().date(),
            help="Analyze duty reports up to this date",
            key="duty_end_date"
        )
    
    st.info(f"📊 **Target Analysis:** {', '.join(DUTY_FORM_TYPES)} from {duty_start_date} to {duty_end_date}")
    
    # Fetch duty reports button
    if st.button("🔄 Fetch Duty Reports", type="primary", key="fetch_duty_reports"):
        with st.spinner("Fetching duty reports from Roompact..."):
            # Calculate page limit based on realistic data patterns
            # IMPORTANT: Roompact API does NOT support date filtering
            # We must paginate through ALL forms until we reach the target date
            days_back = (datetime.now().date() - duty_start_date).days
            
            # Much higher page limits since we can't filter by date in the API
            # We need to paginate through all recent forms to reach historical data
            if days_back > 90:
                max_pages = 500  # 3+ months - need many pages
            elif days_back > 60:
                max_pages = 400  # 2+ months
            elif days_back > 30:
                max_pages = 300  # 1+ months
            elif days_back > 14:
                max_pages = 200  # 2+ weeks
            else:
                max_pages = 100  # Recent data
            
            st.info(f"📊 Searching up to {max_pages} pages for duty reports going back {days_back} days to {duty_start_date}")
            st.info(f"📈 **Note:** API returns newest forms first - may need to fetch many pages to reach {duty_start_date}")
            
            progress_placeholder = st.empty()
            
            def show_duty_progress(page_num, total_forms, oldest_date, reached_target):
                status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
                if oldest_date != "Unknown":
                    status += f" | Oldest: {oldest_date}"
                if reached_target:
                    status += f" | ✅ Reached {duty_start_date}"
                progress_placeholder.info(status)
            
            all_forms = fetch_roompact_forms(
                max_pages=max_pages,
                target_start_date=duty_start_date,
                progress_callback=show_duty_progress
            )
            
            if not all_forms:
                st.warning("No forms found.")
                return
            
            # Debug: Show what was fetched BEFORE filtering
            raw_form_dates = []
            for form in all_forms:
                current_revision = form.get('current_revision', {})
                date_str = current_revision.get('date', '')
                if date_str:
                    try:
                        form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        raw_form_dates.append(form_datetime)
                    except:
                        pass
            
            if raw_form_dates:
                raw_oldest = min(raw_form_dates).strftime('%Y-%m-%d %H:%M')
                raw_newest = max(raw_form_dates).strftime('%Y-%m-%d %H:%M')
                st.info(f"📦 **Fetched {len(all_forms)} unique forms** (after deduplication)")
                st.info(f"📅 **Raw Data Range:** {raw_oldest} to {raw_newest}")
            else:
                st.info(f"📦 **Fetched {len(all_forms)} total forms from Roompact API**")
            
            # Filter for duty reports only
            duty_forms, filter_error = filter_forms_by_date_and_type(
                all_forms, duty_start_date, duty_end_date, DUTY_FORM_TYPES
            )
            
            if filter_error:
                st.error(f"Error filtering duty reports: {filter_error}")
                return
            
            # Show filtered results
            if duty_forms:
                duty_dates = []
                for form in duty_forms:
                    current_revision = form.get('current_revision', {})
                    date_str = current_revision.get('date', '')
                    if date_str:
                        try:
                            form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            duty_dates.append(form_datetime)
                        except:
                            pass
                
                if duty_dates:
                    duty_oldest = min(duty_dates).strftime('%Y-%m-%d')
                    duty_newest = max(duty_dates).strftime('%Y-%m-%d')
                    st.success(f"✅ **Found {len(duty_forms)} duty reports** from {duty_oldest} to {duty_newest}")
            else:
                st.warning(f"⚠️ No duty reports found in date range {duty_start_date} to {duty_end_date}")
            
            # Store duty forms in session state
            st.session_state['duty_forms'] = duty_forms
            st.session_state['duty_filter_info'] = {
                'start_date': duty_start_date,
                'end_date': duty_end_date,
                'form_types': DUTY_FORM_TYPES,
                'total_fetched': len(all_forms),
                'filtered_count': len(duty_forms)
            }
            
            if duty_forms:
                st.success(f"✅ Found {len(duty_forms)} duty reports in the selected date range")
            else:
                st.warning("No duty reports found matching your criteria")
    
    # Show analysis options if duty forms are available in session state
    if 'duty_forms' in st.session_state and st.session_state['duty_forms']:
        st.markdown("---")
        st.subheader("📊 Analysis Options")

        duty_forms = st.session_state['duty_forms']
        filter_info = st.session_state.get('duty_filter_info', {})

        st.info(f"**Loaded:** {len(duty_forms)} duty reports from {filter_info.get('start_date')} to {filter_info.get('end_date')}")

        # Group reports by type, show submitter names and dates under each type
        from collections import defaultdict
        grouped = defaultdict(list)
        for idx, form in enumerate(duty_forms):
            form_type = form.get('form_template_name', 'Unknown Form')
            author = form.get('current_revision', {}).get('author', 'Unknown')
            date = form.get('current_revision', {}).get('date', 'Unknown')
            grouped[form_type].append((idx, author, date))

        st.markdown("**Select duty reports to analyze:**")
        selected_indices = []
        for form_type, items in grouped.items():
            with st.expander(f"{form_type} ({len(items)})"):
                for idx, author, date in items:
                    label = f"{author} — {date}"
                    if st.checkbox(label, value=True, key=f"select_{form_type}_{idx}"):
                        selected_indices.append(idx)
        selected_forms = [duty_forms[idx] for idx in selected_indices]

        # Analysis type selection
        analysis_type = st.radio(
            "Select Analysis Type:",
            ["📊 Standard Analysis", "📅 Weekly Report Analysis"],
            key="duty_analysis_type"
        )

        # Persist analysis and selection in session_state
        if st.button("🤖 Generate Analysis", type="primary", key="generate_duty_analysis"):
            if not selected_forms:
                st.warning("Please select at least one duty report to analyze.")
                return
            st.session_state['analysis_type'] = analysis_type
            st.session_state['selected_forms'] = selected_forms
            st.session_state['filter_info'] = filter_info
            if analysis_type == "📊 Standard Analysis":
                with st.spinner("Generating standard duty report analysis..."):
                    result = create_duty_report_summary(
                        selected_forms,
                        filter_info.get('start_date'),
                        filter_info.get('end_date')
                    )
                    summary = result.get('summary', "Failed to generate analysis")
                    st.session_state['last_weekly_analysis'] = summary
            else:
                with st.spinner("Generating weekly duty report summary..."):
                    result = create_weekly_duty_report_summary(
                        selected_forms,
                        filter_info.get('start_date'),
                        filter_info.get('end_date')
                    )
                    summary = result.get('summary', result) if isinstance(result, dict) else result
                    st.session_state['last_weekly_analysis'] = summary

        # Always show the last generated analysis if present
        if 'last_weekly_analysis' in st.session_state:
            analysis_type = st.session_state.get('analysis_type', analysis_type)
            selected_forms = st.session_state.get('selected_forms', selected_forms)
            filter_info = st.session_state.get('filter_info', filter_info)
            summary = st.session_state['last_weekly_analysis']
            if analysis_type == "📊 Standard Analysis":
                st.markdown("### 📊 Duty Report Analysis")
            else:
                st.markdown("### 📅 Weekly Duty Report Summary")
            st.markdown(summary)
            st.download_button(
                label="📥 Download Analysis" if analysis_type == "📊 Standard Analysis" else "📥 Download Weekly Report",
                data=summary,
                file_name=f"{'duty_analysis' if analysis_type == '📊 Standard Analysis' else 'weekly_duty_report'}_{filter_info.get('start_date')}_{filter_info.get('end_date')}.md",
                mime="text/markdown"
            )
            # Save button for analysis
            if analysis_type == "📊 Standard Analysis":
                if st.button("💾 Save Analysis", key="save_duty_analysis"):
                    from src.database import save_duty_analysis
                    user = st.session_state.get('user')
                    user_id = getattr(user, 'id', 'Unknown') if user else 'Unknown'
                    analysis_data = {
                        'report_type': '📊 Standard Analysis',
                        'filter_info': filter_info,
                        'selected_forms': selected_forms,
                        'all_selected_forms': selected_forms,
                        'summary': summary
                    }
                    week_ending = filter_info.get('end_date')
                    # Convert date fields to ISO strings if needed
                    if hasattr(week_ending, 'isoformat'):
                        week_ending = week_ending.isoformat()
                    if 'start_date' in filter_info and hasattr(filter_info['start_date'], 'isoformat'):
                        analysis_data['filter_info']['start_date'] = filter_info['start_date'].isoformat()
                    if 'end_date' in filter_info and hasattr(filter_info['end_date'], 'isoformat'):
                        analysis_data['filter_info']['end_date'] = filter_info['end_date'].isoformat()
                    # Use admin client for admins
                    role = st.session_state.get('role', 'staff')
                    if role == 'admin':
                        admin_client = get_admin_client()
                        db_client = admin_client
                    else:
                        db_client = None
                    result = save_duty_analysis(analysis_data, week_ending_date=week_ending, created_by_user_id=user_id, db_client=db_client)
                    st.session_state['last_save_result'] = result
                    if result.get('success'):
                        st.success(result.get('message', 'Duty analysis saved.'))
                    else:
                        st.error(result.get('message', 'Failed to save duty analysis.'))
            else:
                if st.button("💾 Save Weekly Duty Analysis", key="save_weekly_duty_analysis"):
                    from src.database import save_duty_analysis
                    user = st.session_state.get('user')
                    user_id = getattr(user, 'id', 'Unknown') if user else 'Unknown'
                    analysis_data = {
                        'report_type': '📅 Weekly Summary Report',
                        'filter_info': filter_info,
                        'selected_forms': selected_forms,
                        'all_selected_forms': selected_forms,
                        'summary': summary
                    }
                    week_ending = filter_info.get('end_date')
                    # Use admin client for admins
                    role = st.session_state.get('role', 'staff')
                    if role == 'admin':
                        admin_client = get_admin_client()
                        db_client = admin_client
                    else:
                        db_client = None
                    result = save_duty_analysis(analysis_data, week_ending_date=week_ending, created_by_user_id=user_id, db_client=db_client)
                    st.session_state['last_save_result'] = result
                    if result.get('success'):
                        st.success(result.get('message', 'Duty analysis saved.'))
                    else:
                        st.error(result.get('message', 'Failed to save duty analysis.'))
            # Show debug info if available
            if 'last_save_result' in st.session_state:
                st.markdown("**Debug Save Result:**")
                st.write(st.session_state['last_save_result'])


def engagement_analysis_section():
    """Specialized section for Residence Life Event Submission analysis - Full Semester Management"""
    st.subheader("🎉 Engagement Analysis - Fall Semester")
    st.markdown("""
    **Focus:** Complete Fall semester event lifecycle management (Aug 22 - Dec 31, 2025)  
    **Purpose:** Track all event submissions from proposal to completion with status updates and weekly analysis.
    **Data Management:** Fetches ALL event submissions and updates existing records as events progress through approval/completion.
    """)
    
    # Predefined engagement form type
    ENGAGEMENT_FORM_TYPE = "Residence Life Event Submission"
    
    # Academic year info display
    st.info("🏫 **Academic Year Management:** Event submissions from August 1, 2025 onward will be fetched and synchronized with the engagement database. Events are tracked uniquely throughout their lifecycle from proposal to completion.")
    
    # Fetch ALL engagement forms button (with August 1, 2025 target date)
    if st.button("🔄 Fetch All Event Submissions", type="primary", key="fetch_all_engagement_forms"):
        with st.spinner("Fetching event submissions from Roompact since August 1, 2025..."):
            # Use comprehensive page limit for academic year data
            max_pages = 1200  # Generous limit to capture academic year
            # Set target date to August 1, 2025 to limit how far back we go
            target_start_date = datetime(2025, 8, 1).date()
            
            st.info(f"📊 **Academic Year Sync:** Fetching event submissions from August 1, 2025 to present (up to {max_pages} pages)")
            st.warning(f"⏳ **Comprehensive Search:** This may take 2-4 minutes to fetch and process event submissions")
            
            progress_placeholder = st.empty()
            
            def show_engagement_progress(page_num, total_forms, oldest_date, reached_target):
                status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
                if oldest_date != "Unknown":
                    status += f" | Oldest: {oldest_date}"
                if reached_target:
                    status += " | ✅ August 1, 2025 reached"
                progress_placeholder.info(status)
            
            # Fetch forms with August 1, 2025 as target start date
            all_forms = fetch_roompact_forms(
                max_pages=max_pages,
                target_start_date=target_start_date,  # Stop at August 1, 2025
                progress_callback=show_engagement_progress
            )
            
            # Removed undefined error variable handling
            
            if not all_forms:
                st.warning("No forms found.")
                return
            
            # Filter for engagement forms only (no date filtering)
            engagement_forms = []
            for form in all_forms:
                if form.get('form_template_name') == ENGAGEMENT_FORM_TYPE:
                    engagement_forms.append(form)
            
            # Show comprehensive data statistics
            if all_forms:
                form_dates = []
                engagement_dates = []
                
                for form in engagement_forms:
                    current_revision = form.get('current_revision', {})
                    date_str = current_revision.get('date', '')
                    if date_str:
                        try:
                            form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            engagement_dates.append(form_datetime)
                        except:
                            pass
                
                if engagement_dates:
                    oldest_engagement = min(engagement_dates).strftime('%Y-%m-%d')
                    newest_engagement = max(engagement_dates).strftime('%Y-%m-%d')
                    st.success(f"📅 **Event Submissions Range:** {oldest_engagement} to {newest_engagement}")
                else:
                    st.info("📅 **No date information** available in retrieved forms")
            
            # Store engagement forms in session state
            st.session_state['engagement_forms'] = engagement_forms
            st.session_state['engagement_filter_info'] = {
                'start_date': datetime(2025, 8, 1).date(),  # Academic year start (Aug 1, 2025)
                'end_date': datetime.now().date(),   # Current date (latest submissions)
                'form_type': ENGAGEMENT_FORM_TYPE,
                'total_fetched': len(all_forms),
                'filtered_count': len(engagement_forms),
                'semester': 'Academic Year 2025-2026',
                'management_mode': 'academic_year'
            }
            
            if engagement_forms:
                st.success(f"✅ Found {len(engagement_forms)} event submissions for the academic year")
            else:
                st.warning("No event submissions found")

def general_form_analysis_section():
    """General form analysis section for any form type with automatic discovery"""
    st.subheader("📊 General Form Analysis - Custom Report Generation")
    st.markdown("""
    **Focus:** Analyze ANY form type available in Roompact - automatically discover and select from available forms  
    **Purpose:** Generate custom AI reports for any combination of form types and date ranges  
    **Flexibility:** Choose specific forms, date ranges, and get tailored AI analysis
    """)
    
    # Date range selection for general analysis
    col1, col2 = st.columns(2)
    
    with col1:
        general_start_date = st.date_input(
            "📅 Start Date",
            value=datetime.now().date() - timedelta(days=14),
            help="Discover forms from this date forward",
            key="general_start_date"
        )
    
    with col2:
        general_end_date = st.date_input(
            "📅 End Date", 
            value=datetime.now().date(),
            help="Discover forms up to this date",
            key="general_end_date"
        )
    
    # Form discovery section
    st.subheader("🔍 Discover Available Forms")
    
    if st.button("🔄 Discover Forms", type="primary", key="discover_general_forms"):
        # Calculate page limit for general forms (more forms than just duty reports)
        days_back = (datetime.now().date() - general_start_date).days
        
        # Use generous page limits to ensure we reach historical data
        if days_back > 90:
            max_pages = 1200  # 3+ months - maximum pages for all form types
        elif days_back > 60:
            max_pages = 900   # 2+ months - high page limit
        elif days_back > 30:
            max_pages = 600   # 1+ months - moderate page limit  
        elif days_back > 14:
            max_pages = 400   # 2+ weeks - sufficient pages
        else:
            max_pages = 200   # Recent data - conservative but adequate
        
        st.info(f"🔍 Discovering forms (up to {max_pages} pages) going back {days_back} days to {general_start_date}")
        st.info(f"📈 **Estimate:** ~{days_back * 15} total forms expected (15 per day × {days_back} days)")
        
        # Show extended search warning for very old dates
        if days_back > 30:
            minutes_estimate = max(2, days_back // 15)  # Rough estimate: 1 minute per 15 days
            st.warning(f"⏳ **Extended Search:** Searching {max_pages} pages may take {minutes_estimate}-{minutes_estimate + 2} minutes to complete.")
        
        progress_placeholder = st.empty()
        
        def show_general_progress(page_num, total_forms, oldest_date, reached_target):
            status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
            if oldest_date != "Unknown":
                status += f" | Oldest: {oldest_date}" 
            if reached_target:
                status += f" | ✅ Reached {general_start_date}"
            progress_placeholder.info(status)
        
        # Discover available form types
        form_types_info, error = discover_form_types(
            max_pages=max_pages,
            target_start_date=general_start_date,
            progress_callback=show_general_progress
        )
        
        if form_types_info is None or error:
            st.error(f"Failed to discover forms: {error or 'Unknown error'}")
            return
        
        # Store discovered forms in session state
        st.session_state['general_form_types'] = form_types_info
        st.session_state['general_discovery_date'] = general_start_date
        
        if form_types_info:
            st.success(f"✅ Discovered {len(form_types_info)} different form types")
        else:
            st.warning("No forms found in the specified date range")
    
    # Display discovered form types
    if 'general_form_types' in st.session_state:
        form_types_info = st.session_state['general_form_types']
        discovery_date = st.session_state.get('general_discovery_date')
        
        st.subheader(f"📋 Available Form Types (since {discovery_date})")
        
        if form_types_info:
            # Create multiselect for form type selection
            form_type_options = []
            form_type_details = {}
            
            for form_info in form_types_info:
                display_name = form_info['display_name']
                template_name = form_info['template_name']
                form_type_options.append(display_name)
                form_type_details[display_name] = template_name
            
            selected_form_labels = st.multiselect(
                "Select form types to analyze:",
                form_type_options,
                help="Choose which form types to include in your analysis",
                key="selected_general_form_types"
            )
            
            # Convert labels back to form type names
            selected_form_types = [form_type_details[label] for label in selected_form_labels]
            
            if selected_form_types:
                st.info(f"📊 **Selected for analysis:** {', '.join(selected_form_types)}")
                
                # Fetch forms button
                if st.button("📥 Fetch Selected Forms", type="primary", key="fetch_general_forms"):
                    with st.spinner("Fetching selected forms from Roompact..."):
                        # Calculate page limit for fetching selected general forms
                        days_back = (datetime.now().date() - general_start_date).days
                        
                        # Use same generous limits as discovery phase
                        if days_back > 90:
                            max_pages = 1200  # 3+ months
                        elif days_back > 60:
                            max_pages = 900   # 2+ months
                        elif days_back > 30:
                            max_pages = 600   # 1+ months  
                        elif days_back > 14:
                            max_pages = 400   # 2+ weeks
                        else:
                            max_pages = 200   # Recent data
                        
                        # Show extended search warning
                        if days_back > 60:
                            st.info(f"⏳ **Extended Search:** Going back {days_back} days requires searching up to {max_pages} pages. This may take 1-2 minutes.")
                        
                        progress_placeholder = st.empty()
                        
                        def show_fetch_progress(page_num, total_forms, oldest_date, reached_target):
                            status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
                            if oldest_date != "Unknown":
                                status += f" | Oldest: {oldest_date}"
                            if reached_target:
                                status += f" | ✅ Reached {general_start_date}"
                            progress_placeholder.info(status)
                        
                        all_forms, error = fetch_roompact_forms(
                            max_pages=max_pages,
                            target_start_date=general_start_date,
                            progress_callback=show_fetch_progress
                        )
                        
                        if error:
                            st.error(error)
                            return
                        
                        if not all_forms:
                            st.warning("No forms found.")
                            return
                        
                        # Filter for selected form types
                        filtered_forms, filter_error = filter_forms_by_date_and_type(
                            all_forms, general_start_date, general_end_date, selected_form_types
                        )
                        
                        if filter_error:
                            st.error(f"Error filtering forms: {filter_error}")
                            return
                        
                        # Store filtered forms in session state
                        st.session_state['general_filtered_forms'] = filtered_forms
                        st.session_state['general_filter_info'] = {
                            'start_date': general_start_date,
                            'end_date': general_end_date,
                            'form_types': selected_form_types,
                            'total_fetched': len(all_forms),
                            'filtered_count': len(filtered_forms)
                        }
                        
                        if filtered_forms:
                            st.success(f"✅ Found {len(filtered_forms)} forms matching your criteria (from {len(all_forms)} total forms)")
                        else:
                            st.warning(f"No forms found matching your criteria in the date range {general_start_date} to {general_end_date}")
        
        else:
            st.info("No forms discovered. Try expanding your date range or check your API connection.")
    
    # Display and analyze filtered forms
    if 'general_filtered_forms' in st.session_state and st.session_state['general_filtered_forms']:
        filtered_forms = st.session_state['general_filtered_forms']
        filter_info = st.session_state.get('general_filter_info', {})
        
        st.subheader(f"📊 Forms Ready for Analysis ({len(filtered_forms)} forms)")
        
        # Show filter summary
        if filter_info:
            st.info(f"""
            📊 **Analysis Ready:** {filter_info['filtered_count']} forms (from {filter_info['total_fetched']} total forms)  
            📅 **Date Range:** {filter_info['start_date']} to {filter_info['end_date']}  
            📋 **Form Types:** {', '.join(filter_info['form_types'])}
            """)
        
        # Form selection and analysis
        col_select, col_analyze = st.columns([2, 1])
        
        with col_select:
            st.markdown("**Select forms to analyze:**")
            
            # Group forms by type
            forms_by_type = {}
            for form in filtered_forms:
                template_name = form.get('form_template_name', 'Unknown Form')
                if template_name not in forms_by_type:
                    forms_by_type[template_name] = []
                forms_by_type[template_name].append(form)
            
            selected_general_forms = []
            
            for form_type, type_forms in forms_by_type.items():
                st.markdown(f"**{form_type}** ({len(type_forms)} forms)")
                
                # Select all checkbox for this type
                select_all_key = f"select_all_general_{form_type.replace(' ', '_')}"
                if st.checkbox(f"Select all {form_type}", key=select_all_key):
                    selected_general_forms.extend(type_forms)
                else:
                    # Individual form checkboxes (show first 15 per type)
                    for i, form in enumerate(type_forms[:15]):
                        current_revision = form.get('current_revision', {})
                        author = current_revision.get('author', 'Unknown')
                        date_str = current_revision.get('date', '')
                        
                        # Format date for display
                        try:
                            if date_str:
                                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                display_date = date_obj.strftime('%Y-%m-%d %H:%M')
                            else:
                                display_date = 'Unknown date'
                        except:
                            display_date = date_str or 'Unknown date'
                        
                        form_key = f"general_form_{form_type}_{i}"
                        if st.checkbox(f"📄 {author} - {display_date}", key=form_key):
                            selected_general_forms.append(form)
                
                st.write("---")
        
        with col_analyze:
            st.markdown("**Analysis Options:**")
            
            max_general_forms = st.slider("Max forms to analyze", 
                                min_value=1, 
                                max_value=1000, 
                                value=500,
                                help="Set high limit to analyze all forms (AI can handle large datasets)",
                                key="max_general_forms")
            
            if len(selected_general_forms) > 0:
                st.success(f"✅ {len(selected_general_forms)} forms selected")
                
                # Show helpful message for large datasets
                if len(selected_general_forms) > 100:
                    st.info(f"💪 **Large Dataset Ready:** You can analyze all {len(selected_general_forms)} forms! Set the slider to {len(selected_general_forms)} or higher.")
                
                if st.button("🤖 Generate Analysis", type="primary", key="analyze_general"):
                    if len(selected_general_forms) > max_general_forms:
                        st.warning(f"⚠️ Too many forms selected. Analyzing first {max_general_forms} forms.")
                    
                    # Use general form summary
                    summary = summarize_form_submissions(
                        selected_general_forms[:max_general_forms], 
                        max_general_forms
                    )
                    
                    # Display results
                    st.subheader("📊 General Analysis Results")
                    st.markdown(summary)
                    
                    # Download option
                    date_range = f"{filter_info.get('start_date', 'N/A')} to {filter_info.get('end_date', 'N/A')}"
                    
                    summary_data = f"""# General Form Analysis Summary

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Form Types:** {', '.join(filter_info.get('form_types', []))}  
**Date Range:** {date_range}  
**Forms Analyzed:** {min(len(selected_general_forms), max_general_forms)} of {len(selected_general_forms)} selected  

{summary}

---
Generated by UND Housing & Residence Life Weekly Reporting Tool - General Analysis Section
"""
                    
                    st.download_button(
                        label=f"📄 Download Analysis Report",
                        data=summary_data,
                        file_name=f"general_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown",
                        help="Download the analysis as a markdown file",
                        key="download_general_analysis"
                    )
            else:
                st.info("Select forms above to enable analysis")
    
    else:
        st.info("👆 First discover available form types, then select and fetch the forms you want to analyze")

    # Test API connectivity first
    with st.expander("🔧 API Connection Status", expanded=False):
        config, error = get_roompact_config()
        if error:
            st.error(error)
            st.markdown("""
            **Setup Instructions:**
            1. Contact your system administrator to obtain a Roompact API token
            2. Add the token to your Streamlit secrets under the key `roompact_api_token`
            3. Refresh this page to test the connection
            """)
            return
        else:
            st.success("✅ Roompact API token configured successfully")
            
            # Test API connection
            with st.spinner("Testing API connection..."):
                test_data, test_error = make_roompact_request("forms", {"cursor": ""})
                if test_error:
                    st.error(f"API connection test failed: {test_error}")
                    return
                else:
                    st.success("✅ API connection successful")
                    if isinstance(test_data, dict):
                        total_forms = test_data.get('total_records', 0)
                    else:
                        total_forms = 0
                    st.info(f"📊 Total forms available: {total_forms}")
    
    st.divider()
    
    # Main form analysis interface
    st.subheader("📝 Form Submissions Analysis")
    
    # Date range and filtering options
    col_date1, col_date2, col_discover = st.columns([1, 1, 1])
    
    with col_date1:
        start_date = st.date_input(
            "📅 Start Date",
            value=datetime.now().date() - timedelta(days=90),  # Extended to 90 days
            help="Filter forms submitted on or after this date"
        )
    
    with col_date2:
        end_date = st.date_input(
            "📅 End Date", 
            value=datetime.now().date(),
            help="Filter forms submitted on or before this date"
        )
    
    with col_discover:
        if st.button("🔍 Discover Form Types", help="Scan available forms to see what types exist"):
            # Calculate intelligent page limit based on date range
            days_back = (datetime.now().date() - start_date).days
            if days_back > 90:
                max_pages = 300
            elif days_back > 60:
                max_pages = 200  
            elif days_back > 30:
                max_pages = 100
            else:
                max_pages = 50
            
            st.info(f"🔍 Scanning for forms (up to {max_pages} pages) going back {days_back} days to {start_date.strftime('%Y-%m-%d')}...")
            
            # Show extended search warning for very old dates
            if days_back > 60:
                st.warning(f"⏳ **Extended Search:** Going back {days_back} days requires searching many pages. This may take 1-2 minutes.")
            
            form_types, error = discover_form_types(
                max_pages=max_pages, 
                target_start_date=start_date
            )
            
            if error:
                st.error(f"Error discovering forms: {error}")
            elif form_types:
                st.session_state['discovered_form_types'] = form_types
                st.session_state['discovery_date_range'] = {
                    'start_date': start_date,
                    'end_date': end_date
                }
                st.success(f"✅ Found {len(form_types)} different form types going back to {start_date}!")
            else:
                st.warning("No forms found to discover types from")
    
    # Form type selection
    if 'discovered_form_types' in st.session_state:
        form_options = st.session_state['discovered_form_types']
        
        st.subheader("📋 Select Form Types to Analyze")
        
        # Add "All Form Types" option
        all_option = {"display_name": "All Form Types", "template_name": "All Form Types", "count": sum(f['count'] for f in form_options)}
        display_options = [all_option] + form_options
        
        # Create multiselect with form type options
        selected_displays = st.multiselect(
            "Choose specific form types:",
            options=[opt['display_name'] for opt in display_options],
            default=["All Form Types"],
            help="Select one or more form types to analyze. Default is all forms."
        )
        
        # Convert display names back to template names
        selected_form_types = []
        for display_name in selected_displays:
            for opt in display_options:
                if opt['display_name'] == display_name:
                    selected_form_types.append(opt['template_name'])
                    break
        
        # Show selection summary
        if selected_form_types and "All Form Types" not in selected_form_types:
            total_count = sum(opt['count'] for opt in form_options if opt['template_name'] in selected_form_types)
            st.info(f"📊 Selected {len(selected_form_types)} form type(s) with approximately {total_count} submissions")
    
    else:
        st.info("👆 Click 'Discover Form Types' to see available form types and make specific selections")
        selected_form_types = ["All Form Types"]  # Default fallback
    
    st.divider()
    
    # Fetch and display forms
    if st.button("🔄 Fetch Forms in Date Range", type="primary"):
        if not ('discovered_form_types' in st.session_state and selected_form_types):
            st.warning("Please discover form types and make selections first!")
            return
            
        with st.spinner("Fetching forms from Roompact..."):
            # Calculate page limit based on date range for original supervisors section
            days_back = (datetime.now().date() - start_date).days
            
            # Use generous page limits to ensure historical data access
            if days_back > 90:
                max_pages = 1000  # 3+ months
            elif days_back > 60:
                max_pages = 800   # 2+ months
            elif days_back > 30:
                max_pages = 600   # 1+ months  
            elif days_back > 14:
                max_pages = 400   # 2+ weeks
            else:
                max_pages = 200   # Recent data
            
            st.info(f"📊 Fetching up to {max_pages} pages of data going back {days_back} days to {start_date}")
            
            # Show extended search warning for very old dates
            if days_back > 30:
                st.warning(f"⏳ **Extended Search:** Going back {days_back} days requires searching many pages. This may take 2-3 minutes.")
            
            progress_placeholder = st.empty()
            
            def show_fetch_progress(page_num, total_forms, oldest_date, reached_target):
                status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
                if oldest_date != "Unknown":
                    status += f" | Oldest: {oldest_date}"
                if reached_target:
                    status += f" | ✅ Reached {start_date}"
                progress_placeholder.info(status)
            
            all_forms = fetch_roompact_forms(
                max_pages=max_pages,
                target_start_date=start_date,
                progress_callback=show_fetch_progress
            )
            
            if not all_forms:
                st.warning("No forms found.")
                return
            
            # Filter forms by date range and selected types
            filtered_forms, filter_error = filter_forms_by_date_and_type(
                all_forms, start_date, end_date, selected_form_types
            )
            
            if filter_error:
                st.error(f"Error filtering forms: {filter_error}")
                return
            
            # Store filtered forms in session state
            st.session_state['roompact_forms'] = filtered_forms
            st.session_state['filter_info'] = {
                'start_date': start_date,
                'end_date': end_date,
                'form_types': selected_form_types,
                'total_fetched': len(all_forms),
                'filtered_count': len(filtered_forms)
            }
            
            # Show actual date range of retrieved forms for debugging
            if all_forms:
                form_dates = []
                for form in all_forms:
                    current_revision = form.get('current_revision', {})
                    date_str = current_revision.get('date', '')
                    if date_str:
                        try:
                            form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            form_dates.append(form_datetime)
                        except:
                            pass
                
                if form_dates:
                    oldest_retrieved = min(form_dates).strftime('%Y-%m-%d')
                    newest_retrieved = max(form_dates).strftime('%Y-%m-%d')
                    st.info(f"📅 **Retrieved data range:** {oldest_retrieved} to {newest_retrieved}")
                    
                    if datetime.strptime(oldest_retrieved, '%Y-%m-%d').date() > start_date:
                        days_missing = (datetime.strptime(oldest_retrieved, '%Y-%m-%d').date() - start_date).days
                        st.warning(f"⚠️ **Missing {days_missing} days of data** - oldest form found is {oldest_retrieved}, but you requested back to {start_date}. Try increasing page limits or check if forms exist for that period.")
            
            if filtered_forms:
                st.success(f"✅ Found {len(filtered_forms)} forms matching your criteria (from {len(all_forms)} total forms)")
            else:
                form_type_text = ", ".join(selected_form_types) if len(selected_form_types) <= 3 else f"{len(selected_form_types)} selected form types"
                st.warning(f"No forms found in the date range {start_date} to {end_date} matching: {form_type_text}")
    
    # Display forms if available
    if 'roompact_forms' in st.session_state and st.session_state['roompact_forms']:
        forms = st.session_state['roompact_forms']
        filter_info = st.session_state.get('filter_info', {})
        
        # Show filter summary
        if filter_info:
            form_types_display = filter_info.get('form_types', [])
            if len(form_types_display) <= 3:
                form_types_text = ", ".join(form_types_display)
            else:
                form_types_text = f"{len(form_types_display)} selected form types"
                
            st.info(f"""
            📊 **Filter Results:** {filter_info['filtered_count']} forms found (from {filter_info['total_fetched']} total)  
            📅 **Date Range:** {filter_info['start_date']} to {filter_info['end_date']}  
            📋 **Form Types:** {form_types_text}
            """)
        
        st.subheader(f"📋 Filtered Forms ({len(forms)} submissions)")
        
        # Create form selection interface
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("**Select forms to analyze:**")
            
            # Group forms by template name for better organization
            forms_by_template = {}
            for form in forms:
                template_name = form.get('form_template_name', 'Unknown Form')
                if template_name not in forms_by_template:
                    forms_by_template[template_name] = []
                forms_by_template[template_name].append(form)
            
            selected_forms = []
            
            # Show forms grouped by template
            for template_name, template_forms in forms_by_template.items():
                st.markdown(f"**{template_name}** ({len(template_forms)} submissions)")
                
                # Select all checkbox for this template
                select_all_key = f"select_all_{template_name.replace(' ', '_')}"
                if st.checkbox(f"Select all {template_name}", key=select_all_key):
                    selected_forms.extend(template_forms)
                else:
                    # Individual form checkboxes
                    for i, form in enumerate(template_forms[:10]):  # Limit display to first 10 per template
                        current_revision = form.get('current_revision', {})
                        author = current_revision.get('author', 'Unknown')
                        date_str = current_revision.get('date', '')
                        
                        # Format date for display
                        try:
                            if date_str:
                                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                display_date = date_obj.strftime('%Y-%m-%d %H:%M')
                            else:
                                display_date = 'Unknown date'
                        except:
                            display_date = date_str or 'Unknown date'
                        
                        form_key = f"form_{template_name}_{i}"
                        if st.checkbox(f"📄 {author} - {display_date}", key=form_key):
                            selected_forms.append(form)
                
                st.write("---")
        
        with col2:
            st.markdown("**Analysis Options:**")
            
            max_forms = st.slider("Max forms to analyze", 
                                min_value=1, 
                                max_value=1000, 
                                value=500,
                                help="Set high limit to analyze all forms (AI can handle large datasets)")
            
            if len(selected_forms) > 0:
                st.success(f"✅ {len(selected_forms)} forms selected")
                
                if st.button("🤖 Generate AI Summary", type="primary"):
                    if len(selected_forms) > max_forms:
                        st.warning(f"⚠️ Too many forms selected. Analyzing first {max_forms} forms.")
                    
                    # Check if focusing on duty reports for specialized analysis
                    filter_info = st.session_state.get('filter_info', {})
                    form_types = filter_info.get('form_types', [])
                    
                    # Use specialized duty report analysis if only duty-related forms are selected
                    is_duty_focused = (
                        len(form_types) == 1 and 
                        any('duty' in form_type.lower() for form_type in form_types)
                    ) or (
                        len([ft for ft in form_types if 'duty' in ft.lower()]) > 0 and
                        len([ft for ft in form_types if 'duty' not in ft.lower()]) == 0
                    )
                    
                    if is_duty_focused and 'All Form Types' not in form_types:
                        summary = create_duty_report_summary(
                            selected_forms[:max_forms], 
                            filter_info['start_date'], 
                            filter_info['end_date']
                        )
                    else:
                        # Use general form analysis
                        summary = summarize_form_submissions(selected_forms, max_forms)
                    
                    # Display results
                    st.subheader("📊 AI Analysis Results")
                    st.markdown(summary)
                    
                    # Offer download option
                    filter_info = st.session_state.get('filter_info', {})
                    form_types = filter_info.get('form_types', ['Forms'])
                    
                    # Determine analysis type for filename and label
                    if len(form_types) == 1 and 'duty' in form_types[0].lower():
                        analysis_type = "Duty Reports"
                        file_prefix = "duty_reports"
                    elif len(form_types) <= 3:
                        analysis_type = " & ".join(form_types)
                        file_prefix = "forms_analysis"
                    else:
                        analysis_type = f"{len(form_types)} Form Types"
                        file_prefix = "multi_forms_analysis"
                    
                    date_range = f"{filter_info.get('start_date', 'N/A')} to {filter_info.get('end_date', 'N/A')}"
                    form_types_text = ", ".join(form_types) if len(form_types) <= 5 else f"{len(form_types)} selected form types"
                    
                    summary_data = f"""# Roompact Forms Analysis Summary

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Form Types:** {form_types_text}  
**Date Range:** {date_range}  
**Forms Analyzed:** {min(len(selected_forms), max_forms)} of {len(selected_forms)} selected  

{summary}

---
Generated by UND Housing & Residence Life Weekly Reporting Tool
"""
                    
                    st.download_button(
                        label=f"📄 Download Analysis Report",
                        data=summary_data,
                        file_name=f"{file_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown",
                        help="Download the forms analysis as a markdown file"
                    )
            else:
                st.info("Select forms above to enable AI analysis")
    
    else:
        st.info("👆 Click 'Fetch Latest Forms' to load form submissions from Roompact")


def individual_reports_viewer():
    """View and filter individual staff reports"""
    st.subheader("📋 Individual Reports Viewer")
    st.markdown("""
    View detailed individual staff submissions with filtering by date, staff member, and form type.
    """)
    
    # Date range selection
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input(
            "📅 Start Date",
            value=datetime.now().date() - timedelta(days=30),
            help="View reports from this date forward",
            key="individual_start_date"
        )
    
    with col2:
        end_date = st.date_input(
            "📅 End Date",
            value=datetime.now().date(),
            help="View reports up to this date",
            key="individual_end_date"
        )
    
    # Fetch reports button
    if st.button("🔍 Fetch Reports", type="primary", key="fetch_individual_reports"):
        with st.spinner("Fetching reports from Roompact..."):
            # Increase max_pages to fetch more forms
            # Note: We don't use target_start_date here because we want to fetch
            # all recent forms and then filter by date range
            max_pages = 300
            
            progress_placeholder = st.empty()
            
            def show_progress(page_num, total_forms, oldest_date, reached_target):
                status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
                if oldest_date:
                    status += f" | Oldest: {oldest_date.strftime('%Y-%m-%d') if isinstance(oldest_date, datetime) else oldest_date}"
                progress_placeholder.info(status)
            
            # Fetch forms with target_start_date to stop when we reach older forms
            # This prevents fetching the entire history when we only need recent reports
            all_forms = fetch_roompact_forms(
                max_pages=max_pages,
                target_start_date=start_date,  # Stop when we reach forms older than start_date
                progress_callback=show_progress
            )
            
            if not all_forms:
                st.warning("No forms found.")
                return
            
            st.info(f"📦 **Fetched {len(all_forms)} total forms from Roompact API**")
            
            # Filter by date range
            filtered_forms, filter_error = filter_forms_by_date_and_type(
                all_forms, start_date, end_date, []  # Empty list means all form types
            )
            
            if filter_error:
                st.error(f"Error filtering forms: {filter_error}")
                return
            
            # Store in session state
            st.session_state['individual_reports'] = filtered_forms
            st.session_state['individual_reports_date_range'] = {
                'start_date': start_date,
                'end_date': end_date
            }
            
            if filtered_forms:
                st.success(f"✅ Found {len(filtered_forms)} reports in the selected date range")
            else:
                st.warning("No reports found matching your criteria")
    
    # Display reports if available
    if 'individual_reports' in st.session_state and st.session_state['individual_reports']:
        reports = st.session_state['individual_reports']
        date_range = st.session_state.get('individual_reports_date_range', {})
        
        st.markdown("---")
        st.subheader("📊 Filter and View Reports")
        
        # Extract unique staff members and form types
        staff_members = set()
        form_types = set()
        
        for form in reports:
            current_revision = form.get('current_revision', {})
            author = current_revision.get('author', 'Unknown')
            form_type = form.get('form_template_name', 'Unknown Form')
            
            if author and author != 'Unknown':
                staff_members.add(author)
            if form_type and form_type != 'Unknown Form':
                form_types.add(form_type)
        
        # Filters
        col1, col2, col3 = st.columns(3)
        
        with col1:
            selected_staff = st.multiselect(
                "👤 Filter by Staff Member",
                options=sorted(list(staff_members)),
                default=[],
                help="Select one or more staff members to filter",
                key="filter_staff"
            )
        
        with col2:
            selected_form_types = st.multiselect(
                "📝 Filter by Form Type",
                options=sorted(list(form_types)),
                default=[],
                help="Select one or more form types to filter",
                key="filter_form_types"
            )
        
        with col3:
            sort_order = st.selectbox(
                "📅 Sort By",
                options=["Newest First", "Oldest First"],
                key="sort_order"
            )
        
        # Apply filters
        filtered_reports = reports
        
        if selected_staff:
            filtered_reports = [
                form for form in filtered_reports
                if form.get('current_revision', {}).get('author', '') in selected_staff
            ]
        
        if selected_form_types:
            filtered_reports = [
                form for form in filtered_reports
                if form.get('form_template_name', '') in selected_form_types
            ]
        
        # Sort reports
        def get_form_date(form):
            date_str = form.get('current_revision', {}).get('date', '')
            if date_str:
                try:
                    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except:
                    return datetime.min
            return datetime.min
        
        filtered_reports = sorted(
            filtered_reports,
            key=get_form_date,
            reverse=(sort_order == "Newest First")
        )
        
        # Display summary
        st.info(f"**Showing {len(filtered_reports)} of {len(reports)} reports**")
        
        # Staff member report counts
        if filtered_reports:
            staff_counts = {}
            for form in filtered_reports:
                author = form.get('current_revision', {}).get('author', 'Unknown')
                staff_counts[author] = staff_counts.get(author, 0) + 1
            
            with st.expander("📊 Report Counts by Staff Member"):
                for staff, count in sorted(staff_counts.items(), key=lambda x: x[1], reverse=True):
                    st.write(f"**{staff}:** {count} report(s)")
        
        # Display individual reports
        st.markdown("---")
        st.subheader(f"📋 Individual Reports ({len(filtered_reports)})")
        
        for i, form in enumerate(filtered_reports, 1):
            current_revision = form.get('current_revision', {})
            form_name = form.get('form_template_name', 'Unknown Form')
            author = current_revision.get('author', 'Unknown')
            date_str = current_revision.get('date', 'Unknown date')
            
            # Format date for display
            display_date = date_str
            if date_str != 'Unknown date':
                try:
                    form_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    display_date = form_date.strftime('%Y-%m-%d %I:%M %p')
                except:
                    pass
            
            # Create expander for each report
            with st.expander(f"**{i}.** {form_name} - {author} - {display_date}"):
                # Display form metadata
                st.markdown(f"**Staff Member:** {author}")
                st.markdown(f"**Form Type:** {form_name}")
                st.markdown(f"**Submission Date:** {display_date}")
                
                st.markdown("---")
                st.markdown("### Form Responses")
                
                # Display all form responses
                responses = current_revision.get('responses', [])
                
                if not responses:
                    st.info("No responses recorded for this form.")
                else:
                    for resp_idx, response in enumerate(responses):
                        field_label = response.get('field_label', 'Unknown Field')
                        field_response = response.get('response', '')
                        
                        if field_response and str(field_response).strip():
                            # Try to parse and format JSON/list responses
                            formatted_response = field_response
                            
                            # Check if it's a list or dict (JSON-like)
                            if isinstance(field_response, (list, dict)):
                                try:
                                    # Format lists of dicts (like tags)
                                    if isinstance(field_response, list) and field_response and isinstance(field_response[0], dict):
                                        formatted_items = []
                                        for item in field_response:
                                            if 'tag_name' in item:
                                                formatted_items.append(f"• {item['tag_name']}")
                                            else:
                                                # Generic dict formatting
                                                formatted_items.append(f"• {', '.join(f'{k}: {v}' for k, v in item.items())}")
                                        formatted_response = '\n'.join(formatted_items)
                                    else:
                                        # For other structures, use JSON formatting
                                        import json
                                        formatted_response = json.dumps(field_response, indent=2)
                                except:
                                    formatted_response = str(field_response)
                            
                            # Check if string looks like JSON
                            elif isinstance(field_response, str) and (field_response.startswith('[') or field_response.startswith('{')):
                                try:
                                    import json
                                    parsed = json.loads(field_response.replace("'", '"'))
                                    
                                    # Format lists of dicts (like tags)
                                    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                                        formatted_items = []
                                        for item in parsed:
                                            if 'tag_name' in item:
                                                formatted_items.append(f"• {item['tag_name']}")
                                            else:
                                                # Generic dict formatting
                                                formatted_items.append(f"• {', '.join(f'{k}: {v}' for k, v in item.items())}")
                                        formatted_response = '\n'.join(formatted_items)
                                    else:
                                        formatted_response = json.dumps(parsed, indent=2)
                                except:
                                    # If parsing fails, keep original
                                    formatted_response = str(field_response)
                            else:
                                formatted_response = str(field_response)
                            
                            # Format long responses as text areas
                            if len(formatted_response) > 100:
                                st.markdown(f"**{field_label}:**")
                                st.text_area(
                                    label="",
                                    value=formatted_response,
                                    height=min(100 + (formatted_response.count('\n') * 20), 300),
                                    disabled=True,
                                    key=f"response_{i}_{resp_idx}_{field_label}",
                                    label_visibility="collapsed"
                                )
                            else:
                                st.markdown(f"**{field_label}:** {formatted_response}")
                
                # Export button for individual report
                st.markdown("---")
                report_markdown = f"""# {form_name}

**Staff Member:** {author}  
**Submission Date:** {display_date}

## Form Responses

"""
                for response in responses:
                    field_label = response.get('field_label', 'Unknown Field')
                    field_response = response.get('response', '')
                    if field_response and str(field_response).strip():
                        report_markdown += f"**{field_label}:** {field_response}\n\n"
                
                st.download_button(
                    label="📥 Download Report",
                    data=report_markdown,
                    file_name=f"{form_name}_{author}_{display_date.replace(':', '-').replace(' ', '_')}.md",
                    mime="text/markdown",
                    key=f"download_{i}"
                )
