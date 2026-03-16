import json
from datetime import datetime, timedelta

import streamlit as st

from src.ai import clean_summary_response, create_duty_report_summary, summarize_form_submissions
from src.weekly_report import create_weekly_duty_report_summary
from src.database import get_admin_client, log_user_activity, supabase
from src.roompact import (
    discover_form_types,
    fetch_roompact_forms,
    filter_forms_by_date_and_type,
    get_roompact_config,
    make_roompact_request,
)

# Roompact duty form templates we treat as duty reports
DUTY_FORM_TYPES = [
    "Resident Assistant Duty",
    "Resident Assistant Duty Report",
    "CA Duty",
    "Community Assistant Duty Report",
    "RD Duty",
    "RD Duty Report",
    "Resident Manager Duty",
    "Resident Manager Duty Report",
    "RM Duty Report",
]


def supervisor_summaries_page() -> None:
    """Display saved supervisor team summaries stored in Supabase."""
    st.title("My Saved Team Summaries")
    st.write("Saved summaries you've generated for your team.")

    if "user" not in st.session_state:
        st.info("Log in to view saved summaries.")
        return

    try:
        resp = supabase.rpc(
            "get_supervisor_summaries",
            {"p_super": st.session_state["user"].id},
        ).execute()
        summaries = resp.data or []
        if not summaries:
            st.info("You have no saved team summaries yet.")
            return

        for summary in summaries:
            created = summary.get("created_at", "")
            week_ending = summary.get("week_ending_date", "Unknown")
            with st.expander(f"Week Ending {week_ending} — Saved {created}"):
                st.markdown(clean_summary_response(summary.get("summary_text", "")))
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to fetch supervisor summaries: {exc}")


def supervisors_section_page() -> None:
    """Entry point for the supervisors section (tabs for duty, general, and viewer)."""
    st.title("👩‍💼 Supervisors Section - Form Analysis")
    st.markdown(
        """
        Review Roompact form submissions, run AI-powered summaries, and drill into individual reports.
        """
    )

    tab_duty, tab_general, tab_viewer = st.tabs(
        ["⛑️ Duty Analysis", "📝 General Form Analysis", "📄 Individual Reports"]
    )

    with tab_duty:
        duty_analysis_section()

    with tab_general:
        general_form_analysis_section()

    with tab_viewer:
        individual_reports_viewer()


def duty_analysis_section() -> None:
    """Specialized analysis for duty-related forms."""
    st.subheader("⛑️ Duty Report Analysis")

    col1, col2 = st.columns(2)
    with col1:
        duty_start_date = st.date_input(
            "📅 Start Date",
            value=datetime.now().date() - timedelta(days=30),
            help="Analyze duty reports from this date forward",
            key="duty_start_date",
        )
    with col2:
        duty_end_date = st.date_input(
            "📅 End Date",
            value=datetime.now().date(),
            help="Analyze duty reports up to this date",
            key="duty_end_date",
        )

    if st.button("🔄 Fetch Duty Reports", type="primary", key="fetch_duty_reports"):
        days_back = (datetime.now().date() - duty_start_date).days
        if days_back > 90:
            max_pages = 500
        elif days_back > 60:
            max_pages = 400
        elif days_back > 30:
            max_pages = 300
        elif days_back > 14:
            max_pages = 200
        else:
            max_pages = 120

        progress_placeholder = st.empty()

        def show_progress(page_num: int, total_forms: int, oldest_date: str, reached_target: bool) -> None:
            status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
            if oldest_date != "Unknown":
                status += f" | Oldest: {oldest_date}"
            if reached_target:
                status += f" | ✅ Reached {duty_start_date}"
            progress_placeholder.info(status)

        with st.spinner("Fetching duty reports from Roompact..."):
            all_forms, error = fetch_roompact_forms(
                max_pages=max_pages,
                target_start_date=duty_start_date,
                progress_callback=show_progress,
            )

        if error:
            st.error(error)
            return

        duty_forms, filter_error = filter_forms_by_date_and_type(
            all_forms, duty_start_date, duty_end_date, DUTY_FORM_TYPES
        )
        if filter_error:
            st.error(filter_error)
            return

        st.session_state["duty_forms"] = duty_forms
        st.session_state["duty_filter_info"] = {
            "start_date": duty_start_date,
            "end_date": duty_end_date,
            "form_types": DUTY_FORM_TYPES,
            "total_fetched": len(all_forms),
            "filtered_count": len(duty_forms),
        }
        # Clear any previously generated analysis when new data is fetched to avoid stale results
        st.session_state.pop("duty_analysis_result", None)

        if duty_forms:
            st.success(f"✅ Found {len(duty_forms)} duty reports (from {len(all_forms)} total forms)")
        else:
            st.warning(
                f"No duty reports found in the date range {duty_start_date} to {duty_end_date}"
            )

    if "duty_forms" not in st.session_state or not st.session_state["duty_forms"]:
        return

    duty_forms = st.session_state["duty_forms"]
    filter_info = st.session_state.get("duty_filter_info", {})

    st.info(
        f"📊 Analysis Ready: {filter_info.get('filtered_count', len(duty_forms))} reports from "
        f"{filter_info.get('start_date')} to {filter_info.get('end_date')}"
    )

    col_select, col_analyze = st.columns([2, 1])
    with col_select:
        st.markdown("**Select duty reports to analyze:**")
        grouped = {}
        for form in duty_forms:
            name = form.get("form_template_name", "Unknown Form")
            grouped.setdefault(name, []).append(form)

        selected = []
        for form_type, forms in grouped.items():
            st.markdown(f"**{form_type}** ({len(forms)} reports)")
            select_all_key = f"duty_select_all_{form_type.replace(' ', '_')}"
            if st.checkbox(f"Select all {form_type}", key=select_all_key):
                selected.extend(forms)
            else:
                for idx, form in enumerate(forms[:30]):
                    current = form.get("current_revision", {})
                    author = current.get("author", "Unknown")
                    date_str = _format_date(current.get("date", ""))
                    if st.checkbox(
                        f"📄 {author} - {date_str}", key=f"duty_form_{form_type}_{idx}"
                    ):
                        selected.append(form)
            st.write("---")

    with col_analyze:
        st.markdown("**Analysis Options:**")
        report_type = st.radio(
            "Report Type",
            ["📊 Standard Analysis", "📅 Weekly Summary"],
            help="Choose a detailed analysis or a weekly summary format",
            key="duty_report_type",
        )
        max_forms = st.slider(
            "Max reports to analyze",
            min_value=1,
            max_value=500,
            value=min(200, len(duty_forms)),
            key="max_duty_forms",
        )
        custom_prompt = st.text_area(
            "AI prompt (optional)",
            value=(
                "You are an expert student affairs analyst. Summarize key themes, concerns, "
                "action items, and recognition opportunities. Be concise and actionable."
            ),
            height=140,
            help="Provide custom instructions for the AI.",
            key="duty_ai_prompt",
        )

        if selected:
            st.success(f"✅ {len(selected)} duty reports selected")
            if st.button("🤖 Generate Duty Analysis", type="primary", key="run_duty_analysis"):
                start_date = filter_info.get("start_date")
                end_date = filter_info.get("end_date")
                start_date_str = start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date)
                end_date_str = end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date)
                if report_type == "📅 Weekly Summary":
                    summary_result = create_weekly_duty_report_summary(
                        selected[:max_forms],
                        start_date,
                        end_date,
                    )
                    summary = summary_result.get("summary") if isinstance(summary_result, dict) else summary_result
                    report_label = "Weekly Duty Summary"
                    file_prefix = "weekly_duty_summary"
                    # Persist weekly duty summary for later integration (admin dashboard)
                    weekly_report_data = {
                        "date_generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "date_range": f"{start_date_str} to {end_date_str}",
                        "reports_analyzed": min(len(selected), max_forms),
                        "total_selected": len(selected),
                        "summary": summary,
                    }
                    st.session_state.setdefault("weekly_duty_reports", []).append(weekly_report_data)
                else:
                    summary = create_duty_report_summary(
                        selected[:max_forms],
                        start_date,
                        end_date,
                    )
                    report_label = "Duty Analysis"
                    file_prefix = "duty_analysis"
                # Cache the result for reuse on rerun (keeps save/download buttons visible)
                st.session_state["duty_analysis_result"] = {
                    "variant": "weekly_summary" if report_type == "📅 Weekly Summary" else "standard",
                    "label": report_label,
                    "file_prefix": file_prefix,
                    "summary": summary,
                    "filter_info": {
                        "start_date": start_date_str,
                        "end_date": end_date_str,
                    },
                    "analyzed": min(len(selected), max_forms),
                    "selected": len(selected),
                    "custom_prompt": custom_prompt,
                }
                # Log activity (best effort)
                try:
                    log_user_activity(
                        event_type="analysis_run",
                        context="roompact_duty_analysis",
                        metadata={
                            "selected_forms": len(selected),
                            "analyzed_forms": min(len(selected), max_forms),
                            "date_range": [
                                str(filter_info.get("start_date")),
                                str(filter_info.get("end_date")),
                            ],
                            "custom_prompt": custom_prompt,
                        },
                        user=st.session_state.get("user"),
                    )
                except Exception:
                    pass

            analysis_result = st.session_state.get("duty_analysis_result")
            if analysis_result:
                report_label = analysis_result.get("label", "Duty Analysis")
                file_prefix = analysis_result.get("file_prefix", "duty_analysis")
                summary = analysis_result.get("summary")
                filter_start = analysis_result.get("filter_info", {}).get("start_date")
                filter_end = analysis_result.get("filter_info", {}).get("end_date")
                analyzed_count = analysis_result.get("analyzed", len(selected))
                selected_count = analysis_result.get("selected", len(selected))
                st.subheader(f"📊 {report_label} Results")
                if summary:
                    st.markdown(summary)
                else:
                    st.warning("No summary text returned.")

                download_data = _build_download(
                    title=report_label,
                    form_types=DUTY_FORM_TYPES,
                    date_range=(filter_start, filter_end),
                    analyzed=analyzed_count,
                    selected=selected_count,
                    summary=summary,
                    custom_prompt=analysis_result.get("custom_prompt", ""),
                )
                st.download_button(
                    label="📄 Download Analysis Report",
                    data=download_data,
                    file_name=f"{file_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                    key="download_duty_analysis",
                )

                if analysis_result.get("variant") == "weekly_summary":
                    if st.button("💾 Save Weekly Duty Summary", type="secondary", key="save_weekly_duty_summary"):
                        try:
                            admin_client = get_admin_client()
                            save_payload = {
                                "week_ending_date": filter_end,
                                "report_type": "weekly_summary",
                                "date_range_start": filter_start,
                                "date_range_end": filter_end,
                                "reports_analyzed": analyzed_count,
                                "total_selected": selected_count,
                                "analysis_text": summary,
                                "created_by": st.session_state.get("user").id if st.session_state.get("user") else None,
                                "created_at": datetime.now().isoformat(),
                                "updated_at": datetime.now().isoformat(),
                            }

                            # Try insert first; if duplicate, perform update manually (avoids missing unique index errors)
                            try:
                                admin_client.table("saved_duty_analyses").insert(save_payload).execute()
                                st.success("✅ Weekly duty summary saved to database.")
                            except Exception as insert_exc:  # noqa: BLE001
                                err_text = str(insert_exc)
                                if "duplicate key" in err_text or "unique constraint" in err_text:
                                    admin_client.table("saved_duty_analyses").update(
                                        {
                                            "date_range_start": filter_start,
                                            "date_range_end": filter_end,
                                            "reports_analyzed": analyzed_count,
                                            "total_selected": selected_count,
                                            "analysis_text": summary,
                                            "updated_at": datetime.now().isoformat(),
                                        }
                                    ).match(
                                        {
                                            "week_ending_date": filter_end,
                                            "created_by": st.session_state.get("user").id if st.session_state.get("user") else None,
                                            "report_type": "weekly_summary",
                                        }
                                    ).execute()
                                    st.success("✅ Weekly duty summary updated in database.")
                                else:
                                    raise insert_exc
                        except Exception as exc:  # noqa: BLE001
                            st.error(f"Failed to save weekly duty summary: {exc}")


def general_form_analysis_section() -> None:
    """General Roompact form discovery, fetching, and AI analysis."""
    st.subheader("📝 General Form Analysis")

    # Discover available form types
    col_discover_start, col_discover_end, col_discover_button = st.columns([1, 1, 1])
    with col_discover_start:
        discovery_start = st.date_input(
            "📅 Discover: Start Date",
            value=datetime.now().date() - timedelta(days=60),
            key="general_discovery_start",
        )
    with col_discover_end:
        discovery_end = st.date_input(
            "📅 Discover: End Date",
            value=datetime.now().date(),
            key="general_discovery_end",
        )
    with col_discover_button:
        if st.button("🔍 Discover Form Types", key="discover_general_forms"):
            days_back = (datetime.now().date() - discovery_start).days
            if days_back > 90:
                max_pages = 600
            elif days_back > 60:
                max_pages = 450
            elif days_back > 30:
                max_pages = 300
            else:
                max_pages = 180

            progress_placeholder = st.empty()

            def show_progress(page_num: int, total_forms: int, oldest_date: str, reached_target: bool) -> None:
                status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
                if oldest_date != "Unknown":
                    status += f" | Oldest: {oldest_date}"
                if reached_target:
                    status += f" | ✅ Reached {discovery_start}"
                progress_placeholder.info(status)

            with st.spinner("Discovering available form types..."):
                form_types, error = discover_form_types(
                    max_pages=max_pages,
                    target_start_date=discovery_start,
                    progress_callback=show_progress,
                )

            if error:
                st.error(f"Failed to discover forms: {error}")
            elif form_types:
                st.session_state["discovered_form_types"] = form_types
                st.session_state["discovery_date_range"] = {
                    "start_date": discovery_start,
                    "end_date": discovery_end,
                }
                st.success(f"✅ Discovered {len(form_types)} form types")
            else:
                st.warning("No forms found in the specified range.")

    if "discovered_form_types" not in st.session_state:
        st.info("👆 Run discovery to see available form types.")
        return

    form_options = st.session_state.get("discovered_form_types", [])
    discovery_dates = st.session_state.get("discovery_date_range", {})
    st.markdown(
        f"**Discovered {len(form_options)} form types** (from {discovery_dates.get('start_date')} "
        f"to {discovery_dates.get('end_date')})."
    )

    all_option = {
        "display_name": "All Form Types",
        "template_name": "All Form Types",
        "count": sum(item.get("count", 0) for item in form_options),
    }
    display_options = [all_option] + form_options

    selected_displays = st.multiselect(
        "Select form types to analyze:",
        options=[opt["display_name"] for opt in display_options],
        default=["All Form Types"],
        help="Choose one or more form types. Default is all forms.",
    )

    selected_form_types = []
    for display_name in selected_displays:
        for opt in display_options:
            if opt["display_name"] == display_name:
                selected_form_types.append(opt["template_name"])
                break

    st.markdown("---")

    col_fetch_start, col_fetch_end = st.columns(2)
    with col_fetch_start:
        fetch_start = st.date_input(
            "📅 Fetch: Start Date",
            value=discovery_dates.get("start_date", datetime.now().date() - timedelta(days=30)),
            key="general_fetch_start",
        )
    with col_fetch_end:
        fetch_end = st.date_input(
            "📅 Fetch: End Date",
            value=discovery_dates.get("end_date", datetime.now().date()),
            key="general_fetch_end",
        )

    if st.button("🔄 Fetch Forms in Date Range", type="primary", key="fetch_general_forms"):
        if not selected_form_types:
            st.warning("Select at least one form type.")
        else:
            days_back = (datetime.now().date() - fetch_start).days
            if days_back > 90:
                max_pages = 1000
            elif days_back > 60:
                max_pages = 800
            elif days_back > 30:
                max_pages = 600
            elif days_back > 14:
                max_pages = 400
            else:
                max_pages = 200

            progress_placeholder = st.empty()

            def show_fetch_progress(page_num: int, total_forms: int, oldest_date: str, reached_target: bool) -> None:
                status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
                if oldest_date != "Unknown":
                    status += f" | Oldest: {oldest_date}"
                if reached_target:
                    status += f" | ✅ Reached {fetch_start}"
                progress_placeholder.info(status)

            with st.spinner("Fetching forms from Roompact..."):
                all_forms, error = fetch_roompact_forms(
                    max_pages=max_pages,
                    target_start_date=fetch_start,
                    progress_callback=show_fetch_progress,
                )

            if error:
                st.error(error)
                return
            if not all_forms:
                st.warning("No forms found.")
                return

            filtered_forms, filter_error = filter_forms_by_date_and_type(
                all_forms, fetch_start, fetch_end, selected_form_types
            )
            if filter_error:
                st.error(filter_error)
                return

            st.session_state["roompact_forms"] = filtered_forms
            st.session_state["filter_info"] = {
                "start_date": fetch_start,
                "end_date": fetch_end,
                "form_types": selected_form_types,
                "total_fetched": len(all_forms),
                "filtered_count": len(filtered_forms),
            }

            if filtered_forms:
                st.success(
                    f"✅ Found {len(filtered_forms)} forms matching your criteria (from {len(all_forms)} total forms)"
                )
            else:
                st.warning(
                    f"No forms found in the date range {fetch_start} to {fetch_end} matching your selection."
                )

    if "roompact_forms" not in st.session_state or not st.session_state["roompact_forms"]:
        return

    forms = st.session_state["roompact_forms"]
    filter_info = st.session_state.get("filter_info", {})

    st.info(
        f"📊 Filter Results: {filter_info.get('filtered_count', len(forms))} forms from {filter_info.get('total_fetched', len(forms))} fetched"
    )

    col_forms, col_options = st.columns([2, 1])
    with col_forms:
        st.markdown("**Select forms to analyze:**")
        forms_by_template = {}
        for form in forms:
            template_name = form.get("form_template_name", "Unknown Form")
            forms_by_template.setdefault(template_name, []).append(form)

        selected_forms = []
        st.markdown("<div style='max-height: 520px; overflow-y: auto; padding-right: 8px;'>", unsafe_allow_html=True)
        for template_name, template_forms in forms_by_template.items():
            st.markdown(f"**{template_name}** ({len(template_forms)} submissions)")
            select_all_key = f"select_all_{template_name.replace(' ', '_')}"
            if st.checkbox(f"Select all {template_name}", key=select_all_key):
                selected_forms.extend(template_forms)
            else:
                st.markdown(
                    "<div style='max-height: 260px; overflow-y: auto; padding-left: 4px;'>",
                    unsafe_allow_html=True,
                )
                for idx, form in enumerate(template_forms[:300]):
                    current_revision = form.get("current_revision", {})
                    author = current_revision.get("author", "Unknown")
                    date_str = _format_date(current_revision.get("date", ""))
                    form_key = f"form_{template_name}_{idx}"
                    if st.checkbox(f"📄 {author} - {date_str}", key=form_key):
                        selected_forms.append(form)
                st.markdown("</div>", unsafe_allow_html=True)
            st.write("---")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_options:
        st.markdown("**Analysis Options:**")
        max_forms = st.slider(
            "Max forms to analyze",
            min_value=1,
            max_value=1000,
            value=min(500, len(forms)),
            help="Set high limit to analyze all forms (AI can handle large datasets)",
            key="max_general_forms",
        )
        custom_prompt = st.text_area(
            "AI prompt (optional)",
            value=(
                "You are an expert student affairs analyst. Summarize key themes, concerns, "
                "action items, and recognition opportunities. Be concise and actionable."
            ),
            height=140,
            help="Provide custom instructions for the AI.",
            key="general_ai_prompt",
        )

        if selected_forms:
            st.success(f"✅ {len(selected_forms)} forms selected")
            if st.button("🤖 Generate AI Summary", type="primary", key="run_general_analysis"):
                if len(selected_forms) > max_forms:
                    st.warning(f"⚠️ Too many forms selected. Analyzing first {max_forms} forms.")

                form_types = filter_info.get("form_types", [])
                is_duty_only = (
                    len(form_types) == 1 and "duty" in form_types[0].lower()
                ) or (
                    len([ft for ft in form_types if "duty" in ft.lower()]) > 0
                    and len([ft for ft in form_types if "duty" not in ft.lower()]) == 0
                )

                if is_duty_only and "All Form Types" not in form_types:
                    summary = create_duty_report_summary(
                        selected_forms[:max_forms],
                        filter_info.get("start_date"),
                        filter_info.get("end_date"),
                    )
                else:
                    summary = summarize_form_submissions(
                        selected_forms[:max_forms],
                        max_forms,
                        custom_prompt=custom_prompt,
                        context="roompact_general_form_analysis",
                    )

                try:
                    log_user_activity(
                        event_type="analysis_run",
                        context="roompact_general_form_analysis",
                        metadata={
                            "selected_forms": len(selected_forms),
                            "analyzed_forms": min(len(selected_forms), max_forms),
                            "form_types": form_types,
                            "date_range": [
                                str(filter_info.get("start_date")),
                                str(filter_info.get("end_date")),
                            ],
                            "custom_prompt": custom_prompt,
                        },
                        user=st.session_state.get("user"),
                    )
                except Exception:
                    pass

                st.subheader("📊 General Analysis Results")
                st.markdown(summary)

                download_data = _build_download(
                    title="General Form Analysis Summary",
                    form_types=form_types,
                    date_range=(filter_info.get("start_date"), filter_info.get("end_date")),
                    analyzed=min(len(selected_forms), max_forms),
                    selected=len(selected_forms),
                    summary=summary,
                    custom_prompt=custom_prompt,
                )
                st.download_button(
                    label="📄 Download Analysis Report",
                    data=download_data,
                    file_name=f"general_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                    key="download_general_analysis",
                )
        else:
            st.info("Select forms above to enable analysis")

    st.divider()

    with st.expander("🔧 API Connection Status", expanded=False):
        config, error = get_roompact_config()
        if error:
            st.error(error)
            st.markdown(
                """
                **Setup Instructions:**
                1. Contact your system administrator to obtain a Roompact API token
                2. Add the token to your Streamlit secrets under the key `roompact_api_token`
                3. Refresh this page to test the connection
                """
            )
            return

        with st.spinner("Testing API connection..."):
            test_data, test_error = make_roompact_request("forms", {"cursor": ""})
            if test_error:
                st.error(f"API connection test failed: {test_error}")
            else:
                st.success("✅ API connection successful")
                total_forms = test_data.get("total_records", 0) if isinstance(test_data, dict) else 0
                st.info(f"📊 Total forms available: {total_forms}")


def individual_reports_viewer() -> None:
    """Fetch and browse individual reports with filters."""
    st.subheader("📄 Individual Reports Viewer")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "📅 Start Date",
            value=datetime.now().date() - timedelta(days=30),
            help="View reports from this date",
            key="individual_start_date",
        )
    with col2:
        end_date = st.date_input(
            "📅 End Date",
            value=datetime.now().date(),
            help="View reports up to this date",
            key="individual_end_date",
        )

    if st.button("🔍 Fetch Reports", type="primary", key="fetch_individual_reports"):
        max_pages = 300
        progress_placeholder = st.empty()

        def show_progress(page_num: int, total_forms: int, oldest_date: str, reached_target: bool) -> None:
            status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
            if oldest_date:
                status += f" | Oldest: {oldest_date}"
            progress_placeholder.info(status)

        with st.spinner("Fetching reports from Roompact..."):
            all_forms, error = fetch_roompact_forms(
                max_pages=max_pages,
                target_start_date=start_date,
                progress_callback=show_progress,
            )

        if error:
            st.error(error)
            return
        if not all_forms:
            st.warning("No forms found.")
            return

        filtered_forms, filter_error = filter_forms_by_date_and_type(
            all_forms, start_date, end_date, []
        )
        if filter_error:
            st.error(filter_error)
            return

        st.session_state["individual_reports"] = filtered_forms
        st.session_state["individual_reports_date_range"] = {
            "start_date": start_date,
            "end_date": end_date,
        }

        if filtered_forms:
            st.success(f"✅ Found {len(filtered_forms)} reports in the selected date range")
        else:
            st.warning("No reports found matching your criteria")

    if "individual_reports" not in st.session_state or not st.session_state["individual_reports"]:
        return

    reports = st.session_state["individual_reports"]
    date_range = st.session_state.get("individual_reports_date_range", {})

    st.markdown("---")
    st.subheader("📊 Filter and View Reports")

    staff_members = set()
    form_types = set()
    for form in reports:
        current_revision = form.get("current_revision", {})
        author = current_revision.get("author", "Unknown")
        form_type = form.get("form_template_name", "Unknown Form")
        if author and author != "Unknown":
            staff_members.add(author)
        if form_type and form_type != "Unknown Form":
            form_types.add(form_type)

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_staff = st.multiselect(
            "👤 Filter by Staff Member",
            options=sorted(list(staff_members)),
            default=[],
            help="Select one or more staff members to filter",
            key="filter_staff",
        )
    with col2:
        selected_form_types = st.multiselect(
            "📝 Filter by Form Type",
            options=sorted(list(form_types)),
            default=[],
            help="Select one or more form types to filter",
            key="filter_form_types",
        )
    with col3:
        sort_order = st.selectbox(
            "📅 Sort By",
            options=["Newest First", "Oldest First"],
            key="sort_order",
        )

    filtered_reports = reports
    if selected_staff:
        filtered_reports = [
            form
            for form in filtered_reports
            if form.get("current_revision", {}).get("author", "") in selected_staff
        ]
    if selected_form_types:
        filtered_reports = [
            form
            for form in filtered_reports
            if form.get("form_template_name", "") in selected_form_types
        ]

    filtered_reports = sorted(
        filtered_reports,
        key=lambda form: _date_for_sort(form.get("current_revision", {}).get("date", "")),
        reverse=(sort_order == "Newest First"),
    )

    st.info(f"**Showing {len(filtered_reports)} of {len(reports)} reports**")

    staff_counts = {}
    for form in filtered_reports:
        author = form.get("current_revision", {}).get("author", "Unknown")
        staff_counts[author] = staff_counts.get(author, 0) + 1

    if filtered_reports:
        with st.expander("📊 Report Counts by Staff Member"):
            for staff, count in sorted(staff_counts.items(), key=lambda item: item[1], reverse=True):
                st.write(f"**{staff}:** {count} report(s)")

    st.markdown("---")
    st.subheader(f"📋 Individual Reports ({len(filtered_reports)})")

    for idx, form in enumerate(filtered_reports, 1):
        current_revision = form.get("current_revision", {})
        form_name = form.get("form_template_name", "Unknown Form")
        author = current_revision.get("author", "Unknown")
        date_str = _format_date(current_revision.get("date", "Unknown date"))

        with st.expander(f"**{idx}.** {form_name} - {author} - {date_str}"):
            st.markdown(f"**Staff Member:** {author}")
            st.markdown(f"**Form Type:** {form_name}")
            st.markdown(f"**Submission Date:** {date_str}")

            st.markdown("---")
            st.markdown("### Form Responses")

            responses = current_revision.get("responses", [])
            if not responses:
                st.info("No responses recorded for this form.")
            else:
                for resp_idx, response in enumerate(responses):
                    field_label = response.get("field_label", "Unknown Field")
                    field_response = response.get("response", "")
                    if field_response and str(field_response).strip():
                        formatted = _format_response(field_response)
                        if len(formatted) > 100:
                            st.markdown(f"**{field_label}:**")
                            st.text_area(
                                label="",
                                value=formatted,
                                height=min(100 + (formatted.count("\n") * 20), 300),
                                disabled=True,
                                key=f"response_{idx}_{resp_idx}_{field_label}",
                                label_visibility="collapsed",
                            )
                        else:
                            st.markdown(f"**{field_label}:** {formatted}")

            st.markdown("---")
            report_markdown = f"""# {form_name}

**Staff Member:** {author}  
**Submission Date:** {date_str}

## Form Responses

"""
            for response in responses:
                field_label = response.get("field_label", "Unknown Field")
                field_response = response.get("response", "")
                if field_response and str(field_response).strip():
                    report_markdown += f"**{field_label}:** {field_response}\n\n"

            st.download_button(
                label="📥 Download Report",
                data=report_markdown,
                file_name=f"{form_name}_{author}_{date_str.replace(':', '-').replace(' ', '_')}.md",
                mime="text/markdown",
                key=f"download_{idx}",
            )


def weekly_reports_viewer(supervisor_id=None) -> None:
    """View weekly reports with optional supervisor scoping and filters."""
    st.markdown("Review finalized and draft weekly reports. Use filters to narrow the view.")

    try:
        admin_client = get_admin_client()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Admin client unavailable: {exc}")
        return

    staff_filter_key = f"wrv_staff_{supervisor_id}" if supervisor_id else "wrv_staff_all"
    start_key = f"wrv_start_{supervisor_id}" if supervisor_id else "wrv_start_all"
    end_key = f"wrv_end_{supervisor_id}" if supervisor_id else "wrv_end_all"

    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input(
            "Start date",
            value=datetime.now().date() - timedelta(days=30),
            key=start_key,
        )
    with col2:
        end_date = st.date_input(
            "End date",
            value=datetime.now().date(),
            key=end_key,
        )
    with col3:
        st.write("")
        st.write("")
        refresh = st.button("🔄 Refresh", key=f"wrv_refresh_{supervisor_id}")

    staff_options = []
    staff_lookup = {}
    try:
        if supervisor_id:
            profiles_resp = (
                admin_client.table("profiles")
                .select("id, full_name, email")
                .eq("supervisor_id", supervisor_id)
                .execute()
            )
            staff_options = profiles_resp.data or []
        else:
            profiles_resp = admin_client.table("profiles").select("id, full_name, email").execute()
            staff_options = profiles_resp.data or []
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load staff list: {exc}")

    for staff in staff_options:
        label = staff.get("full_name") or staff.get("email") or staff.get("id")
        staff_lookup[label] = staff.get("id")

    selected_staff_labels = st.multiselect(
        "Filter by staff",
        options=sorted(list(staff_lookup.keys())),
        key=staff_filter_key,
    )
    selected_staff_ids = [staff_lookup[label] for label in selected_staff_labels]

    if refresh or True:
        query = (
            admin_client.table("reports")
            .select("*")
            .gte("week_ending_date", start_date.isoformat())
            .lte("week_ending_date", end_date.isoformat())
            .order("week_ending_date", desc=True)
        )
        try:
            if supervisor_id and staff_options:
                user_ids = [staff.get("id") for staff in staff_options if staff.get("id")]
                if user_ids:
                    query = query.in_("user_id", user_ids)
            if selected_staff_ids:
                query = query.in_("user_id", selected_staff_ids)

            reports_resp = query.execute()
            reports = reports_resp.data or []
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to load reports: {exc}")
            return

        if not reports:
            st.info("No reports found for the selected filters.")
            return

        st.info(f"Showing {len(reports)} reports")
        for idx, report in enumerate(reports, 1):
            week = report.get("week_ending_date", "Unknown")
            status = report.get("status", "")
            staff_name = report.get("team_member") or report.get("author") or report.get("user_name") or "Unknown"
            well_being = report.get("well_being_rating")
            title = f"{idx}. {staff_name} — Week Ending {week} ({status})"
            with st.expander(title):
                st.markdown(f"**Staff:** {staff_name}")
                st.markdown(f"**Week Ending:** {week}")
                st.markdown(f"**Status:** {status}")
                if well_being is not None:
                    st.markdown(f"**Well-being Rating:** {well_being}")
                if report.get("report_body"):
                    st.markdown("---")
                    st.markdown("**Report Body:**")
                    st.text_area(
                        label="",
                        value=str(report.get("report_body", "")),
                        height=200,
                        disabled=True,
                        key=f"wrv_body_{idx}",
                        label_visibility="collapsed",
                    )
                if report.get("ai_summary"):
                    st.markdown("---")
                    st.markdown("**AI Summary:**")
                    st.markdown(clean_summary_response(report.get("ai_summary", "")))


# Helper utilities
def _format_date(date_str: str) -> str:
    if not date_str:
        return "Unknown date"
    try:
        form_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return form_date.strftime("%Y-%m-%d %I:%M %p")
    except Exception:
        return date_str or "Unknown date"


def _date_for_sort(date_str: str) -> datetime:
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _format_response(field_response) -> str:
    formatted = field_response
    if isinstance(field_response, (list, dict)):
        try:
            if isinstance(field_response, list) and field_response and isinstance(field_response[0], dict):
                items = []
                for item in field_response:
                    if "tag_name" in item:
                        items.append(f"• {item['tag_name']}")
                    else:
                        items.append("• " + ", ".join(f"{k}: {v}" for k, v in item.items()))
                formatted = "\n".join(items)
            else:
                formatted = json.dumps(field_response, indent=2)
        except Exception:
            formatted = str(field_response)
    elif isinstance(field_response, str) and (field_response.startswith("[") or field_response.startswith("{")):
        try:
            parsed = json.loads(field_response.replace("'", '"'))
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                items = []
                for item in parsed:
                    if "tag_name" in item:
                        items.append(f"• {item['tag_name']}")
                    else:
                        items.append("• " + ", ".join(f"{k}: {v}" for k, v in item.items()))
                formatted = "\n".join(items)
            else:
                formatted = json.dumps(parsed, indent=2)
        except Exception:
            formatted = str(field_response)
    else:
        formatted = str(field_response)
    return formatted


def _build_download(
    title: str,
    form_types: list,
    date_range: tuple,
    analyzed: int,
    selected: int,
    summary: str,
    custom_prompt: str,
) -> str:
    start_date, end_date = date_range
    date_range_text = f"{start_date} to {end_date}"
    form_types_text = ", ".join(form_types) if form_types else "Forms"
    return f"""# {title}

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Form Types:** {form_types_text}  
**Date Range:** {date_range_text}  
**Forms Analyzed:** {analyzed} of {selected} selected  
**Custom Prompt Used:** {bool(custom_prompt)}

{summary}

---
Generated by UND Housing & Residence Life Weekly Reporting Tool
"""
