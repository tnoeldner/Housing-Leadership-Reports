import streamlit as st
from src.database import get_admin_client

def saved_reports_page():
    if "user" not in st.session_state:
        st.warning("You must be logged in to view this page.")
        st.stop()
    """View saved duty analyses, staff recognition reports, and weekly summaries"""
    st.title("Saved Reports Archive")
    st.write("View all saved reports: duty analyses, staff recognition, and weekly summaries.")
    tab1, tab2, tab3 = st.tabs(["🛡️ Duty Analyses", "🏆 Staff Recognition", "📅 Weekly Summaries"])
    admin_supabase = get_admin_client()

    with tab1:
        st.subheader("Saved Duty Analyses")
        duty_analyses_response = admin_supabase.table("saved_duty_analyses").select("*").order("created_at", desc=True).execute()
        duty_analyses = getattr(duty_analyses_response, "data", None) or []
        if not duty_analyses:
            st.info("No saved duty analyses found.")
        else:
            for analysis in duty_analyses:
                week = analysis.get('week_ending_date', 'N/A')
                with st.expander(f"Week Ending: {week}"):
                    st.markdown(f"**Created By:** {analysis.get('created_by', 'N/A')}")
                    st.markdown(f"**Analysis:** {analysis.get('analysis_text', 'No analysis available')}")

    with tab2:
        st.subheader("Saved Staff Recognition Reports")
        recognition_response = admin_supabase.table("saved_staff_recognition").select("*").order("created_at", desc=True).execute()
        recognitions = getattr(recognition_response, "data", None) or []
        if not recognitions:
            st.info("No saved staff recognition reports found.")
        else:
            for rec in recognitions:
                week = rec.get('week_ending_date', 'N/A')
                with st.expander(f"Week Ending: {week}"):
                    st.markdown(f"**Created By:** {rec.get('created_by', 'N/A')}")
                    st.markdown(f"**Recognition Report:** {rec.get('recognition_text', 'No recognition available')}")

    with tab3:
        st.subheader("Saved Weekly Summaries")
        summaries_response = admin_supabase.table("weekly_summaries").select("*").order("week_ending_date", desc=True).execute()
        summaries = getattr(summaries_response, "data", None) or []
        if not summaries:
            st.info("No saved weekly summaries found.")
        else:
            for summary in summaries:
                week = summary.get('week_ending_date', 'N/A')
                with st.expander(f"Week Ending: {week}"):
                    st.markdown(f"**Created By:** {summary.get('created_by', 'N/A')}")
                    st.markdown(f"**Summary:** {summary.get('summary_text', 'No summary available')}")
