from pathlib import Path
import json


def load_rubric(supabase, rubric_name, file_path, file_default):
    """
    Try to load rubric from admin_settings, else from file, else fallback default.
    """
    # Try admin_settings
    try:
        row = supabase.table("admin_settings").select("setting_value").eq("setting_name", rubric_name).single().execute()
        if row.data and row.data.get("setting_value"):
            return row.data.get("setting_value", file_default)
    except Exception:
        pass
    # Try file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        pass
    return file_default

def generate_ai_prompt(staff_member, rubric_scores):
    from src.database import get_supabase_client
    supabase = get_supabase_client()
    ascend_rubric = load_rubric(
        supabase,
        "ascend_rubric",
        str(Path('../rubrics/ascend_rubric.md')),
        "ASCEND rubric not found."
    )
    north_rubric = load_rubric(
        supabase,
        "north_rubric",
        str(Path('../rubrics/north_rubric.md')),
        "NORTH rubric not found."
    )
    prompt = f"""
    Evaluate the following staff member based on the ASCEND and NORTH criteria:

    Staff Member: {staff_member['name']}
    ASCEND Score: {rubric_scores['ascend']}
    NORTH Score: {rubric_scores['north']}

    ASCEND Rubric:
    {ascend_rubric}

    NORTH Rubric:
    {north_rubric}

    Based on the above information, provide a summary of how this staff member exemplifies the ASCEND and NORTH criteria.
    """
    return prompt.strip()

def select_best_representative(staff_members):
    best_member = None
    highest_score = -1

    for member in staff_members:
        total_score = member['rubric_scores']['ascend'] + member['rubric_scores']['north']
        if total_score > highest_score:
            highest_score = total_score
            best_member = member

    return best_member

def create_summary_for_best_representative(staff_members):
    best_member = select_best_representative(staff_members)
    if best_member:
        prompt = generate_ai_prompt(best_member, best_member['rubric_scores'])
        return prompt
    return "No staff members available for evaluation."

def get_prompt_template(supabase, prompt_type: str, default_prompt: str) -> str:
    """
    Fetch a prompt template from the admin_settings table, falling back to default if not set.
    """
    try:
        row = supabase.table("admin_settings").select("setting_value").eq("setting_name", prompt_type).single().execute()
        if row.data and row.data.get("setting_value"):
            return row.data.get("setting_value", default_prompt)
    except Exception:
        pass
    return default_prompt

def get_weekly_duty_prompt(supabase) -> str:
    default = (
        """
You are a senior residence life administrator. Analyze the following weekly duty reports and provide a comprehensive summary for leadership, including key incidents, trends, staff response effectiveness, and recommendations for improvement. Use clear markdown with sections for Executive Summary, Incident Analysis, Operational Insights, Facility & Maintenance, and Recommendations. Include actionable insights and highlight any urgent issues.
{reports_text}
"""
    )
    return get_prompt_template(supabase, "weekly_duty_prompt", default)

def get_standard_duty_prompt(supabase) -> str:
    default = (
        """
You are a residence life supervisor. Review the following standard duty reports and summarize key events, staff actions, and any policy or safety concerns. Provide a concise summary for the leadership team.
{reports_text}
"""
    )
    return get_prompt_template(supabase, "standard_duty_prompt", default)

def get_staff_recognition_prompt(supabase) -> str:
    default = (
        """
You are writing a weekly staff recognition summary. From the following staff reports, identify and highlight outstanding contributions, teamwork, and positive impact. Use a warm, professional tone and format as a list of recognitions with staff names and specific actions.
{reports_text}
"""
    )
    return get_prompt_template(supabase, "staff_recognition_prompt", default)