# --- Admin Dashboard Summary Generation ---
def generate_admin_dashboard_summary(selected_date_for_summary, staff_reports_text, duty_reports_section, engagement_reports_section, average_score=0):
    """
    Generate the admin dashboard summary using Gemini AI.
    Args:
        selected_date_for_summary: str, week ending date
        staff_reports_text: str, markdown/text of all staff reports
        duty_reports_section: str, markdown/text of duty reports
        engagement_reports_section: str, markdown/text of engagement reports
        average_score: float, average well-being score
    Returns:
        str: Cleaned summary response
    """
    from pathlib import Path
    from src.config import ASCEND_VALUES, NORTH_VALUES
    from src.ai_prompts import get_admin_prompt

    def load_rubric_text(filename):
        try:
            base_dir = Path(__file__).resolve().parents[1] / "rubrics-integration" / "rubrics"
            return (base_dir / filename).read_text(encoding="utf-8")
        except Exception:
            return ""

    def escape_braces(text):
        # Prevent str.format from treating rubric placeholders like {__app_id} as format keys
        return text.replace("{", "{{").replace("}", "}}") if isinstance(text, str) else text

    ascend_rubric = escape_braces(load_rubric_text("ascend_rubric.md"))
    north_rubric = escape_braces(load_rubric_text("north_rubric.md"))

    default_dashboard_prompt = f"""
You are an executive assistant for the Director of Housing & Residence Life at UND. Your task is to synthesize multiple team reports from the week ending {{selected_date_for_summary}} into a single, comprehensive summary report.

IMPORTANT: Start your response immediately with the first section heading. Do not include any introductory text, cover page text, or phrases like "Here is the comprehensive summary report" or "Weekly Summary Report: Housing & Residence Life". Begin directly with the Executive Summary section.

DATA SOURCES AVAILABLE:
1. Weekly staff reports from residence life team members
2. Weekly duty reports analysis (if available) - quantitative data on incidents, safety, maintenance, and operations
3. Weekly engagement analysis (if available) - event programming, attendance data, community engagement activities

The report MUST contain the following sections, in this order, using markdown headings exactly as shown:

## Executive Summary
A 2-3 sentence high-level overview of the week's key takeaways.

## ASCEND Framework Summary
ASCEND pillars (use EXACT values): {ASCEND_VALUES}. Start with: "ASCEND UND Housing is a unified performance framework for the University of North Dakota's Housing and Residence Life staff. It is designed to clearly define job expectations and drive high performance across the department." Use the ASCEND rubric below to choose the best-fit pillar for each activity. For each pillar include bullet points that reference staff by name and date.

ASCEND rubric:
{ascend_rubric}

## Guiding NORTH Pillars Summary
Guiding NORTH pillars (use EXACT values): {NORTH_VALUES}. Start with: "Guiding NORTH is our core communication standard for UND Housing & Residence Life. It's a simple, five-principle framework that ensures every interaction with students and parents is clear, consistent, and supportive. Its purpose is to build trust and provide reliable direction, making students feel valued and well-supported throughout their housing journey." Use the NORTH rubric below to choose the best-fit pillar for each activity. For each pillar include bullet points that reference staff by name and date.

NORTH rubric:
{north_rubric}

## UND LEADS Summary
Start with: "UND LEADS is a roadmap that outlines the university's goals and aspirations. It's built on the idea of empowering people to make a difference and passing on knowledge to future generations." Analyze activities under these pillars with staff names and dates where applicable: Learning, Equity, Affinity, Discovery, Service.

## Overall Staff Well-being
Start with "The average well-being score for the week was {{average_score}} out of 5." Provide a short qualitative summary and include a "Staff to Connect With" subsection listing low scores or concerning comments.

## Campus Events Summary
Create a markdown table with this exact format:

| Event/Committee | Date | Attendees | Alignment |
|-----------------|------|-----------|-----------|
| Event Name | YYYY-MM-DD | Staff Member Name | ASCEND: Category, NORTH: Category |

Include all campus events and committee meetings attended by staff this week. Group multiple attendees for the same event in one row.

## For the Director's Attention
List items needing director-level attention; if none, state "No specific concerns were raised for the Director this week."

## Key Challenges
Bullet-point significant or recurring challenges, noting who reported them.

## Operational & Safety Summary
If duty reports exist, include:

### Quantitative Metrics
Hall-by-hall table (keep columns exactly):

| Hall/Building | Total Reports | Lockouts | Maintenance | Policy Violations | Safety Concerns | Staff Responses |
|---------------|---------------|----------|-------------|-------------------|-----------------|-----------------|
| Hall Name | # | # | # | # | # | # |

Add a totals row at the bottom.

### Trending Issues
Patterns in lockouts, maintenance, policy violations.

### Staff Response Effectiveness
Assessment of duty staff performance and response times.

### Safety & Security Highlights
Critical incidents and follow-up actions needed.

## Upcoming Projects & Initiatives
Bullet key upcoming projects based on the 'Lookahead' sections.

CRITICAL FORMATTING REQUIREMENTS:

STAFF REPORTS DATA:
{{staff_reports_text}}

DUTY REPORTS DATA:
{{duty_reports_section}}

ENGAGEMENT REPORTS DATA:
{{engagement_reports_section}}
"""
    prompt_template = get_admin_prompt("dashboard_prompt", default_dashboard_prompt)
    prompt = prompt_template.format(
        selected_date_for_summary=selected_date_for_summary,
        staff_reports_text=(staff_reports_text or "").replace("{", "{{").replace("}", "}}"),
        duty_reports_section=(duty_reports_section or "").replace("{", "{{").replace("}", "}}"),
        engagement_reports_section=(engagement_reports_section or "").replace("{", "{{").replace("}", "}}"),
        average_score=average_score
    )
    import streamlit as st
    try:
        response_text = call_gemini_ai(prompt, model_name="models/gemini-2.5-pro", context="admin_dashboard_summary")
        st.info(f"DEBUG: Extracted response_text: {repr(response_text)}")
        if not response_text or not str(response_text).strip():
            st.info("Prompt sent to AI:")
            st.code(prompt)
            st.info("Input data summary:")
            st.code(staff_reports_text)
            st.error("DEBUG: AI did not return a summary.")
            return "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."
        cleaned = clean_summary_response(response_text)
        st.info(f"DEBUG: Cleaned summary: {repr(cleaned)}")
        return cleaned
    except Exception as e:
        import traceback
        st.error(f"Error generating AI summary: {e}")
        st.info(f"DEBUG: Exception traceback:\n{traceback.format_exc()}")
        return f"Error generating AI summary: {str(e)}"
import streamlit as st
import json
import re
import google.generativeai as genai
from src.config import get_secret
from src.database import get_admin_client, get_user_client, log_user_activity

client = None


import streamlit as st
import json
import google.generativeai as genai
from src.config import get_secret
from src.database import get_admin_client

AI_RATE_CARD = {
    # USD per 1K tokens (prompt, response) — replace with your actual rate card
    "models/gemini-2.5-flash": {"prompt": 0.000018, "response": 0.000054},
    "models/gemini-2.5-pro": {"prompt": 0.000125, "response": 0.000375},
    "gemini-2.5-flash": {"prompt": 0.000018, "response": 0.000054},
    "gemini-2.5-pro": {"prompt": 0.000125, "response": 0.000375},
}


def extract_usage_metadata(response):
    """Best-effort extraction of usage metadata from Gemini responses."""
    if response is None:
        return None

    # Common attributes
    for attr in ["usage_metadata", "usageMetadata"]:
        val = getattr(response, attr, None)
        if val:
            return val

    # Nested result object
    res = getattr(response, "result", None) or getattr(response, "_result", None)
    if res:
        for attr in ["usage_metadata", "usageMetadata"]:
            val = getattr(res, attr, None)
            if val:
                return val

    # Fallback to dict form if available
    to_dict = getattr(response, "to_dict", None)
    if callable(to_dict):
        try:
            data = to_dict()
            usage = data.get("usage_metadata") or data.get("usageMetadata")
            if usage:
                return usage
            result = data.get("result") or data.get("_result")
            if result:
                return result.get("usage_metadata") or result.get("usageMetadata")
        except Exception:
            pass
    return None


def resolve_user_identity(explicit_user_id=None, explicit_email=None, explicit_user=None):
    """Best-effort resolution of user id/email from explicit args, session_state, or Supabase auth."""
    uid = explicit_user_id
    email = explicit_email

    # Helper to safely pull from st.session_state even though it's not a dict
    def ss_get(key, default=None):
        try:
            getter = getattr(st.session_state, "get", None)
            if callable(getter):
                return getter(key, default)
            # Fallback attribute access
            return getattr(st.session_state, key, default)
        except Exception:
            return default

    user_obj = explicit_user or ss_get("user")
    if user_obj:
        uid = uid or getattr(user_obj, "id", None) or (user_obj.get("id") if isinstance(user_obj, dict) else None)
        email = email or getattr(user_obj, "email", None) or (user_obj.get("email") if isinstance(user_obj, dict) else None)

    uid = uid or ss_get("user_id")
    email = email or ss_get("user_email") or ss_get("email")

    # Fallback: pull from Supabase auth if access_token is present
    if uid is None or email is None:
        try:
            user_client = get_user_client()
            current = user_client.auth.get_user()
            current_user = getattr(current, "user", current)
            if current_user:
                uid = uid or getattr(current_user, "id", None) or (current_user.get("id") if isinstance(current_user, dict) else None)
                email = email or getattr(current_user, "email", None) or (current_user.get("email") if isinstance(current_user, dict) else None)
        except Exception:
            pass
    return uid, email


def log_ai_usage(model_name, usage, context=None, user_id=None, user_email=None):
    """Persist AI usage metadata to Supabase for cost tracking. Logs even if usage metadata is missing."""
    # Support multiple possible usage field names from Gemini responses
    def _get(name):
        return getattr(usage, name, None) if usage and not isinstance(usage, dict) else (usage.get(name) if isinstance(usage, dict) else None)

    prompt_tokens = _get("prompt_token_count") or _get("input_token_count") or _get("input_tokens")
    response_tokens = _get("candidates_token_count") or _get("output_token_count") or _get("output_tokens")
    total_tokens = _get("total_token_count") or _get("total_tokens") or (
        ((prompt_tokens or 0) + (response_tokens or 0)) if (prompt_tokens is not None or response_tokens is not None) else None
    )

    # Normalize missing token counts to zero to avoid null inserts in ai_usage_logs
    prompt_tokens = 0 if prompt_tokens is None else prompt_tokens
    response_tokens = 0 if response_tokens is None else response_tokens
    total_tokens = (prompt_tokens + response_tokens) if total_tokens is None else total_tokens

    rate = AI_RATE_CARD.get(model_name, AI_RATE_CARD.get(model_name.replace("models/", ""), {"prompt": 0, "response": 0}))
    prompt_cost = ((prompt_tokens or 0) / 1000.0) * rate.get("prompt", 0)
    response_cost = ((response_tokens or 0) / 1000.0) * rate.get("response", 0)
    cost_usd = prompt_cost + response_cost

    try:
        client = get_admin_client()
        user_id, user_email = resolve_user_identity(user_id, user_email)

        payload = {
            "model": model_name,
            "prompt_tokens": prompt_tokens,
            "response_tokens": response_tokens,
            "total_tokens": total_tokens,
            "cost_usd": round(cost_usd, 6),
            "context": context or "",
            "user_id": user_id,
            "user_email": user_email,
        }
        client.table("ai_usage_logs").insert(payload).execute()
        # Also log activity for attribution
        log_user_activity(
            event_type="ai_call",
            context=context or model_name,
            metadata={
                "model": model_name,
                "prompt_tokens": prompt_tokens,
                "response_tokens": response_tokens,
                "total_tokens": total_tokens,
                "cost_usd": round(cost_usd, 6),
            },
            user_id=user_id,
            user_email=user_email,
        )
    except Exception as e:
        # Emit a visible warning so we can debug RLS/credential issues in production
        try:
            st.warning(f"AI usage log insert failed: {type(e).__name__}: {e}")
        except Exception:
            pass
        print(f"[WARN] ai_usage_logs insert failed: {type(e).__name__}: {e}")
        return


def call_gemini_ai(prompt, model_name="models/gemini-2.5-flash", context=None):
    # Always initialize debug info in session state
    api_key = get_secret("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing Google AI API key. Please check your secrets or environment variables.")
    try:
        user_id, user_email = resolve_user_identity()
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content([{ "role": "user", "parts": [{"text": prompt}] }])
        # Log usage/cost if available (robust extraction)
        usage = extract_usage_metadata(response)
        log_ai_usage(model_name, usage, context=context, user_id=user_id, user_email=user_email)
        try:
            import streamlit as st  # local import to avoid dependency when not in Streamlit
            st.session_state["last_ai_usage"] = usage
        except Exception:
            pass
        # Extract text from response
        response_text = None
        try:
            if hasattr(response, 'text') and response.text:
                response_text = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                response_text = response.candidates[0].content.parts[0].text
            elif hasattr(response, 'result') and hasattr(response.result, 'candidates') and response.result.candidates:
                response_text = response.result.candidates[0].content.parts[0].text
            else:
                response_text = str(response)
        except Exception:
            response_text = str(response)
        return response_text
    except Exception as e:
        import traceback
        # Raise error to be handled by caller
        raise RuntimeError(f"AI error: {e}\nTraceback:\n{traceback.format_exc()}")

def clean_summary_response(text):
    if not text:
        return text
    cleaned_text = text.strip()
    # ...existing code for cleaning...
    return cleaned_text

def generate_individual_report_summary(items_to_categorize):
    """
    Generate a unique summary for an individual report using Gemini AI.
    items_to_categorize: list of dicts representing report items (successes/challenges/events)
    Returns a cleaned summary string.
    """
    # Accept additional context via st.session_state for richer prompt
    team_member = st.session_state.get("full_name") or st.session_state.get("title") or st.session_state.get("user", {}).get("email", "Unknown")
    week_ending_date = st.session_state.get("active_saturday") or st.session_state.get("week_ending_date")
    professional_development = st.session_state.get("prof_dev", "")
    key_topics_lookahead = st.session_state.get("lookahead", "")
    personal_check_in = st.session_state.get("personal_check_in", "")
    well_being_rating = st.session_state.get("well_being_rating", "")
    director_concerns = st.session_state.get("director_concerns", "")
    report_json = json.dumps(items_to_categorize, indent=2)
    from src.ai_prompts import get_admin_prompt
    default_individual_prompt = """
You are an executive assistant for the Director of Housing & Residence Life at UND. Your task is to synthesize the following individual staff report into a concise, director-focused summary for the week ending {week_ending_date}. Your summary should:
- Reference the staff member by name: {team_member}
- Highlight professional development, engagement, successes, and challenges
- Include any personal well-being check-in and overall well-being score ({well_being_rating}/5)
- Note any concerns for the director and key topics/lookahead
- Use clear, professional language and reference specific activities where possible
- Be written for the director to quickly understand the staff member's overall week and priorities

STAFF REPORT DATA:
{report_json}

Professional Development: {professional_development}
Key Topics & Lookahead: {key_topics_lookahead}
Personal Check-in: {personal_check_in}
Director Concerns: {director_concerns}
Well-being Rating: {well_being_rating}
"""
    prompt_template = get_admin_prompt("individual_prompt", default_individual_prompt)
    prompt = prompt_template.format(
        week_ending_date=week_ending_date,
        team_member=team_member,
        well_being_rating=well_being_rating,
        report_json=report_json,
        professional_development=professional_development,
        key_topics_lookahead=key_topics_lookahead,
        personal_check_in=personal_check_in,
        director_concerns=director_concerns
    )
    try:
        response_text = call_gemini_ai(prompt, model_name="models/gemini-2.5-flash", context="individual_report_summary")
        st.session_state["raw_ai_response"] = response_text
        return clean_summary_response(response_text)
    except Exception as e:
        st.session_state["raw_ai_response"] = f"AI error: {e}"
        return f"Error generating individual summary: {e}"
from google import genai
import streamlit as st
import re
import google.generativeai as genai

client = None

# Initialize Google Gemini AI using google-genai SDK
def init_ai():
    import streamlit as st
    import google.generativeai as genai
    from src.config import get_secret
    api_key = get_secret("GOOGLE_API_KEY")
    if not api_key:
        st.error("❌ Missing Google AI API key. Please check your secrets or environment variables.")
        st.stop()
    try:
        genai.configure(api_key=api_key)
        # Return True to indicate initialization was successful
        return True
    except Exception as e:
        st.error(f"❌ Google AI API key configuration failed: {e}")
        st.info("Please update your Google AI API key in secrets or environment variables.")
        st.stop()


# Return a list of available Gemini models
def get_gemini_models():
    import google.generativeai as genai
    try:
        init_ai()
        models = list(genai.list_models())
        return models
    except Exception as e:
        return f"Error listing models: {e}"

# Send a test prompt to Gemini and return the response or error
def gemini_test_prompt(prompt="Hello Gemini, are you working?", model_name="gemini-2.5-pro"):
    import google.generativeai as genai
    try:
        init_ai()
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        return getattr(response, "text", str(response))
    except Exception as e:
        return f"Gemini model error: {e}"

def clean_summary_response(text):
    """Remove unwanted introductory text from AI-generated summaries"""
    if not text:
        return text
        
    cleaned_text = text.strip()
    
    # Apply multiple cleanup passes for thorough cleaning
    for _ in range(3):  # Multiple passes to catch nested patterns
        original_length = len(cleaned_text)
        
        # Remove comprehensive intro patterns (must handle multi-line)
        intro_patterns = [
            # Remove "Here is the comprehensive..." patterns
            r"^Here is the comprehensive summary report.*?(?=\*\*Executive Summary\*\*|\*\*[A-Z]|\n\s*\d+\.|$)",
            r"^Here is a comprehensive summary.*?(?=\*\*Executive Summary\*\*|\*\*[A-Z]|\n\s*\d+\.|$)",
            r"^Based on the.*?reports.*?(?=\*\*Executive Summary\*\*|\*\*[A-Z]|\n\s*\d+\.|$)",
            
            # Remove complete memo format (very comprehensive)
            r"^Weekly Summary Report:.*?\n.*?To\n.*?\n.*?From\n.*?\n.*?Date\n.*?\n.*?Subject\n.*?\n\n",
            r"^Weekly Summary Report: Housing & Residence Life.*?(?=\*\*Executive Summary\*\*|\*\*[A-Z])",
            
            # Remove any remaining intro text before executive summary
            r"^.*?(?=## Executive Summary|\*\*Executive Summary\*\*)",
            
            # Remove other intro variations
            r"^Here is the.*?summary.*?(?=\*\*Executive Summary\*\*|\*\*[A-Z]|\n\s*\d+\.|$)",
            r"^Below is the.*?summary.*?(?=\*\*Executive Summary\*\*|\*\*[A-Z]|\n\s*\d+\.|$)",
            r"^This comprehensive.*?(?=\*\*Executive Summary\*\*|\*\*[A-Z]|\n\s*\d+\.|$)",
        ]
        
        # Apply each pattern with DOTALL flag
        for pattern in intro_patterns:
            cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        # Aggressive line-by-line cleanup for memo components
        lines = cleaned_text.split('\n')
        filtered_lines = []
        skip_until_content = True
        
        for line in lines:
            line_stripped = line.strip()
            
            # Skip memo header components
            if skip_until_content:
                if any(keyword in line_stripped.lower() for keyword in [
                    'weekly summary report', 'housing & residence life', 
                    'director of housing', 'executive assistant',
                    'weekly synthesis', 'memorandum'
                ]):
                    continue
                if line_stripped in ['To', 'From', 'Date', 'Subject', ''] or re.match(r'^\d{4}-\d{2}-\d{2}$', line_stripped):
                    continue
                # Start including content when we hit actual content
                if line_stripped.startswith('##') or line_stripped.startswith('**') or line_stripped.startswith('#') or len(line_stripped) > 50:
                    skip_until_content = False
            
            if not skip_until_content:
                filtered_lines.append(line)
        
        cleaned_text = '\n'.join(filtered_lines).strip()
        
        # Additional cleanup patterns
        cleanup_patterns = [
            r'^\s*\n+',  # Remove leading newlines
            r'^---+\s*\n*',  # Remove separator lines
            r'^\s*$\n',  # Remove empty lines at start
        ]
        
        for pattern in cleanup_patterns:
            cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.MULTILINE)
        
        cleaned_text = cleaned_text.strip()
        
        # If no changes were made, break out of the loop
        if len(cleaned_text) == original_length:
            break
    
    return cleaned_text

def extract_und_leads_section(summary_text):
    """Extract the UND LEADS Summary section from a weekly summary"""
    if not summary_text:
        return "No summary text provided."
    
    # Use multiple approaches to extract the complete UND LEADS section
    
    # Method 1: Look for markdown header "## UND LEADS Summary" (most common format from AI prompts)
    pattern1 = r'(##\s*UND LEADS Summary.*?)(?=\n##\s*(?!UND LEADS)(?!#)|$)'
    match = re.search(pattern1, summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        extracted = match.group(1).strip()
        # Make sure we got substantial content (more than just the header)
        if len(extracted) > 100:  # Should have more than just the header
            return extracted
        else:
            # Try to find more content after the header manually
            header_pos = summary_text.find("## UND LEADS Summary")
            if header_pos != -1:
                remaining_text = summary_text[header_pos:]
                # Look for the next main section header (## but not ###)
                next_section = re.search(r'\n##\s*(?!UND LEADS)(?!#)', remaining_text, re.IGNORECASE)
                if next_section:
                    extracted = remaining_text[:next_section.start()].strip()
                else:
                    # Take a reasonable chunk if no next section found
                    extracted = remaining_text[:2000].strip()  # Increased size
                return extracted
            return extracted
    
    # Method 2: Look for the exact numbered section pattern from the prompt
    # Pattern looks for "4. **UND LEADS Summary**" until "5. **Overall Staff Well-being**"
    pattern2 = r'(4\.\s*\*\*UND LEADS Summary\*\*.*?)(?=5\.\s*\*\*Overall Staff Well-being|$)'
    match = re.search(pattern2, summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Method 3: Look for "**UND LEADS Summary**" until "**Overall Staff Well-being**"
    pattern3 = r'(\*\*UND LEADS Summary\*\*.*?)(?=\*\*Overall Staff Well-being|$)'
    match = re.search(pattern3, summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Method 4: Look for numbered section 4 until numbered section 5
    pattern4 = r'(4\.\s*\*\*UND LEADS.*?)(?=5\.\s*\*\*|$)'
    match = re.search(pattern4, summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Method 5: Find UND LEADS section and capture everything until next major section
    # This looks for common section patterns that follow UND LEADS
    pattern5 = r'(\*\*UND LEADS Summary\*\*.*?)(?=\n\s*\*\*(?:Overall|Campus Events|For the Director|Key Challenges|Upcoming Projects)|$)'
    match = re.search(pattern5, summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Method 6: Simple extraction - get UND LEADS until any major section marker
    pattern6 = r'(\*\*UND LEADS Summary\*\*.*?)(?=\n\s*[5-9]\.\s*\*\*|\n\s*##\s+[A-Z]|\n\s*\*\*[A-Z][^*]*\*\*(?!\s*:)|$)'
    match = re.search(pattern6, summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Method 7: Look for markdown header followed by content until next header (broader pattern)
    pattern7 = r'(##\s*UND LEADS.*?)(?=\n##\s*(?!UND LEADS)(?!#)|$)'
    match = re.search(pattern7, summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        extracted = match.group(1).strip()
        # Make sure we have substantial content
        if len(extracted) > 100:
            return extracted
    
    # Method 8: Improved markdown header extraction
    md_pattern = r'##\s*UND LEADS\s*Summary?\s*(.*?)(?=\n##\s*(?!UND LEADS)|$)'
    match = re.search(md_pattern, summary_text, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1).strip()
        if content and len(content) > 10:  # Make sure we have actual content, not just whitespace
            return f"## UND LEADS Summary\n\n{content}"
    
    # Method 9: Last resort - find any UND LEADS header and extract content
    header_patterns = [
        r'\*\*UND LEADS Summary\*\*',
        r'##\s*UND LEADS Summary',
        r'##\s*UND LEADS'
    ]
    
    for header_pattern in header_patterns:
        header_match = re.search(header_pattern, summary_text, re.IGNORECASE)
        if header_match:
            # Find the start position and try to extract content manually
            start_pos = header_match.start()
            remaining_text = summary_text[start_pos:]
            
            # Look for section breaks in the remaining text
            section_breaks = [
                r'\n\s*[5-9]\.\s*\*\*',  # Numbered sections 5-9
                r'\n\s*##\s+(?!UND LEADS)',           # Markdown h2 headers (not UND LEADS)
                r'\n\s*\*\*(?:Overall|Campus|For the|Key|Upcoming)',  # Common next section names
                r'\n\s*##\s*Guiding NORTH'  # Next section in template
            ]
            
            end_pos = len(remaining_text)
            for break_pattern in section_breaks:
                break_match = re.search(break_pattern, remaining_text)
                if break_match:
                    end_pos = min(end_pos, break_match.start())
            
            extracted = remaining_text[:end_pos].strip()
            if len(extracted) > 50:  # Make sure we got substantial content
                return extracted
            else:
                return f"**UND LEADS Summary**\n\nUND LEADS section found but content appears incomplete. Content length: {len(extracted)}. Preview: {extracted[:100]}..."
    
    # No UND LEADS section found at all
    return "Could not find UND LEADS section in this summary. Please check the summary format."

def create_duty_report_summary(selected_forms, start_date, end_date):
    """Create a standard comprehensive duty report analysis"""
    if not selected_forms:
        return {"summary": "No duty reports selected for analysis."}
    
    try:
        from src.ai_prompts import get_weekly_duty_prompt
        # Prepare duty report data for AI analysis
        reports_text = f"\n=== DUTY REPORTS ANALYSIS ===\n"
        reports_text += f"Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n"
        reports_text += f"Total Reports: {len(selected_forms)}\n\n"
        for i, form in enumerate(selected_forms, 1):
            current_revision = form.get('current_revision', {})
            form_name = form.get('form_template_name', 'Unknown Form')
            author = current_revision.get('author', 'Unknown')
            date_str = current_revision.get('date', 'Unknown date')
            reports_text += f"\n--- REPORT {i}: {form_name} ---\n"
            reports_text += f"Staff: {author}\n"
            reports_text += f"Date: {date_str}\n\n"
            # Process responses
            responses = current_revision.get('responses', [])
            for response in responses:
                field_label = response.get('field_label', 'Unknown Field')
                field_response = response.get('response', '')
                if field_response and str(field_response).strip():
                    reports_text += f"**{field_label}:** {field_response}\n"
            reports_text += "\n" + "="*50 + "\n"
        # Use admin-edited prompt template
        import streamlit as st
        from src.database import supabase
        prompt_template = get_weekly_duty_prompt(supabase)
        prompt = prompt_template.format(reports_text=reports_text)
        # Use centralized call wrapper for logging/user attribution
        with st.spinner(f"AI is analyzing {len(selected_forms)} duty reports..."):
            response_text = call_gemini_ai(prompt, model_name="models/gemini-2.5-flash", context="duty_analysis")
            if not response_text or not str(response_text).strip():
                return {"summary": "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."}
            return {"summary": response_text}
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            return {"summary": f"⚠️ API Quota Exceeded: The analysis request was too large. Please try selecting a shorter date range or fewer reports. (Error: {error_msg})"}
        return {"summary": f"Error generating duty report summary: {error_msg}"}

def summarize_form_submissions(selected_forms, max_forms=10):
    """Use AI to summarize selected form submissions"""
    if not selected_forms:
        return "No forms selected for summarization."
    
    try:
        from src.ai_prompts import get_general_form_analysis_prompt
        # Limit to prevent token overflow
        forms_to_process = selected_forms[:max_forms]
        # Prepare form data for AI analysis
        forms_text = ""
        for i, form in enumerate(forms_to_process, 1):
            current_revision = form.get('current_revision', {})
            form_name = form.get('form_template_name', 'Unknown Form')
            author = current_revision.get('author', 'Unknown')
            date = current_revision.get('date', 'Unknown date')
            forms_text += f"\n=== FORM {i}: {form_name} ===\n"
            forms_text += f"Submitted by: {author}\n"
            forms_text += f"Date: {date}\n\n"
            # Process responses
            responses = current_revision.get('responses', [])
            for response in responses:
                field_label = response.get('field_label', 'Unknown Field')
                field_response = response.get('response', '')
                if field_response and str(field_response).strip():
                    forms_text += f"**{field_label}:** {field_response}\n"
        # Use admin-edited prompt template for staff recognition
        import streamlit as st
        from src.database import supabase
        prompt_template = get_general_form_analysis_prompt(supabase)
        prompt = prompt_template.format(reports_text=forms_text)
        with st.spinner("AI is analyzing form submissions..."):
            response_text = call_gemini_ai(prompt, model_name="models/gemini-2.5-pro", context="form_analysis")
            if not response_text or not str(response_text).strip():
                st.info("Prompt sent to AI:")
                st.code(prompt)
                st.info("Input data summary:")
                st.code(forms_text)
                return "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."
            return response_text
    except Exception as e:
        return f"Error generating AI summary: {str(e)}"
