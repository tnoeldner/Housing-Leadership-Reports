import json
from datetime import date

import streamlit as st

from src.ai import call_gemini_ai, clean_summary_response
from src.database import get_admin_client, log_user_activity

FINAL_STATUSES = {"locked", "submitted", "finalized"}


def _default_calendar_range():
    today = date.today()
    year = today.year
    return date(year, 1, 1), date(year, 12, 31)


def _default_fiscal_range():
    today = date.today()
    start_year = today.year if today.month >= 7 else today.year - 1
    return date(start_year, 7, 1), date(start_year + 1, 6, 30)


def _load_profiles(admin_client):
    try:
        resp = admin_client.table("profiles").select("id, full_name, email").order("full_name").execute()
        return resp.data or []
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load staff list: {exc}")
        return []


def _format_staff_label(profile):
    return profile.get("full_name") or profile.get("email") or profile.get("id")


def _fetch_reports(admin_client, start_date, end_date, staff_ids=None):
    query = (
        admin_client.table("reports")
        .select("*")
        .gte("week_ending_date", start_date.isoformat())
        .lte("week_ending_date", end_date.isoformat())
        .order("week_ending_date", desc=True)
    )
    if staff_ids:
        query = query.in_("user_id", staff_ids)
    resp = query.execute()
    return resp.data or []


def _fetch_weekly_summaries(admin_client, start_date, end_date):
    resp = (
        admin_client.table("weekly_summaries")
        .select("week_ending_date, summary_text, created_by")
        .gte("week_ending_date", start_date.isoformat())
        .lte("week_ending_date", end_date.isoformat())
        .order("week_ending_date", desc=True)
        .execute()
    )
    return resp.data or []


def _build_reports_text(reports):
    lines = []
    sorted_reports = sorted(reports, key=lambda r: str(r.get("week_ending_date", "")))
    for report in sorted_reports:
        staff_name = report.get("team_member") or report.get("user_name") or report.get("author") or "Unknown"
        week = report.get("week_ending_date", "Unknown")
        status = report.get("status", "")
        wellbeing = report.get("well_being_rating")
        body = report.get("report_body", {})
        if isinstance(body, dict):
            body_text = json.dumps(body, indent=2)
        else:
            body_text = str(body)
        lines.append(f"\n--- REPORT FOR {staff_name} — Week Ending {week} — Status: {status} ---")
        if wellbeing is not None:
            lines.append(f"Well-being: {wellbeing}")
        lines.append("Report Body:")
        lines.append(body_text)
        ai_summary = report.get("ai_summary")
        if ai_summary:
            lines.append("AI Summary:")
            lines.append(str(ai_summary))
    return "\n".join(lines)


def _build_weekly_summaries_text(summaries):
    lines = []
    sorted_summaries = sorted(summaries, key=lambda s: str(s.get("week_ending_date", "")))
    for summary in sorted_summaries:
        week = summary.get("week_ending_date", "Unknown")
        created_by = summary.get("created_by", "Unknown")
        summary_text = summary.get("summary_text", "")
        lines.append(f"\n--- WEEKLY SUMMARY — Week Ending {week} (created by {created_by}) ---")
        lines.append(str(summary_text))
    return "\n".join(lines)


def _average_wellbeing(reports):
    scores = [r.get("well_being_rating") for r in reports if r.get("well_being_rating") is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def yearly_summaries_page():
    st.title("Yearly & Fiscal Summaries")
    st.write("Use AI to synthesize full-year individual reports and fiscal-year weekly summaries.")

    if "user" not in st.session_state:
        st.warning("Log in to access this page.")
        st.stop()

    if st.session_state.get("role") != "admin":
        st.warning("This page is limited to admins.")
        st.stop()

    try:
        admin_client = get_admin_client()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Admin client unavailable: {exc}")
        st.stop()

    profiles = _load_profiles(admin_client)
    staff_lookup = {_format_staff_label(p): p.get("id") for p in profiles if p.get("id")}

    cal_start_default, cal_end_default = _default_calendar_range()
    fiscal_start_default, fiscal_end_default = _default_fiscal_range()

    tab_reports, tab_summaries = st.tabs([
        "📄 Individual Weekly Reports (Calendar Year)",
        "📅 Weekly Summaries (Fiscal Year)",
    ])

    with tab_reports:
        st.subheader("Calendar Year Reports for Performance Reviews")
        cal_range = st.date_input(
            "Calendar year range",
            value=(cal_start_default, cal_end_default),
            key="yearly_reports_range",
        )
        cal_start, cal_end = cal_range if isinstance(cal_range, (list, tuple)) else (cal_start_default, cal_end_default)
        include_drafts = st.checkbox("Include draft/in-progress reports", value=False, key="yearly_include_drafts")
        selected_staff = st.multiselect(
            "Staff (optional)",
            options=sorted(staff_lookup.keys()),
            key="yearly_staff_filter",
        )
        staff_ids = [staff_lookup[label] for label in selected_staff]

        if st.button("🔄 Load reports", type="primary", key="load_yearly_reports"):
            try:
                reports = _fetch_reports(admin_client, cal_start, cal_end, staff_ids)
                if not include_drafts:
                    reports = [r for r in reports if (r.get("status") or "").lower() in FINAL_STATUSES]
                st.session_state["yearly_reports_data"] = reports
                st.success(f"Loaded {len(reports)} reports from {cal_start} to {cal_end}.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to load reports: {exc}")

        reports = st.session_state.get("yearly_reports_data", [])
        if reports:
            unique_staff = {r.get("user_id") for r in reports if r.get("user_id")}
            avg_wellbeing = _average_wellbeing(reports)
            st.info(
                f"Reports: {len(reports)} | Staff: {len(unique_staff)}"
                + (f" | Avg well-being: {avg_wellbeing}" if avg_wellbeing is not None else "")
            )
            with st.expander("Preview data"):
                st.dataframe(
                    [{
                        "week_ending_date": r.get("week_ending_date"),
                        "staff": r.get("team_member") or r.get("user_name") or r.get("author"),
                        "status": r.get("status"),
                        "well_being_rating": r.get("well_being_rating"),
                    } for r in reports],
                    use_container_width=True,
                )

            default_prompt = (
                "You are preparing a performance evaluation summary using weekly reports for the calendar year. "
                "Highlight accomplishments, growth areas, recurring challenges, well-being trends, and recommended "
                "focus areas for the next cycle. Keep it concise and actionable."
            )
            custom_prompt = st.text_area("AI prompt (optional)", value=default_prompt, height=140, key="yearly_prompt")

            if st.button("🤖 Generate annual summary", type="primary", key="run_yearly_ai"):
                reports_text = _build_reports_text(reports)
                prompt = (
                    f"Prepare an annual performance synthesis for the reports between {cal_start} and {cal_end}.\n"
                    f"Total reports: {len(reports)}. Unique staff: {len(unique_staff)}."
                )
                if avg_wellbeing is not None:
                    prompt += f" Average well-being across reports: {avg_wellbeing}."
                prompt += "\n\nUse the guidance below if provided:\n"
                prompt += custom_prompt
                prompt += "\n\nREPORT DATA:\n"
                prompt += reports_text
                with st.spinner("Generating annual summary..."):
                    try:
                        ai_response = call_gemini_ai(prompt, model_name="models/gemini-2.5-pro", context="annual_reports_summary")
                        cleaned = clean_summary_response(ai_response)
                        st.markdown(cleaned)
                        log_user_activity(
                            event_type="ai_call",
                            context="annual_reports_summary",
                            metadata={"reports": len(reports), "staff": len(unique_staff)},
                        )
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"AI error: {exc}")

            st.download_button(
                label="Download raw report bundle",
                data=_build_reports_text(reports),
                file_name=f"calendar_reports_{cal_start}_{cal_end}.txt",
                mime="text/plain",
                key="download_yearly_reports",
            )
        else:
            st.info("Load reports to summarize the calendar year.")

    with tab_summaries:
        st.subheader("Fiscal Year Weekly Summaries for Annual Report")
        fiscal_range = st.date_input(
            "Fiscal year range",
            value=(fiscal_start_default, fiscal_end_default),
            key="fiscal_range",
        )
        fiscal_start, fiscal_end = fiscal_range if isinstance(fiscal_range, (list, tuple)) else (fiscal_start_default, fiscal_end_default)

        if st.button("🔄 Load weekly summaries", type="primary", key="load_weekly_summaries"):
            try:
                summaries = _fetch_weekly_summaries(admin_client, fiscal_start, fiscal_end)
                st.session_state["yearly_weekly_summaries"] = summaries
                st.success(f"Loaded {len(summaries)} weekly summaries from {fiscal_start} to {fiscal_end}.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to load weekly summaries: {exc}")

        summaries = st.session_state.get("yearly_weekly_summaries", [])
        if summaries:
            st.info(f"Weekly summaries loaded: {len(summaries)}")
            with st.expander("Preview weekly summaries"):
                st.dataframe(
                    [{"week_ending_date": s.get("week_ending_date"), "created_by": s.get("created_by")}
                     for s in summaries],
                    use_container_width=True,
                )

            default_prompt = (
                "You are preparing the departmental annual report using weekly summaries from the fiscal year. "
                "Surface major accomplishments, student impact, risks, and resource needs. Provide 5-7 bullets "
                "that leadership can use directly."
            )
            custom_prompt = st.text_area("AI prompt (optional)", value=default_prompt, height=140, key="fiscal_prompt")

            if st.button("🤖 Generate fiscal-year rollup", type="primary", key="run_fiscal_ai"):
                summaries_text = _build_weekly_summaries_text(summaries)
                prompt = (
                    f"Create a fiscal-year rollup for weekly summaries between {fiscal_start} and {fiscal_end}.\n"
                    f"Total weeks: {len(summaries)}."
                )
                prompt += "\n\nUse the guidance below if provided:\n"
                prompt += custom_prompt
                prompt += "\n\nWEEKLY SUMMARIES DATA:\n"
                prompt += summaries_text
                with st.spinner("Generating fiscal-year rollup..."):
                    try:
                        ai_response = call_gemini_ai(prompt, model_name="models/gemini-2.5-pro", context="fiscal_weekly_rollup")
                        cleaned = clean_summary_response(ai_response)
                        st.markdown(cleaned)
                        log_user_activity(
                            event_type="ai_call",
                            context="fiscal_weekly_rollup",
                            metadata={"weeks": len(summaries)},
                        )
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"AI error: {exc}")

            st.download_button(
                label="Download weekly summaries bundle",
                data=_build_weekly_summaries_text(summaries),
                file_name=f"fiscal_weekly_summaries_{fiscal_start}_{fiscal_end}.txt",
                mime="text/plain",
                key="download_weekly_summaries",
            )
        else:
            st.info("Load weekly summaries to build a fiscal-year rollup.")
