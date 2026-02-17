import streamlit as st
from src.database import supabase

def get_admin_prompt(setting_name: str, default: str) -> str:
    """
    Fetch the prompt template from the admin_settings table, or return the default if not set.
    """
    try:
        row = supabase.table("admin_settings").select("setting_value").eq("setting_name", setting_name).single().execute()
        if row.data and row.data.get("setting_value"):
            return row.data["setting_value"]
    except Exception:
        pass
    return default

def get_prompt_template(supabase_client, prompt_type: str, default_prompt: str) -> str:
    """
    Fetch a prompt template from the admin_settings table, falling back to default if not set.
    """
    try:
        row = supabase_client.table("admin_settings").select("setting_value").eq("setting_name", prompt_type).single().execute()
        if row.data and row.data.get("setting_value"):
            return row.data.get("setting_value", default_prompt)
    except Exception:
        pass
    return default_prompt

def get_weekly_duty_prompt(supabase_client) -> str:
    """Get the weekly duty analysis prompt template"""
    default = """You are a senior residence life administrator. Analyze the following weekly duty reports and provide a comprehensive summary for leadership, including key incidents, trends, staff response effectiveness, and recommendations for improvement. Use clear markdown with sections for Executive Summary, Incident Analysis, Operational Insights, Facility & Maintenance, and Recommendations. Include actionable insights and highlight any urgent issues.
{reports_text}
"""
    return get_prompt_template(supabase_client, "weekly_duty_prompt", default)

def get_standard_duty_prompt(supabase_client) -> str:
    """Get the standard duty analysis prompt template"""
    default = """You are a residence life supervisor. Review the following standard duty reports and summarize key events, staff actions, and any policy or safety concerns. Provide a concise summary for the leadership team.
{reports_text}
"""
    return get_prompt_template(supabase_client, "standard_duty_prompt", default)

def get_staff_recognition_prompt(supabase_client) -> str:
    """Get the staff recognition summary prompt template"""
    default = """You are writing a weekly staff recognition summary. From the following staff reports, identify and highlight outstanding contributions, teamwork, and positive impact. Use a warm, professional tone and format as a list of recognitions with staff names and specific actions.
{reports_text}
"""
    return get_prompt_template(supabase_client, "staff_recognition_prompt", default)

def get_general_form_analysis_prompt(supabase_client) -> str:
    """Get the general form analysis prompt template - analyzes reported data and content"""
    default = """You are a housing and residence life data analyst. Your task is to analyze the following form submissions and provide a comprehensive summary of the data and information reported. 

Focus on:
1. Key themes and patterns across all submissions
2. Specific data points, statistics, or numbers reported by staff
3. Issues, challenges, or concerns raised
4. Activities, events, or initiatives described
5. Notable achievements or successes mentioned
6. Trends or observations across multiple forms

Provide a well-organized summary that helps leadership understand what was reported across the forms. Use clear sections and bullet points to make the information easy to scan. Include specific examples and quotes from the forms where relevant. Do not focus on recognizing individual staff members, but rather on summarizing the actual content and data they reported.

Form Submissions:
{reports_text}
"""
    return get_prompt_template(supabase_client, "general_form_analysis_prompt", default)
