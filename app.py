import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta, date, time as dt_time
from supabase import create_client, Client
import google.generativeai as genai
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    # Fallback for older Python versions
    from datetime import timezone
    def ZoneInfo(tz):
        if tz == "US/Central":
            return timezone.utc  # Simplified fallback
        return timezone.utc
import time

from collections import Counter
import smtplib
import re
import email.message
from io import BytesIO
import base64
import os
import requests

# --- Page Configuration ---
st.set_page_config(page_title="Weekly Impact Report", page_icon="🚀", layout="wide")

# --- Connections ---
@st.cache_resource
def init_connection():
    url = os.getenv("SUPABASE_URL") or st.secrets.get("supabase_url")
    key = os.getenv("SUPABASE_KEY") or st.secrets.get("supabase_key")
    api_key = os.getenv("GOOGLE_API_KEY") or st.secrets.get("google_api_key")
    
    # Validate required keys exist
    if not url or not key:
        st.error("❌ Missing Supabase configuration. Please check your secrets or environment variables.")
        st.stop()
    
    if not api_key:
        st.error("❌ Missing Google AI API key. Please check your secrets or environment variables.")
        st.stop()
    
    # Test Google AI API key validity
    try:
        genai.configure(api_key=api_key)
        # Quick test to validate the API key works
        test_model = genai.GenerativeModel("models/gemini-2.5-pro")
        # Don't actually call the API, just configure it
    except Exception as e:
        st.error(f"❌ Google AI API key configuration failed: {e}")
        st.info("Please update your Google AI API key in secrets or environment variables.")
        st.stop()
    
    return create_client(url, key)

supabase: Client = init_connection()

# --- CONSTANTS ---
ASCEND_VALUES = ["Accountability", "Service", "Community", "Excellence", "Nurture", "Development", "N/A"]
NORTH_VALUES = ["Nurturing", "Operational", "Resource", "Transformative", "Holistic", "N/A"]
CORE_SECTIONS = {
    "students": "Students/Stakeholders",
    "projects": "Projects",
    "collaborations": "Collaborations",
    "responsibilities": "General Job Responsibilities",
    "staffing": "Staffing/Personnel",
    "kpis": "KPIs",
    "events": "Campus Events/Committees",
}

# --- Helper Functions ---
def get_deadline_settings():
    """Get the current deadline configuration from admin settings"""
    try:
        # Try to get from database first (when table exists)
        settings_response = supabase.table("admin_settings").select("*").eq("setting_name", "report_deadline").execute()
        if settings_response.data:
            # JSONB is already parsed as dict, no need for json.loads
            return settings_response.data[0]["setting_value"]
    except Exception as e:
        # If there's an error, we'll use fallback
        print(f"Database settings error: {e}")  # For debugging
    
    # Check session state for temporary storage
    if "admin_deadline_settings" in st.session_state:
        return st.session_state["admin_deadline_settings"]
    
    # Default settings if nothing is configured
    return {"day_of_week": 0, "hour": 16, "minute": 0, "grace_hours": 16}

def calculate_deadline_info(now):
    """Calculate deadline information based on current time and settings"""
    deadline_config = get_deadline_settings()
    
    deadline_day = deadline_config["day_of_week"]  # 0 = Monday
    deadline_hour = deadline_config["hour"]
    deadline_minute = deadline_config["minute"]
    grace_hours = deadline_config["grace_hours"]
    
    # Handle both datetime objects and string dates
    if isinstance(now, str):
        # If it's a string date, convert to datetime and use current time as reference
        try:
            week_ending_date = datetime.strptime(now, "%Y-%m-%d").date()
            # Use current time for comparison
            current_time = datetime.now(ZoneInfo("America/Chicago"))
            current_weekday = current_time.weekday()
            
            # Calculate deadline for the specific week
            deadline_date = week_ending_date + timedelta(days=(deadline_day - 5) % 7 + (1 if deadline_day <= 5 else 0))
            deadline_datetime = datetime.combine(deadline_date, datetime.min.time().replace(hour=deadline_hour, minute=deadline_minute)).replace(tzinfo=ZoneInfo("America/Chicago"))
            grace_end_datetime = deadline_datetime + timedelta(hours=grace_hours)
            
            # Check if deadline has passed
            deadline_passed = current_time > deadline_datetime
            in_grace_period = current_time <= grace_end_datetime and current_time > deadline_datetime
            
            return {
                "active_saturday": week_ending_date,
                "deadline": deadline_datetime,
                "grace_end": grace_end_datetime,
                "deadline_passed": deadline_passed,
                "in_grace_period": in_grace_period
            }
        except ValueError:
            # If string parsing fails, fall back to current time
            now = datetime.now(ZoneInfo("America/Chicago"))
    
    # Calculate the current week's Saturday
    current_weekday = now.weekday()  # Monday is 0, Sunday is 6
    days_to_saturday = 5 - current_weekday
    this_saturday = now.date() + timedelta(days=days_to_saturday)

    # Calculate deadline for this week
    deadline_date = this_saturday + timedelta(days=(deadline_day - 5) % 7 + (1 if deadline_day <= 5 else 0))
    deadline_datetime = datetime.combine(deadline_date, datetime.min.time().replace(hour=deadline_hour, minute=deadline_minute))
    deadline_datetime = deadline_datetime.replace(tzinfo=ZoneInfo("America/Chicago"))
    grace_end = deadline_datetime + timedelta(hours=grace_hours)

    # If current time is after grace period, advance to next Saturday
    if now > grace_end:
        # Next Saturday
        active_saturday = this_saturday + timedelta(days=7)
        # Recalculate deadline for next week
        deadline_date = active_saturday + timedelta(days=(deadline_day - 5) % 7 + (1 if deadline_day <= 5 else 0))
        deadline_datetime = datetime.combine(deadline_date, datetime.min.time().replace(hour=deadline_hour, minute=deadline_minute))
        deadline_datetime = deadline_datetime.replace(tzinfo=ZoneInfo("America/Chicago"))
        grace_end = deadline_datetime + timedelta(hours=grace_hours)
        is_grace_period = False
        deadline_passed = True
    else:
        active_saturday = this_saturday
        is_grace_period = deadline_datetime <= now <= grace_end
        deadline_passed = now > grace_end

    return {
        "active_saturday": active_saturday,
        "deadline_datetime": deadline_datetime,
        "grace_end": grace_end,
        "is_grace_period": is_grace_period,
        "deadline_passed": deadline_passed,
        "config": deadline_config
    }

def clear_form_state():
    keys_to_clear = ["draft_report", "report_to_edit", "last_summary", "events_count"]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

def safe_db_query(query_builder, operation_name="Database query", max_retries=3):
    """
    Safely execute a Supabase query with retry logic and error handling.
    
    Args:
        query_builder: The Supabase query builder object
        operation_name: Description of the operation for error messages
        max_retries: Maximum number of retry attempts
    
    Returns:
        tuple: (success: bool, data: list|None, error: str|None)
    """
    import time
    
    for attempt in range(max_retries):
        try:
            response = query_builder.execute()
            return True, response.data, None
        except Exception as e:
            error_msg = str(e)
            
            # Check if it's a network/timeout error that might be retryable
            if any(keyword in error_msg.lower() for keyword in ['timeout', 'connection', 'network', 'httpx', 'read']):
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))  # Exponential backoff: 1s, 2s, 3s
                    continue
            
            # Return error on final attempt or non-retryable errors
            return False, None, f"{operation_name} failed: {error_msg}"
    
    return False, None, f"{operation_name} failed after {max_retries} attempts"
    for section_key in CORE_SECTIONS.keys():
        if f"{section_key}_success_count" in st.session_state:
            del st.session_state[f"{section_key}_success_count"]
        if f"{section_key}_challenge_count" in st.session_state:
            del st.session_state[f"{section_key}_challenge_count"]
    
    # Clear event-related session state
    events_to_clear = [key for key in st.session_state.keys() if key.startswith("event_name_") or key.startswith("event_date_")]
    for key in events_to_clear:
        del st.session_state[key]

# --- Email Functions ---
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

def get_logo_base64():
    """Convert logo image to base64 for embedding in HTML"""
    try:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Look for logo in various possible locations
        possible_paths = [
            os.path.join(script_dir, "assets", "und_housing_logo.jpg"),
            os.path.join(script_dir, "assets", "und_housing_logo.png"),
            os.path.join(script_dir, "und_housing_logo.jpg"),
            os.path.join(script_dir, "und_housing_logo.png"),
            "assets/und_housing_logo.jpg",
            "assets/und_housing_logo.png", 
            "und_housing_logo.jpg",
            "und_housing_logo.png"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, "rb") as img_file:
                    img_data = base64.b64encode(img_file.read()).decode()
                    ext = path.split('.')[-1].lower()
                    # Debug: Show which path was used (for testing)
                    print(f"DEBUG: Logo loaded from: {path}")
                    return f"data:image/{ext};base64,{img_data}"
        
        # If no logo found, return a placeholder SVG logo
        return create_text_logo_svg()
    except Exception as e:
        return create_text_logo_svg()

def create_text_logo_svg():
    """Create a professional SVG logo for UND Housing"""
    svg_content = """<svg width="240" height="90" xmlns="http://www.w3.org/2000/svg">
<defs>
<linearGradient id="bgGradient" x1="0%" y1="0%" x2="100%" y2="100%">
<stop offset="0%" style="stop-color:#009A44;stop-opacity:1" />
<stop offset="100%" style="stop-color:#007a36;stop-opacity:1" />
</linearGradient>
</defs>
<rect width="240" height="90" fill="url(#bgGradient)" rx="8"/>
<rect x="0" y="0" width="240" height="4" fill="#ffffff" opacity="0.8" rx="8"/>
<g transform="translate(15, 20)">
<polygon points="15,25 25,15 35,25 35,40 15,40" fill="white" opacity="0.9"/>
<rect x="20" y="30" width="5" height="10" fill="#009A44"/>
<rect x="27" y="25" width="4" height="4" fill="#009A44"/>
</g>
<text x="70" y="30" font-family="Arial, sans-serif" font-size="22" font-weight="900" text-anchor="start" fill="white">UND</text>
<text x="70" y="48" font-family="Arial, sans-serif" font-size="13" font-weight="bold" text-anchor="start" fill="white">HOUSING &amp; RESIDENCE LIFE</text>
<text x="70" y="65" font-family="Arial, sans-serif" font-size="9" font-weight="normal" text-anchor="start" fill="white" opacity="0.9">University of North Dakota</text>
<rect x="180" y="25" width="55" height="20" fill="#ffffff" rx="10" opacity="0.15"/>
<text x="207" y="37" font-family="Arial, sans-serif" font-size="8" font-weight="bold" text-anchor="middle" fill="white">LEADERSHIP</text>
</svg>"""
    svg_base64 = base64.b64encode(svg_content.encode()).decode()
    return f"data:image/svg+xml;base64,{svg_base64}"

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

def convert_markdown_to_html(text):
    """Convert markdown-formatted text to proper HTML with professional styling"""
    if not text:
        return ""
    
    # Split into lines for processing
    lines = text.split('\n')
    html_lines = []
    in_list = False
    in_table = False
    table_rows = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines but preserve spacing
        if not line:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            if in_table:
                html_lines.append(process_table(table_rows))
                table_rows = []
                in_table = False
            # Skip adding breaks to reduce spacing between sections
            i += 1
            continue
        
        # Handle subsection headers with ** first (### **text** or #### **text**) 
        if re.match(r'^#{3,4}\s+\*\*.*?\*\*', line):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            if in_table:
                html_lines.append(process_table(table_rows))
                table_rows = []
                in_table = False
                
            # Count hashes to determine if it's a main section or subsection
            hash_count = len(line) - len(line.lstrip('#'))
            match = re.match(r'^#{3,4}\s+\*\*(.*?)\*\*:?\s*(.*)', line)
            if match:
                title, rest = match.groups()
                if hash_count >= 4:
                    # #### headers are subsections (like "Nurturing") - use h4 with underlines
                    html_lines.append(f'<h4>{title}</h4>')
                else:
                    # ### headers are main sections - use h3
                    html_lines.append(f'<h3>{title}</h3>')
                if rest.strip():
                    html_lines.append(f'<p>{format_inline_text(rest)}</p>')
        
        # Handle regular markdown headers (##, ###, #### without asterisks)
        elif re.match(r'^#{2,4}\s+', line) and '**' not in line:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            if in_table:
                html_lines.append(process_table(table_rows))
                table_rows = []
                in_table = False
            
            # Count the number of hashes to determine header level
            hash_count = len(line) - len(line.lstrip('#'))
            header_text = line.lstrip('#').strip()
            
            if hash_count == 2:
                html_lines.append(f'<h2>{header_text}</h2>')
            elif hash_count == 3:
                html_lines.append(f'<h3>{header_text}</h3>')
            elif hash_count >= 4:
                html_lines.append(f'<h4>{header_text}</h4>')

        # Handle numbered sections (1. 2. 3. etc.)
        elif re.match(r'^\d+\.\s*\*\*.*?\*\*', line):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            if in_table:
                html_lines.append(process_table(table_rows))
                table_rows = []
                in_table = False
            
            match = re.match(r'^(\d+)\.\s*\*\*(.*?)\*\*:?\s*(.*)', line)
            if match:
                num, title, rest = match.groups()
                html_lines.append(f'<div class="section">')
                html_lines.append(f'<h2>{num}. {title}</h2>')
                if rest.strip():
                    html_lines.append(f'<p>{format_inline_text(rest)}</p>')
        

        
        # Handle bold headers (**Header**) - these should be subsection headers with underlines
        elif re.match(r'^\*\*.*?\*\*:?\s*', line):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            if in_table:
                html_lines.append(process_table(table_rows))
                table_rows = []
                in_table = False
            
            # Extract title by removing ** markers
            match = re.match(r'^\*\*(.*?)\*\*:?\s*(.*)', line)
            if match:
                title, rest = match.groups()
                # Use h4 for subsections like "Nurturing" to get underline styling
                html_lines.append(f'<h4>{title}</h4>')
                if rest.strip():
                    html_lines.append(f'<p>{format_inline_text(rest)}</p>')
            else:
                # Fallback: just remove ** markers
                clean_title = re.sub(r'^\*\*(.*?)\*\*:?\s*', r'\1', line)
                html_lines.append(f'<h4>{clean_title}</h4>')
        
        # Handle table rows
        elif '|' in line and line.count('|') >= 2:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            if not in_table:
                in_table = True
                table_rows = []
            table_rows.append(line)
        
        # Handle former bullet points as individual paragraphs with bold first word
        elif line.startswith('- '):
            if in_table:
                html_lines.append(process_table(table_rows))
                table_rows = []
                in_table = False
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            
            # Extract content and clean it thoroughly
            content = line[2:].strip()
            
            # Clean up any remaining asterisks before processing
            content = re.sub(r'^\*+\s*', '', content)  # Remove leading asterisks
            content = re.sub(r'\s*\*+$', '', content)  # Remove trailing asterisks
            
            # Process markdown formatting
            formatted_content = format_inline_text(content)
            
            # Make the first word bold if it's not already formatted
            words = formatted_content.split(' ', 1)
            if len(words) >= 2 and not words[0].startswith('<strong>') and not words[0].startswith('<b>'):
                formatted_content = f"<strong>{words[0]}</strong> {words[1]}"
            elif len(words) == 1 and not words[0].startswith('<strong>') and not words[0].startswith('<b>'):
                formatted_content = f"<strong>{words[0]}</strong>"
                
            html_lines.append(f'<p class="item-paragraph">{formatted_content}</p>')
        
        # Handle regular paragraphs
        else:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            if in_table:
                html_lines.append(process_table(table_rows))
                table_rows = []
                in_table = False
            
            # Clean up any leading asterisks that might appear in regular paragraphs
            clean_line = re.sub(r'^\*+\s*', '', line)
            html_lines.append(f'<p>{format_inline_text(clean_line)}</p>')
        
        i += 1
    
    # Close any remaining open tags
    if in_list:
        html_lines.append('</ul>')
    if in_table:
        html_lines.append(process_table(table_rows))
    
    return '\n'.join(html_lines)

def format_inline_text(text):
    """Format inline markdown elements like bold, etc."""
    # Convert **bold** to <strong>
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    # Convert *italic* to <em> (but be careful with leftover asterisks)
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', text)
    # Remove any remaining single asterisks that might be leftover
    text = re.sub(r'(?<!\*)\*(?!\*)', '', text)
    return text

def process_table(table_rows):
    """Convert markdown table rows to HTML table with professional styling"""
    if not table_rows:
        return ""
    
    html = ['<div class="table-container"><table class="professional-table">']
    header_processed = False
    
    for row in table_rows:
        # Clean up the row and split into cells
        cells = [cell.strip() for cell in row.split('|') if cell.strip()]
        
        # Skip empty rows or separator rows (those with dashes)
        if not cells or all(re.match(r'^[-\s]*$', cell) for cell in cells):
            continue
        
        # First valid row is the header
        if not header_processed:
            html.append('<thead><tr>')
            for cell in cells:
                html.append(f'<th>{format_inline_text(cell)}</th>')
            html.append('</tr></thead><tbody>')
            header_processed = True
        else:  # Data rows
            html.append('<tr>')
            for cell in cells:
                formatted_cell = format_inline_text(cell)
                # Add special styling for numeric values
                if re.match(r'^[\d.,]+%?$', cell.strip()):
                    html.append(f'<td class="numeric">{formatted_cell}</td>')
                else:
                    html.append(f'<td>{formatted_cell}</td>')
            html.append('</tr>')
    
    if header_processed:
        html.append('</tbody>')
    html.append('</table></div>')
    return '\n'.join(html)

def format_summary_as_html(summary_text, week_date, creator_name="Unknown", print_optimized=False):
    """Convert markdown summary to formatted HTML for better document export"""
    
    # Clean the summary text before processing
    summary_text = clean_summary_response(summary_text)
    
    # Get the logo as base64 encoded image
    logo_data = get_logo_base64()
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Weekly Summary - {week_date}</title>
        <style>
            body {{
                font-family: 'Segoe UI', 'Arial', 'Helvetica', sans-serif;
                line-height: 1.7;
                max-width: 8.5in;
                margin: 0 auto;
                padding: 0.75in;
                color: #2c3e50;
                background-color: #ffffff;
                font-size: 11pt;
            }}
            .header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                border-bottom: 4px solid #009A44;
                padding-bottom: 20px;
                margin-bottom: 30px;
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                padding: 20px;
                border-radius: 8px 8px 0 0;
            }}
            .header-content {{
                flex: 1;
            }}
            .logo-section {{
                flex: 0 0 auto;
                text-align: right;
            }}
            .logo {{
                max-height: 80px;
                max-width: 200px;
                height: auto;
            }}
            .header h1 {{
                color: #009A44;
                margin: 0 0 10px 0;
                font-size: 28px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .header .subtitle {{
                color: #333;
                font-size: 16px;
                margin: 5px 0;
                font-weight: 500;
            }}
            .header .report-type {{
                color: #009A44;
                font-size: 18px;
                font-weight: 600;
                margin: 10px 0 5px 0;
            }}
            h2 {{
                color: #009A44;
                border-left: 6px solid #009A44;
                padding: 12px 16px 12px 20px;
                margin: 20px 0 15px 0;
                font-size: 18pt;
                font-weight: 700;
                background: linear-gradient(135deg, #f8f9fa 0%, #e8f5e8 100%);
                border-radius: 0 8px 8px 0;
                box-shadow: 0 2px 6px rgba(0,154,68,0.15);
                page-break-after: avoid;
            }}
            h3 {{
                color: #006633;
                font-size: 14pt;
                margin: 15px 0 10px 0;
                font-weight: 600;
                border-bottom: 3px solid #009A44;
                padding-bottom: 6px;
                padding-left: 12px;
                background-color: #f8f9fa;
                padding-top: 6px;
                border-radius: 4px 4px 0 0;
            }}
            h4 {{
                color: #2c3e50;
                font-size: 12pt;
                margin: 12px 0 8px 0;
                font-weight: 600;
                padding-left: 8px;
                border-left: 3px solid #AEAEAE;
            }}
            ul, ol {{
                padding-left: 35px;
                margin: 15px 0 20px 0;
                background-color: #fdfdfd;
                border-left: 3px solid #e8f5e8;
                padding-top: 15px;
                padding-bottom: 15px;
                padding-right: 20px;
                border-radius: 0 8px 8px 0;
                box-shadow: 0 1px 3px rgba(0,154,68,0.1);
            }}
            .item-paragraph {{
                margin: 4px 0 6px 15px;
                line-height: 1.5;
                color: #2c3e50;
                text-indent: 0;
            }}
            .item-paragraph strong {{
                color: #009A44;
                font-weight: bold;
            }}
            ul {{
                list-style-type: none;
            }}
            ul li {{
                position: relative;
                margin-bottom: 12px;
                line-height: 1.6;
                padding-left: 25px;
            }}
            ul li::before {{
                content: "●";
                color: #009A44;
                font-weight: bold;
                font-size: 16px;
                position: absolute;
                left: 8px;
                top: 0px;
                line-height: 1.6;
            }}
            ol li {{
                margin-bottom: 12px;
                line-height: 1.6;
                padding-left: 5px;
            }}
            ol li::marker {{
                color: #009A44;
                font-weight: bold;
                font-size: 13px;
            }}
            p {{
                margin: 12px 0;
                text-align: justify;
                hyphens: auto;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                background-color: #fff;
                border: 2px solid #009A44;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            th {{
                background: linear-gradient(135deg, #009A44 0%, #006633 100%);
                color: white;
                padding: 15px 12px;
                text-align: left;
                font-weight: 600;
                text-transform: uppercase;
                font-size: 12px;
                letter-spacing: 0.5px;
            }}
            td {{
                padding: 12px;
                border-bottom: 1px solid #e9ecef;
                vertical-align: top;
            }}
            tr:nth-child(even) {{
                background-color: #f8f9fa;
            }}
            tr:hover {{
                background-color: #e8f5e8;
            }}
            .section {{
                margin-bottom: 35px;
                page-break-inside: avoid;
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                overflow: hidden;
            }}
            .section:last-child {{
                margin-bottom: 20px;
            }}
            .content-block {{
                padding: 20px;
                margin: 15px 0;
                background-color: #fafafa;
                border-radius: 6px;
                border: 1px solid #e9ecef;
            }}
            .footer {{
                margin-top: 50px;
                padding-top: 20px;
                border-top: 2px solid #AEAEAE;
                text-align: center;
                color: #666;
                font-size: 12px;
                background-color: #f8f9fa;
                padding: 20px;
                border-radius: 5px;
            }}
            .footer .und-info {{
                color: #009A44;
                font-weight: 600;
                margin-bottom: 5px;
            }}
            strong {{
                color: #009A44;
                font-weight: 600;
            }}
            em {{
                color: #006633;
                font-style: italic;
            }}
            .well-being-score {{
                background: linear-gradient(135deg, #e8f5e8 0%, #f0f8f0 100%);
                padding: 20px;
                border-left: 5px solid #009A44;
                margin: 20px 0;
                border-radius: 0 8px 8px 0;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }}
            .executive-summary {{
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                padding: 25px;
                border: 2px solid #009A44;
                border-radius: 10px;
                margin: 25px 0;
                font-size: 12pt;
                line-height: 1.8;
                box-shadow: 0 4px 8px rgba(0,154,68,0.1);
            }}
            .metric-highlight {{
                background-color: #e8f5e8;
                padding: 8px 12px;
                border-radius: 4px;
                color: #006633;
                font-weight: 600;
                display: inline-block;
                margin: 4px 8px 4px 0;
            }}
            .page-break {{
                page-break-before: always;
                margin-top: 40px;
                padding-top: 20px;
                border-top: 2px solid #009A44;
            }}
            .section {{
                margin: 30px 0;
                padding: 20px;
                background-color: #fafafa;
                border-radius: 8px;
                border-left: 4px solid #009A44;
            }}
            @media print {{
                .page-break {{
                    page-break-before: always;
                }}
                body {{
                    font-size: 12pt;
                    line-height: 1.4;
                }}
                .header-section {{
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 80px;
                    background: white;
                    border-bottom: 2px solid #009A44;
                    z-index: 1000;
                }}
            }}
            .table-container {{
                margin: 20px 0;
                overflow-x: auto;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border-radius: 8px;
            }}
            .professional-table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 11pt;
                background-color: white;
                border-radius: 8px;
                overflow: hidden;
            }}
            .professional-table thead th {{
                background: linear-gradient(135deg, #009A44 0%, #007a36 100%);
                color: white;
                font-weight: 600;
                padding: 12px 15px;
                text-align: left;
                border: none;
                font-size: 10pt;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .professional-table tbody td {{
                padding: 10px 15px;
                border-bottom: 1px solid #e0e0e0;
                color: #333;
                font-size: 10pt;
            }}
            .professional-table tbody tr:nth-child(even) {{
                background-color: #f8f9fa;
            }}
            .professional-table tbody tr:hover {{
                background-color: #e8f5e8;
            }}
            .professional-table td.numeric {{
                text-align: right;
                font-weight: 600;
                color: #009A44;
            }}
            .accent-green {{
                color: #009A44;
            }}
            .accent-gray {{
                color: #AEAEAE;
            }}
            .highlight-box {{
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-left: 4px solid #009A44;
                padding: 15px;
                margin: 15px 0;
                border-radius: 0 5px 5px 0;
            }}
            @media print {{
                body {{ 
                    margin: 0.5in; 
                    -webkit-print-color-adjust: exact;
                    print-color-adjust: exact;
                }}
                .header {{ 
                    page-break-after: avoid; 
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%) !important;
                }}
                .section {{ page-break-inside: avoid; }}
                .logo {{ max-height: 60px; }}
                h2 {{
                    background-color: #f8f9fa !important;
                    border-left: 5px solid #009A44 !important;
                }}
                th {{
                    background: #009A44 !important;
                    color: white !important;
                }}
                .footer {{
                    background-color: #f8f9fa !important;
                }}
            }}
            @page {{
                margin: 0.75in;
                size: letter;
            }}
            .print-instructions {{
                background-color: #fff3cd;
                border: 1px solid #ffeaa7;
                color: #856404;
                padding: 15px;
                margin: 20px 0;
                border-radius: 5px;
                text-align: center;
                font-weight: 600;
            }}
            .print-tip {{
                background-color: #d1ecf1;
                border: 1px solid #bee5eb;
                color: #0c5460;
                padding: 10px;
                margin: 10px 0;
                border-radius: 5px;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1>UND Housing & Residence Life</h1>
                <div class="report-type">Weekly Leadership Report Summary</div>
                <div class="subtitle">Week Ending: {week_date}</div>
                <div class="subtitle">Generated by: {creator_name}</div>
                <div class="subtitle">Report Date: {datetime.now().strftime('%B %d, %Y')}</div>
            </div>
            <div class="logo-section">
                <img src="{logo_data}" alt="UND Housing & Residence Life Logo" class="logo" 
                     style="max-height: 80px; max-width: 200px; height: auto; border-radius: 5px; 
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            </div>
        </div>
    """
    
    # Add print instructions if this is print-optimized
    if print_optimized:
        html_content += """
        <div class="print-instructions">
            🖨️ <strong>PRINT TO PDF INSTRUCTIONS</strong><br>
            Press <kbd>Ctrl+P</kbd> (or <kbd>Cmd+P</kbd> on Mac) → Choose "Save as PDF" → Click "More settings" → Check "Background graphics" → Save
        </div>
        <div class="print-tip">
            💡 <strong>Tip:</strong> This file is optimized for printing to PDF. All UND colors and formatting will be preserved when you print to PDF from your browser.
        </div>
        """
    
    # Convert markdown summary to professional HTML
    formatted_text = convert_markdown_to_html(summary_text)
    
    html_content += formatted_text
    
    html_content += f"""
        <div class="footer">
            <p>Generated by UND Housing & Residence Life Weekly Reporting Tool</p>
            <p>University of North Dakota Housing & Residence Life Department</p>
        </div>
        </div>
    </body>
    </html>
    """
    
    return html_content

def create_formatted_document_download(summary_text, week_date, creator_name="Unknown", file_format="html"):
    """Create a formatted document for download"""
    if file_format.lower() == "html":
        html_content = format_summary_as_html(summary_text, week_date, creator_name)
        return html_content.encode('utf-8'), f"weekly_summary_{week_date}.html", "text/html"

    else:
        # Fallback to plain text with better formatting
        formatted_text = f"""
UND HOUSING & RESIDENCE LIFE
WEEKLY LEADERSHIP REPORT SUMMARY

Week Ending: {week_date}
Generated by: {creator_name}
Report Date: {datetime.now().strftime('%B %d, %Y')}

{'='*60}

{summary_text}

{'='*60}
Generated by UND Housing & Residence Life Weekly Reporting Tool
University of North Dakota Housing & Residence Life Department
        """.strip()
        
        return formatted_text.encode('utf-8'), f"weekly_summary_{week_date}.txt", "text/plain"

def send_email(to_email, subject, body, from_email=None, smtp_server=None, smtp_port=587, email_password=None):
    """Send an email with the UND LEADS section"""
    try:
        # Use environment variables or Streamlit secrets for email configuration
        if not from_email:
            try:
                from_email = st.secrets["EMAIL_ADDRESS"]
            except KeyError:
                st.error("EMAIL_ADDRESS not found in secrets configuration.")
                return False
            except Exception as e:
                st.error(f"Error accessing EMAIL_ADDRESS from secrets: {e}")
                return False
                
        if not email_password:
            try:
                email_password = st.secrets["EMAIL_PASSWORD"]
            except KeyError:
                st.error("EMAIL_PASSWORD not found in secrets configuration.")
                return False
            except Exception as e:
                st.error(f"Error accessing EMAIL_PASSWORD from secrets: {e}")
                return False
                
        if not smtp_server:
            try:
                smtp_server = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
            except Exception as e:
                st.error(f"Error accessing SMTP_SERVER from secrets: {e}")
                smtp_server = "smtp.gmail.com"  # Default fallback
        
        # Debug information
        st.write(f"🔧 Debug - Using SMTP server: {smtp_server}")
        st.write(f"🔧 Debug - From email: {from_email}")
        
        if not from_email or not email_password:
            st.error("Email configuration incomplete. Missing email address or password.")
            return False
        
        # Create message using email.message
        msg = email.message.EmailMessage()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.set_content(body)
        
        # Create SMTP session
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Enable TLS security
        server.login(from_email, email_password)
        server.send_message(msg)
        server.quit()
        
        return True
        
    except Exception as e:
        st.error(f"Failed to send email: {e}")
        return False

# --- Roompact API Functions ---
def get_roompact_config():
    """Get Roompact API configuration from environment variables or secrets"""
    try:
        # Try environment variables first (for deployment), then secrets (for local)
        api_token = os.getenv("ROOMPACT_API_TOKEN") or st.secrets.get("roompact_api_token")
        base_url = "https://api.roompact.com/v1"
        
        if not api_token:
            return None, "❌ Missing Roompact API token. Please add 'roompact_api_token' to your secrets or environment variables."
        
        return {"api_token": api_token, "base_url": base_url}, None
        
    except Exception as e:
        return None, f"❌ Error accessing Roompact API configuration: {e}"

def make_roompact_request(endpoint, params=None):
    """Make authenticated request to Roompact API"""
    config, error = get_roompact_config()
    if error:
        return None, error
    
    try:
        headers = {
            "Authorization": f"Bearer {config['api_token']}",
            "Content-Type": "application/json"
        }
        
        url = f"{config['base_url']}/{endpoint.lstrip('/')}"
        
        response = requests.get(url, headers=headers, params=params or {})
        response.raise_for_status()
        
        return response.json(), None
        
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code == 401:
                return None, "❌ Unauthorized: Invalid API token or token has been deactivated"
            elif e.response.status_code == 403:
                return None, "❌ Forbidden: Insufficient permissions for this resource"
            else:
                return None, f"❌ API Error {e.response.status_code}: {e.response.text}"
        return None, f"❌ Connection error: {str(e)}"
    except Exception as e:
        return None, f"❌ Unexpected error: {str(e)}"

def fetch_roompact_forms(cursor=None, max_pages=600, target_start_date=None, progress_callback=None):
    """Fetch forms data from Roompact API with pagination and optional date-based stopping"""
    forms = []
    page_count = 0
    next_cursor = cursor
    reached_target_date = False
    
    try:
        # Convert target_start_date to datetime for comparison if provided
        target_datetime = None
        if target_start_date:
            target_datetime = datetime.combine(target_start_date, datetime.min.time())
        
        while page_count < max_pages and not reached_target_date:
            params = {}
            if next_cursor:
                params['cursor'] = next_cursor
                
            data, error = make_roompact_request("forms", params)
            if error:
                return None, error
            
            # Add forms from this page
            page_forms = data.get('data', [])
            
            # If we have a target date, check if we've reached forms older than our target
            if target_datetime and page_forms:
                for form in page_forms:
                    current_revision = form.get('current_revision', {})
                    date_str = current_revision.get('date', '')
                    
                    if date_str:
                        try:
                            form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            form_datetime = form_datetime.replace(tzinfo=None)
                            
                            # If this form is older than our target, we've gone far enough
                            if form_datetime < target_datetime:
                                reached_target_date = True
                                break
                        except:
                            pass  # Skip forms with invalid dates
            
            forms.extend(page_forms)
            
            # Update progress if callback provided
            if progress_callback:
                oldest_date = "Unknown"
                if page_forms:
                    dates = []
                    for form in page_forms:
                        current_revision = form.get('current_revision', {})
                        date_str = current_revision.get('date', '')
                        if date_str:
                            try:
                                form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                dates.append(form_datetime)
                            except:
                                pass
                    if dates:
                        oldest_date = min(dates).strftime('%Y-%m-%d')
                
                progress_callback(page_count + 1, len(forms), oldest_date, reached_target_date)
            
            # Check for pagination
            links = data.get('links', [])
            next_cursor = None
            
            for link in links:
                if link.get('rel') == 'next':
                    # Extract cursor from URI
                    next_uri = link.get('uri', '')
                    if 'cursor=' in next_uri:
                        next_cursor = next_uri.split('cursor=')[1].split('&')[0]
                    break
            
            page_count += 1
            
            # If no next page, break
            if not next_cursor:
                break
                
        return forms, None
        
    except Exception as e:
        return None, f"Error fetching forms: {str(e)}"

def discover_form_types(max_pages=600, target_start_date=None, progress_callback=None):
    """Fetch forms and discover all available form types"""
    try:
        def progress_update(page_num, total_forms, oldest_date, reached_target):
            status_text = f"📄 Page {page_num}: {total_forms} forms found"
            if oldest_date != "Unknown":
                status_text += f" | Oldest: {oldest_date}"
            if reached_target:
                status_text += " | ✅ Target date reached"
            return status_text
        
        progress_placeholder = st.empty()
        
        def show_progress(page_num, total_forms, oldest_date, reached_target):
            progress_placeholder.info(progress_update(page_num, total_forms, oldest_date, reached_target))
        
        with st.spinner("Discovering available form types..."):
            forms, error = fetch_roompact_forms(
                max_pages=max_pages, 
                target_start_date=target_start_date,
                progress_callback=show_progress
            )
            
            if error:
                return None, error
            
            if not forms:
                return [], "No forms found"
            
            # Extract unique form template names with counts and date ranges
            form_type_info = {}
            for form in forms:
                template_name = form.get('form_template_name', 'Unknown Form')
                if template_name and template_name != 'Unknown Form':
                    if template_name not in form_type_info:
                        form_type_info[template_name] = {
                            'count': 0,
                            'dates': []
                        }
                    
                    form_type_info[template_name]['count'] += 1
                    
                    # Get submission date for date range info
                    current_revision = form.get('current_revision', {})
                    date_str = current_revision.get('date', '')
                    if date_str:
                        try:
                            form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            form_type_info[template_name]['dates'].append(form_datetime)
                        except:
                            pass
            
            # Create form type options with metadata
            form_type_options = []
            for template_name, info in form_type_info.items():
                count = info['count']
                dates = info['dates']
                
                if dates:
                    dates.sort()
                    oldest = dates[0].strftime('%Y-%m-%d')
                    newest = dates[-1].strftime('%Y-%m-%d')
                    date_info = f"({oldest} to {newest})"
                else:
                    date_info = "(dates unknown)"
                
                display_name = f"{template_name} - {count} submissions {date_info}"
                form_type_options.append({
                    'display_name': display_name,
                    'template_name': template_name,
                    'count': count
                })
            
            # Sort by count (most common first)
            form_type_options.sort(key=lambda x: x['count'], reverse=True)
            
            return form_type_options, None
            
    except Exception as e:
        return None, f"Error discovering form types: {str(e)}"

def filter_forms_by_type_and_date(forms, selected_form_types, start_date, end_date):
    """Filter forms by date range and selected form types"""
    if not forms:
        return [], "No forms to filter"
    
    filtered_forms = []
    
    try:
        # Convert dates to datetime objects for comparison
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())
        
        for form in forms:
            # Get the form submission date
            current_revision = form.get('current_revision', {})
            date_str = current_revision.get('date', '')
            
            if not date_str:
                continue  # Skip forms without dates
            
            try:
                # Parse the ISO format date from Roompact API
                form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                # Convert to local time for comparison
                form_datetime = form_datetime.replace(tzinfo=None)
                
                # Check if form is within date range
                if not (start_datetime <= form_datetime <= end_datetime):
                    continue
                
            except (ValueError, TypeError):
                continue  # Skip forms with invalid dates
            
            # Check if form matches selected types
            form_template_name = form.get('form_template_name', '')
            if form_template_name in selected_form_types:
                filtered_forms.append(form)
        
        return filtered_forms, None
        
    except Exception as e:
        return [], f"Error filtering forms: {str(e)}"

def analyze_general_forms_with_ai(selected_forms, form_types, start_date, end_date):
    """Generate AI analysis for general form submissions"""
    if not selected_forms:
        return None
    
    try:
        # Prepare forms data for AI analysis
        forms_text = f"ANALYSIS PARAMETERS:\n"
        forms_text += f"Form Types: {', '.join(form_types)}\n"
        forms_text += f"Date Range: {start_date} to {end_date}\n"
        forms_text += f"Total Forms: {len(selected_forms)}\n\n"
        forms_text += "FORM SUBMISSIONS DATA:\n" + "="*50 + "\n"
        
        for i, form in enumerate(selected_forms, 1):
            current_revision = form.get('current_revision', {})
            author = current_revision.get('author', 'Unknown')
            date_str = current_revision.get('date', '')
            template_name = form.get('form_template_name', 'Unknown Form')
            
            # Format date for readability
            form_date = "Unknown Date"
            if date_str:
                try:
                    form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    form_date = form_datetime.strftime('%Y-%m-%d %H:%M')
                except:
                    form_date = date_str
            
            forms_text += f"FORM #{i}: {template_name}\n"
            forms_text += f"Submitted by: {author}\n"
            forms_text += f"Date: {form_date}\n"
            forms_text += f"Form ID: {form.get('id', 'Unknown')}\n\n"
            
            # Include form responses
            responses = current_revision.get('responses', [])
            for response in responses:
                field_label = response.get('field_label', 'Unknown Field')
                field_response = response.get('response', '')
                
                if field_response and str(field_response).strip():
                    forms_text += f"**{field_label}:** {field_response}\n"
            
            forms_text += "\n" + "="*50 + "\n"
        
        # Create AI prompt for summarization
        prompt = f"""
You are analyzing form submissions from residence life staff for supervisory review. Please create a comprehensive summary that helps supervisors understand key themes, concerns, and insights from the submitted forms.

FORM DATA:
{forms_text}

Please provide a summary that includes:

1. **Executive Overview**: Brief summary of the number and types of forms analyzed
2. **Key Themes**: Major patterns, recurring topics, or common themes across submissions  
3. **Notable Incidents**: Any significant events, concerns, or issues reported
4. **Staff Performance**: Observations about staff responsiveness, thoroughness, and professionalism
5. **Operational Insights**: Patterns in facility issues, resident needs, or procedural gaps
6. **Recommendations**: Actionable suggestions for improvements or follow-up actions
7. **Data Summary**: Key statistics and trends from the submissions

Provide specific examples and data-driven insights while maintaining appropriate confidentiality. Focus on actionable recommendations for residence life leadership.
"""

        # Use Gemini 2.5 Flash for better quota efficiency  
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        
        with st.spinner(f"AI is analyzing {len(selected_forms)} forms..."):
            result = model.generate_content(prompt)
            return result.text
            
    except Exception as e:
        return f"Error generating form analysis: {str(e)}"
    
    try:
        # Convert target_start_date to datetime for comparison if provided
        target_datetime = None
        if target_start_date:
            target_datetime = datetime.combine(target_start_date, datetime.min.time())
        
        while page_count < max_pages and not reached_target_date:
            params = {}
            if next_cursor:
                params['cursor'] = next_cursor
                
            data, error = make_roompact_request("forms", params)
            if error:
                return None, error
            
            # Add forms from this page
            page_forms = data.get('data', [])
            
            # If we have a target date, check if we've reached forms older than our target
            if target_datetime and page_forms:
                for form in page_forms:
                    current_revision = form.get('current_revision', {})
                    date_str = current_revision.get('date', '')
                    
                    if date_str:
                        try:
                            form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            form_datetime = form_datetime.replace(tzinfo=None)
                            
                            # If this form is older than our target, we've gone far enough
                            if form_datetime < target_datetime:
                                reached_target_date = True
                                break
                        except:
                            pass  # Skip forms with invalid dates
            
            forms.extend(page_forms)
            
            # Update progress if callback provided
            if progress_callback:
                oldest_date = "Unknown"
                if page_forms:
                    dates = []
                    for form in page_forms:
                        current_revision = form.get('current_revision', {})
                        date_str = current_revision.get('date', '')
                        if date_str:
                            try:
                                form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                dates.append(form_datetime)
                            except:
                                pass
                    if dates:
                        oldest_date = min(dates).strftime('%Y-%m-%d')
                
                progress_callback(page_count + 1, len(forms), oldest_date, reached_target_date)
            
            # Check for pagination
            links = data.get('links', [])
            next_cursor = None
            
            for link in links:
                if link.get('rel') == 'next':
                    # Extract cursor from URI
                    next_uri = link.get('uri', '')
                    if 'cursor=' in next_uri:
                        next_cursor = next_uri.split('cursor=')[1].split('&')[0]
                    break
            
            page_count += 1
            
            # If no next page, break
            if not next_cursor:
                break
                
        return forms, None
        
    except Exception as e:
        return None, f"Error fetching forms: {str(e)}"

def discover_form_types(max_pages=600, target_start_date=None, progress_callback=None):
    """Fetch forms and discover all available form types"""
    try:
        def progress_update(page_num, total_forms, oldest_date, reached_target):
            status_text = f"📄 Page {page_num}: {total_forms} forms found"
            if oldest_date != "Unknown":
                status_text += f" | Oldest: {oldest_date}"
            if reached_target:
                status_text += " | ✅ Target date reached"
            return status_text
        
        progress_placeholder = st.empty()
        
        def show_progress(page_num, total_forms, oldest_date, reached_target):
            progress_placeholder.info(progress_update(page_num, total_forms, oldest_date, reached_target))
        
        with st.spinner("Discovering available form types..."):
            forms, error = fetch_roompact_forms(
                max_pages=max_pages, 
                target_start_date=target_start_date,
                progress_callback=show_progress
            )
            
            if error:
                return None, error
            
            if not forms:
                return [], "No forms found"
            
            # Extract unique form template names with counts and date ranges
            form_type_info = {}
            for form in forms:
                template_name = form.get('form_template_name', 'Unknown Form')
                if template_name and template_name != 'Unknown Form':
                    if template_name not in form_type_info:
                        form_type_info[template_name] = {
                            'count': 0,
                            'dates': []
                        }
                    
                    form_type_info[template_name]['count'] += 1
                    
                    # Get submission date for date range info
                    current_revision = form.get('current_revision', {})
                    date_str = current_revision.get('date', '')
                    if date_str:
                        try:
                            form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            form_type_info[template_name]['dates'].append(form_datetime)
                        except:
                            pass
            
            # Create form type options with metadata
            form_type_options = []
            for template_name, info in form_type_info.items():
                count = info['count']
                dates = info['dates']
                
                if dates:
                    dates.sort()
                    oldest = dates[0].strftime('%Y-%m-%d')
                    newest = dates[-1].strftime('%Y-%m-%d')
                    date_info = f"({oldest} to {newest})"
                else:
                    date_info = "(dates unknown)"
                
                display_name = f"{template_name} - {count} submissions {date_info}"
                form_type_options.append({
                    'display_name': display_name,
                    'template_name': template_name,
                    'count': count
                })
            
            # Sort by count (most common first) then alphabetically
            form_type_options.sort(key=lambda x: (-x['count'], x['template_name']))
            
            return form_type_options, None
            
    except Exception as e:
        return None, f"Error discovering form types: {str(e)}"

def summarize_form_submissions(selected_forms, max_forms=10):
    """Use AI to summarize selected form submissions"""
    if not selected_forms:
        return "No forms selected for summarization."
    
    try:
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
        # Create AI prompt for summarization
        prompt = f"""
Format the response in clear markdown with headers and bullet points. Focus on actionable insights that help supervisors make informed decisions about their teams and operations.
"""

        # Use the same AI configuration as the rest of the app
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        
        with st.spinner("AI is analyzing form submissions..."):
            result = model.generate_content(prompt)
            if not result or not getattr(result, 'text', None) or not result.text.strip():
                st.info("Prompt sent to AI:")
                st.code(prompt)
                st.info("Input data summary:")
                st.code(forms_text)
                return "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."
            return result.text
            
    except Exception as e:
        return f"Error generating AI summary: {str(e)}"

def filter_forms_by_date_and_type(forms, start_date, end_date, selected_form_types):
    """Filter forms by date range and selected form types"""
    if not forms:
        return [], "No forms to filter"
    
    filtered_forms = []
    
    try:
        # Convert dates to datetime objects for comparison
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())
        
        for form in forms:
            # Get the form submission date
            current_revision = form.get('current_revision', {})
            date_str = current_revision.get('date', '')
            
            if not date_str:
                continue  # Skip forms without dates
            
            try:
                # Parse the ISO format date from Roompact API
                form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                # Convert to local time for comparison
                form_datetime = form_datetime.replace(tzinfo=None)
                
                # Check if form is within date range
                if not (start_datetime <= form_datetime <= end_datetime):
                    continue
                
            except (ValueError, TypeError):
                continue  # Skip forms with invalid dates
            
            # Filter by selected form types
            form_template_name = form.get('form_template_name', '')
            
            # If no specific form types selected, include all forms
            if not selected_form_types or "All Form Types" in selected_form_types:
                filtered_forms.append(form)
            elif form_template_name in selected_form_types:
                filtered_forms.append(form)
        
        return filtered_forms, None
        
    except Exception as e:
        return [], f"Error filtering forms: {str(e)}"

def create_weekly_duty_report_summary(selected_forms, start_date, end_date):
    """Create a weekly quantitative duty report with hall breakdowns for admin summaries"""
    if not selected_forms:
        return "No duty reports selected for analysis."
    
    try:
        from collections import defaultdict
        halls_data = defaultdict(lambda: {
            'total_reports': 0,
            'incidents': [],
            'lockouts': 0,
            'maintenance': 0,
            'policy_violations': 0,
            'safety_concerns': 0,
            'staff_responses': 0
        })
        weekly_data = defaultdict(lambda: {
            'total_reports': 0,
            'incident_count': 0,
            'halls_active': set()
        })

        # Process each form to extract quantitative data
        for form in selected_forms:
            current_revision = form.get('current_revision', {})
            author = current_revision.get('author', 'Unknown')
            date_str = current_revision.get('date', '')

            # Extract hall/building info from responses
            hall_name = "Unknown Hall"
            responses = current_revision.get('responses', [])

            for response in responses:
                field_label = response.get('field_label', '').lower()
                field_response = str(response.get('response', '')).strip()
                # Try to identify hall/building
                if any(word in field_label for word in ['building', 'hall', 'location', 'area']):
                    if field_response and field_response != 'None':
                        hall_name = field_response
                        break

            # Extract week from date
            if date_str:
                try:
                    form_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    week_key = form_date.strftime('Week of %Y-%m-%d')
                    weekly_data[week_key]['total_reports'] += 1
                    weekly_data[week_key]['halls_active'].add(hall_name)
                except:
                    week_key = "Unknown Week"
            else:
                week_key = "Unknown Week"

            # Count incidents by type in this report
            report_text = ""
            for response in responses:
                field_response = str(response.get('response', '')).strip().lower()
                report_text += field_response + " "

            # Increment hall counters
            halls_data[hall_name]['total_reports'] += 1

            # Count specific incident types
            if any(word in report_text for word in ['lockout', 'locked out', 'key']):
                halls_data[hall_name]['lockouts'] += 1

            if any(word in report_text for word in ['maintenance', 'repair', 'broken', 'leak', 'ac', 'heat']):
                halls_data[hall_name]['maintenance'] += 1

            if any(word in report_text for word in ['alcohol', 'intoxicated', 'violation', 'policy', 'noise']):
                halls_data[hall_name]['policy_violations'] += 1
                weekly_data[week_key]['incident_count'] += 1

            if any(word in report_text for word in ['safety', 'emergency', 'security', 'fire', 'medical']):
                halls_data[hall_name]['safety_concerns'] += 1
                weekly_data[week_key]['incident_count'] += 1

            if any(word in report_text for word in ['responded', 'contacted', 'called', 'notified']):
                halls_data[hall_name]['staff_responses'] += 1

        # Prepare comprehensive report data for AI analysis
        reports_text = f"\n=== WEEKLY DUTY REPORTS ANALYSIS ===\n"
        reports_text += f"Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n"
        reports_text += f"Total Reports: {len(selected_forms)}\n\n"

        # Add quantitative breakdown by hall (formatted for table creation)
        reports_text += "=== HALL-BY-HALL INCIDENT BREAKDOWN (FOR TABLE) ===\n"

        # Calculate totals for summary
        total_lockouts = sum(data['lockouts'] for data in halls_data.values())
        total_maintenance = sum(data['maintenance'] for data in halls_data.values())
        total_violations = sum(data['policy_violations'] for data in halls_data.values())
        total_safety = sum(data['safety_concerns'] for data in halls_data.values())
        total_reports = sum(data['total_reports'] for data in halls_data.values())
        total_responses = sum(data['staff_responses'] for data in halls_data.values())

        reports_text += "DATA FOR QUANTITATIVE METRICS TABLE:\n"
        reports_text += f"TOTALS: Reports={total_reports}, Lockouts={total_lockouts}, Maintenance={total_maintenance}, Violations={total_violations}, Safety={total_safety}, Responses={total_responses}\n\n"

        reports_text += "HALL-BY-HALL DATA:\n"
        for hall, data in sorted(halls_data.items()):
            reports_text += f"{hall}: Reports={data['total_reports']}, Lockouts={data['lockouts']}, Maintenance={data['maintenance']}, Violations={data['policy_violations']}, Safety={data['safety_concerns']}, Responses={data['staff_responses']}\n"

        reports_text += "\nDETAILED BREAKDOWN BY HALL:\n"
        for hall, data in sorted(halls_data.items()):
            total_incidents = data['lockouts'] + data['maintenance'] + data['policy_violations'] + data['safety_concerns']
            reports_text += f"**{hall}** ({data['total_reports']} reports, {total_incidents} total incidents):\n"
            reports_text += f"  • Lockouts: {data['lockouts']}\n"
            reports_text += f"  • Maintenance: {data['maintenance']}\n"  
            reports_text += f"  • Policy Violations: {data['policy_violations']}\n"
            reports_text += f"  • Safety Concerns: {data['safety_concerns']}\n"
            reports_text += f"  • Staff Responses: {data['staff_responses']}\n\n"

        reports_text += "\n=== WEEKLY ACTIVITY SUMMARY ===\n"
        for week, data in sorted(weekly_data.items()):
            reports_text += f"\n**{week}:**\n"
            reports_text += f"- Total Reports: {data['total_reports']}\n"
            reports_text += f"- Incident Reports: {data['incident_count']}\n"
            reports_text += f"- Active Halls: {len(data['halls_active'])}\n"
            reports_text += f"- Halls: {', '.join(sorted(data['halls_active']))}\n"

        reports_text += f"\n=== DETAILED REPORTS ===\n"

        for i, form in enumerate(selected_forms, 1):
            current_revision = form.get('current_revision', {})
            form_name = form.get('form_template_name', 'Unknown Form')
            author = current_revision.get('author', 'Unknown')
            date = current_revision.get('date', 'Unknown date')

            reports_text += f"\n--- REPORT {i}: {form_name} ---\n"
            reports_text += f"Staff: {author}\n"
            reports_text += f"Date: {date}\n\n"

            # Process responses
            responses = current_revision.get('responses', [])
            for response in responses:
                field_label = response.get('field_label', 'Unknown Field')
                field_response = response.get('response', '')

                if field_response and str(field_response).strip():
                    reports_text += f"**{field_label}:** {field_response}\n"

            reports_text += "\n" + "="*50 + "\n"

        # Updated AI prompt for improved, actionable, bullet-pointed summary
        prompt = f"""
You are analyzing residence life duty reports for a weekly administrative summary. Your goal is to produce a concise, actionable, and easy-to-read report for leadership. Please:

- Summarize the week's overall activity and key trends in 3-5 bullet points.
- Highlight the most important incidents, challenges, or successes that require attention. Use bullet points for each item.
- Provide a quantitative breakdown (number of reports, incidents by type, hall-by-hall summary) in a clear, readable format.
- For each hall, create a dedicated section with the hall name as the header. The individual halls are: Swanson, West, McVey, Brannon, Noren, Selke, Johnstone, Smith, University Place. Under each hall, list the key items, incidents, challenges, successes, and any notable staff actions for that hall as bullet points. Do not group halls together; each hall should have its own section, even if some halls have no incidents or items to report.
- List specific action items or recommendations for staff or administration. Make these actionable and direct.
- Note any staff performance highlights or concerns.
- If relevant, mention any policy, facility, or safety issues that need follow-up.

Do NOT include a separate "Recurring Issues" section. Instead, ensure hall-specific issues are included under each hall's section.

Format your response in markdown with clear headers and bullet points. Focus on actionable insights and brevity. Do not include unnecessary narrative or filler text.

DUTY REPORTS DATA:
{reports_text}

Generate the weekly duty analysis summary below:
"""

        import google.generativeai as genai
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        import streamlit as st
        with st.spinner(f"AI is generating weekly duty report from {len(selected_forms)} reports..."):
            result = model.generate_content(prompt)
            if not result or not getattr(result, 'text', None) or not result.text.strip():
                st.info("Prompt sent to AI:")
                st.code(prompt)
                st.info("Input data summary:")
                st.code(reports_text)
                return "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."
            return result.text
    except Exception as e:
        return f"Error generating weekly duty report summary: {str(e)}"

def store_duty_report_data(selected_forms, start_date, end_date, generated_by_user_id=None):
    """Store individual duty report incidents in Supabase for historical analysis and graphing"""
    if not selected_forms:
        return {"success": False, "message": "No duty reports to store"}
    
    try:
        # Check for existing records for this analysis period to prevent duplicates
        existing_query = supabase.table("duty_report_incidents").select("*").eq("date_range_start", start_date.isoformat()).eq("date_range_end", end_date.isoformat())
        
        if generated_by_user_id:
            existing_query = existing_query.eq("generated_by_user_id", generated_by_user_id)
        
        existing_response = existing_query.execute()
        existing_records = existing_response.data if existing_response.data else []
        
        # If records exist for this analysis period, ask user what to do
        if existing_records:
            return {
                "success": False, 
                "message": f"Found {len(existing_records)} existing records for this analysis period ({start_date} to {end_date}). Use 'Replace Existing Data' option if you want to update the data.",
                "existing_count": len(existing_records),
                "duplicate_detected": True
            }
        
        stored_records = []
        for form in selected_forms:
            current_revision = form.get('current_revision', {})
            date_str = current_revision.get('date', '')
            report_date = None
            if date_str:
                try:
                    form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    report_date = form_datetime.date()
                except:
                    report_date = None
            hall_name = "Unknown Hall"
            responses = current_revision.get('responses', [])
            # First pass: find hall/building
            for response in responses:
                field_label = response.get('field_label', '').lower()
                field_response = str(response.get('response', '')).strip()
                if any(word in field_label for word in ['building', 'hall', 'location', 'area']):
                    if field_response and field_response not in ['None', '']:
                        hall_name = field_response
                        break
            # Second pass: extract incidents and create records
            report_text = ""
            for response in responses:
                field_response = str(response.get('response', '')).strip().lower()
                report_text += field_response + " "
            author = current_revision.get('author', 'Unknown')
            form_name = form.get('form_template_name', 'Unknown Form')
            base_record = {
                'report_date': report_date.isoformat() if report_date else None,
                'hall_name': hall_name,
                'staff_author': author,
                'form_type': form_name,
                'generated_by_user_id': generated_by_user_id,
                'created_at': datetime.now().isoformat(),
                'date_range_start': start_date.isoformat(),
                'date_range_end': end_date.isoformat()
            }
            # Create incident records based on detected patterns
            incidents_found = []
            
            # First pass: find hall/building
            for response in responses:
                field_label = response.get('field_label', '').lower()
                field_response = str(response.get('response', '')).strip()
                
                if any(word in field_label for word in ['building', 'hall', 'location', 'area']):
                    if field_response and field_response not in ['None', '']:
                        hall_name = field_response
                        break
            
            # Second pass: extract incidents and create records
            report_text = ""
            for response in responses:
                field_response = str(response.get('response', '')).strip().lower()
                report_text += field_response + " "
            
            # Create base record for this duty report
            base_record = {
                'report_date': report_date.isoformat() if report_date else None,
                'hall_name': hall_name,
                'staff_author': author,
                'form_type': form_name,
                'generated_by_user_id': generated_by_user_id,
                'created_at': datetime.now().isoformat(),
                'date_range_start': start_date.isoformat(),
                'date_range_end': end_date.isoformat()
            }
            
            # Create incident records based on detected patterns
            incidents_found = []
            
            if any(word in report_text for word in ['lockout', 'locked out', 'key']):
                incidents_found.append({**base_record, 'incident_type': 'lockout', 'incident_count': 1})
            
            if any(word in report_text for word in ['maintenance', 'repair', 'broken', 'leak', 'ac', 'heat']):
                incidents_found.append({**base_record, 'incident_type': 'maintenance', 'incident_count': 1})
            
            if any(word in report_text for word in ['alcohol', 'intoxicated', 'violation', 'policy', 'noise']):
                incidents_found.append({**base_record, 'incident_type': 'policy_violation', 'incident_count': 1})
            
            if any(word in report_text for word in ['safety', 'emergency', 'security', 'fire', 'medical']):
                incidents_found.append({**base_record, 'incident_type': 'safety_concern', 'incident_count': 1})
            
            # If no specific incidents found, create a general activity record
            if not incidents_found:
                incidents_found.append({**base_record, 'incident_type': 'general_activity', 'incident_count': 1})
            
            stored_records.extend(incidents_found)
        
        # Store all records in Supabase with enhanced error handling
        if stored_records:
            saved_count = 0
            skipped_count = 0
            errors = []
            
            # Process records in batches to handle duplicates gracefully
            for record in stored_records:
                try:
                    # Check if this specific record already exists
                    existing_check = supabase.table("duty_report_incidents").select("*").eq(
                        "report_date", record['report_date']
                    ).eq(
                        "hall_name", record['hall_name']
                    ).eq(
                        "staff_author", record['staff_author']
                    ).eq(
                        "incident_type", record['incident_type']
                    ).execute()
                    
                    if existing_check.data:
                        skipped_count += 1
                    else:
                        # Safe to insert
                        insert_response = supabase.table("duty_report_incidents").insert(record).execute()
                        if insert_response.data:
                            saved_count += 1
                        else:
                            errors.append(f"Failed to insert {record['incident_type']} record")
                            
                except Exception as e:
                    error_msg = str(e)
                    if "duplicate key" in error_msg or "violates unique constraint" in error_msg:
                        skipped_count += 1
                    else:
                        errors.append(f"Error inserting record: {error_msg}")
            
            # Prepare result message
            messages = []
            if saved_count > 0:
                messages.append(f"✅ Saved {saved_count} new incident records")
            if skipped_count > 0:
                messages.append(f"⚠️ Skipped {skipped_count} duplicate records")
            if errors:
                messages.append(f"❌ {len(errors)} errors occurred")
            
            return {
                "success": saved_count > 0 or skipped_count > 0,
                "message": " | ".join(messages) if messages else "No records processed",
                "records_saved": saved_count,
                "records_skipped": skipped_count,
                "reports_processed": len(selected_forms),
                "errors": errors
            }
        else:
            return {"success": False, "message": "No incident records generated"}
            
    except Exception as e:
        return {"success": False, "message": f"Error storing duty report data: {str(e)}"}

def save_duty_analysis(analysis_data, week_ending_date, created_by_user_id=None):
    """Save a duty analysis report to the database for permanent storage"""
    try:
        # Determine report type
        report_type = "weekly_summary" if analysis_data['report_type'] == "📅 Weekly Summary Report" else "standard_analysis"
        
        # Handle date conversions for database storage
        start_date = analysis_data['filter_info']['start_date']
        end_date = analysis_data['filter_info']['end_date']
        
        # Convert to ISO format strings if they're date objects
        if hasattr(start_date, 'isoformat'):
            start_date = start_date.isoformat()
        if hasattr(end_date, 'isoformat'):
            end_date = end_date.isoformat()
        
        # Check for existing analysis with same week ending date and user
        existing_query = supabase.table("saved_duty_analyses").select("*").eq("week_ending_date", week_ending_date)
        if created_by_user_id:
            existing_query = existing_query.eq("created_by", created_by_user_id)
        
        existing_response = existing_query.execute()
        existing_records = existing_response.data if existing_response.data else []
        
        # Prepare data for saving
        save_data = {
            'week_ending_date': week_ending_date,
            'report_type': report_type,
            'date_range_start': start_date,
            'date_range_end': end_date,
            'reports_analyzed': len(analysis_data['selected_forms']),
            'total_selected': len(analysis_data.get('all_selected_forms', analysis_data['selected_forms'])),
            'analysis_text': analysis_data['summary'],
            'created_by': created_by_user_id,
            'updated_at': datetime.now().isoformat()
        }
        
        # Save to database with enhanced duplicate detection
        if existing_records:
            # Record already exists, provide feedback but don't create duplicate
            return {
                "success": True,
                "message": f"Duty analysis for week ending {week_ending_date} already exists (no duplicate created)",
                "existing_id": existing_records[0]['id'],
                "action": "duplicate_prevented"
            }
        else:
            # No existing record, safe to insert
            try:
                response = supabase.table("saved_duty_analyses").insert(save_data).execute()
                
                if response.data:
                    return {
                        "success": True, 
                        "message": f"✅ Duty analysis saved for week ending {week_ending_date}",
                        "saved_id": response.data[0]['id'],
                        "action": "created_new"
                    }
                else:
                    return {"success": False, "message": "Failed to save duty analysis - no data returned"}
                    
            except Exception as e:
                error_msg = str(e)
                
                # Check if it's a table doesn't exist error
                if "does not exist" in error_msg or "relation" in error_msg:
                    return {
                        "success": False, 
                        "message": "Database tables not found. Please run the database schema setup first. See database_schema_saved_reports.sql"
                    }
                # Check if it's a duplicate key error (fallback)
                elif "duplicate key" in error_msg or "already exists" in error_msg or "violates unique constraint" in error_msg:
                    return {
                        "success": True,
                        "message": f"Duty analysis for week ending {week_ending_date} already exists (no duplicate created)",
                        "action": "duplicate_prevented"
                    }
                else:
                    return {"success": False, "message": f"Database error: {error_msg}"}
                
    except Exception as e:
        return {"success": False, "message": f"Error saving duty analysis: {str(e)}"}

def save_staff_recognition(recognition_data, week_ending_date, created_by_user_id=None):
    """Save a staff recognition report to the database for permanent storage"""
    try:
        # Extract recognition components
        ascend_rec = recognition_data.get("ascend_recognition", {})
        north_rec = recognition_data.get("north_recognition", {})
        
        # Create formatted recognition text
        recognition_text = f"""# Weekly Staff Recognition Report

**Week Ending:** {week_ending_date}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 🌟 ASCEND Recognition
"""
        
        if ascend_rec:
            recognition_text += f"""**Recipient:** {ascend_rec.get('staff_member', 'Unknown')}
**Category:** {ascend_rec.get('category', 'Unknown')}
**Performance Score:** {ascend_rec.get('score', 0)}/10
**Reasoning:** {ascend_rec.get('reasoning', 'No reasoning provided')}

"""
        else:
            recognition_text += "No ASCEND recognition awarded this week.\n\n"
        
        recognition_text += """## 🧭 NORTH Recognition
"""
        
        if north_rec:
            recognition_text += f"""**Recipient:** {north_rec.get('staff_member', 'Unknown')}
**Category:** {north_rec.get('category', 'Unknown')}
**Performance Score:** {north_rec.get('score', 0)}/10
**Reasoning:** {north_rec.get('reasoning', 'No reasoning provided')}

"""
        else:
            recognition_text += "No NORTH recognition awarded this week.\n\n"
        
        recognition_text += """---
Generated by UND Housing & Residence Life Weekly Reporting Tool - Staff Recognition System"""
        
        # Prepare data for saving
        save_data = {
            'week_ending_date': week_ending_date,
            'ascend_recognition': json.dumps(ascend_rec) if ascend_rec else None,
            'north_recognition': json.dumps(north_rec) if north_rec else None,
            'recognition_text': recognition_text,
            'created_by': created_by_user_id,
            'updated_at': datetime.now().isoformat()
        }
        
        # Save to database with graceful error handling
        try:
            # Try simple insert first
            response = supabase.table("saved_staff_recognition").insert(save_data).execute()
            
            if response.data:
                return {
                    "success": True, 
                    "message": f"Staff recognition saved for week ending {week_ending_date}",
                    "saved_id": response.data[0]['id']
                }
            else:
                return {"success": False, "message": "Failed to save staff recognition"}
                
        except Exception as e:
            error_msg = str(e)
            
            # Check if it's a table doesn't exist error
            if "does not exist" in error_msg or "relation" in error_msg:
                return {
                    "success": False, 
                    "message": "Database tables not found. Please run the database schema setup first. See database_schema_saved_reports.sql"
                }
            # Check if it's a duplicate key error
            elif "duplicate key" in error_msg or "already exists" in error_msg:
                return {
                    "success": True,
                    "message": f"Recognition for week ending {week_ending_date} already exists (no duplicate created)"
                }
            else:
                return {"success": False, "message": f"Database error: {error_msg}"}
            
    except Exception as e:
        return {"success": False, "message": f"Error saving staff recognition: {str(e)}"}

def replace_duty_report_data(selected_forms, start_date, end_date, generated_by_user_id=None):
    """Replace existing duty report data for the same analysis period"""
    if not selected_forms:
        return {"success": False, "message": "No duty reports to store"}
    
    try:
        # Delete existing records for this analysis period
        delete_query = supabase.table("duty_report_incidents").delete().eq("date_range_start", start_date.isoformat()).eq("date_range_end", end_date.isoformat())
        
        if generated_by_user_id:
            delete_query = delete_query.eq("generated_by_user_id", generated_by_user_id)
        
        delete_response = delete_query.execute()
        
        # Now store the new data using the original function logic
        stored_records = []
        
        for form in selected_forms:
            current_revision = form.get('current_revision', {})
            author = current_revision.get('author', 'Unknown')
            date_str = current_revision.get('date', '')
            form_name = form.get('form_template_name', 'Unknown Form')
            
            # Parse date
            report_date = None
            if date_str:
                try:
                    form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    report_date = form_datetime.date()
                except:
                    report_date = None
            
            # Extract hall/building info
            hall_name = "Unknown Hall"
            responses = current_revision.get('responses', [])
            
            # First pass: find hall/building
            for response in responses:
                field_label = response.get('field_label', '').lower()
                field_response = str(response.get('response', '')).strip()
                
                if any(word in field_label for word in ['building', 'hall', 'location', 'area']):
                    if field_response and field_response not in ['None', '']:
                        hall_name = field_response
                        break
            
            # Second pass: extract incidents and create records
            report_text = ""
            for response in responses:
                field_response = str(response.get('response', '')).strip().lower()
                report_text += field_response + " "
            
            # Create base record for this duty report
            base_record = {
                'report_date': report_date.isoformat() if report_date else None,
                'hall_name': hall_name,
                'staff_author': author,
                'form_type': form_name,
                'generated_by_user_id': generated_by_user_id,
                'created_at': datetime.now().isoformat(),
                'date_range_start': start_date.isoformat(),
                'date_range_end': end_date.isoformat()
            }
            
            # Create incident records based on detected patterns
            incidents_found = []
            
            if any(word in report_text for word in ['lockout', 'locked out', 'key']):
                incidents_found.append({**base_record, 'incident_type': 'lockout', 'incident_count': 1})
            
            if any(word in report_text for word in ['maintenance', 'repair', 'broken', 'leak', 'ac', 'heat']):
                incidents_found.append({**base_record, 'incident_type': 'maintenance', 'incident_count': 1})
            
            if any(word in report_text for word in ['alcohol', 'intoxicated', 'violation', 'policy', 'noise']):
                incidents_found.append({**base_record, 'incident_type': 'policy_violation', 'incident_count': 1})
            
            if any(word in report_text for word in ['safety', 'emergency', 'security', 'fire', 'medical']):
                incidents_found.append({**base_record, 'incident_type': 'safety_concern', 'incident_count': 1})
            
            # If no specific incidents found, create a general activity record
            if not incidents_found:
                incidents_found.append({**base_record, 'incident_type': 'general_activity', 'incident_count': 1})
            
            stored_records.extend(incidents_found)
        
        # Store all new records in Supabase with enhanced error handling
        if stored_records:
            saved_count = 0
            errors = []
            
            # Insert records in batches with error handling
            for record in stored_records:
                try:
                    insert_response = supabase.table("duty_report_incidents").insert(record).execute()
                    if insert_response.data:
                        saved_count += 1
                    else:
                        errors.append(f"Failed to insert {record['incident_type']} record")
                        
                except Exception as e:
                    errors.append(f"Error inserting {record['incident_type']} record: {str(e)}")
            
            # Prepare result message
            if saved_count > 0:
                success_msg = f"✅ Replaced data: saved {saved_count} incident records from {len(selected_forms)} duty reports"
                if errors:
                    success_msg += f" | ❌ {len(errors)} errors occurred"
                
                return {
                    "success": True, 
                    "message": success_msg,
                    "records_stored": saved_count,
                    "reports_processed": len(selected_forms),
                    "operation": "replaced",
                    "errors": errors
                }
            else:
                return {
                    "success": False, 
                    "message": f"Failed to store any records. Errors: {'; '.join(errors)}"
                }
        else:
            return {"success": False, "message": "No incident records generated"}
            
    except Exception as e:
        return {"success": False, "message": f"Error replacing duty report data: {str(e)}"}

def get_historical_duty_data(start_date=None, end_date=None, halls=None, incident_types=None):
    """Retrieve historical duty report data for graphing and analysis"""
    try:
        query = supabase.table("duty_report_incidents").select("*")
        
        if start_date:
            query = query.gte("report_date", start_date.isoformat())
        if end_date:
            query = query.lte("report_date", end_date.isoformat())
        if halls:
            query = query.in_("hall_name", halls)
        if incident_types:
            query = query.in_("incident_type", incident_types)
        
        response = query.order("report_date", desc=False).execute()
        
        return {"success": True, "data": response.data}
        
    except Exception as e:
        return {"success": False, "message": f"Error retrieving historical data: {str(e)}"}

def create_incident_graphs(start_date, end_date, halls=None, incident_types=None):
    """Create graphs from historical duty report data"""
    try:
        # Get historical data
        data_result = get_historical_duty_data(start_date, end_date, halls, incident_types)
        
        if not data_result["success"]:
            return {"success": False, "message": data_result["message"]}
        
        incidents = data_result["data"]
        
        if not incidents:
            return {"success": False, "message": "No historical data found for the specified criteria"}
        
        # Convert to DataFrame for easy analysis
        import pandas as pd
        df = pd.DataFrame(incidents)
        df['report_date'] = pd.to_datetime(df['report_date'])
        
        # Create summary statistics
        summary = {
            "total_incidents": len(incidents),
            "date_range": f"{start_date} to {end_date}",
            "halls_covered": df['hall_name'].nunique(),
            "incident_types": df['incident_type'].nunique(),
            "by_hall": df.groupby('hall_name')['incident_count'].sum().to_dict(),
            "by_type": df.groupby('incident_type')['incident_count'].sum().to_dict(),
            "by_date": df.groupby(df['report_date'].dt.date)['incident_count'].sum().to_dict()
        }
        
        return {"success": True, "data": incidents, "summary": summary, "dataframe": df}
        
    except Exception as e:
        return {"success": False, "message": f"Error creating graphs: {str(e)}"}

def create_duty_report_summary(selected_forms, start_date, end_date):
    """Create a standard comprehensive duty report analysis"""
    if not selected_forms:
        return "No duty reports selected for analysis."
    
    try:
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
        
        # Create comprehensive duty report AI prompt
        prompt = f"""
You are a senior residence life administrator analyzing duty reports for supervisory insights. Provide a comprehensive analysis that covers:

1. **EXECUTIVE SUMMARY**
   - Overview of reporting period and scope
   - Key findings and trends identified
   - Overall staff performance assessment

2. **INCIDENT ANALYSIS**
   - Categorized breakdown of all incidents reported
   - Severity assessment and patterns identified
   - Safety and security concerns highlighted

3. **OPERATIONAL INSIGHTS**
   - Staff response effectiveness and timeliness
   - Policy compliance observations
   - Training or procedural recommendations

4. **FACILITY & MAINTENANCE TRENDS**
   - Recurring facility issues requiring attention
   - Maintenance response effectiveness
   - Preventive action recommendations

5. **SUPERVISORY RECOMMENDATIONS**
   - Immediate action items requiring administrative follow-up
   - Staff development opportunities identified
   - Policy or procedural improvements suggested

6. **COMMUNITY IMPACT ASSESSMENT**
   - Resident satisfaction and engagement indicators
   - Community standards enforcement patterns
   - Educational programming opportunities identified

Provide specific examples and data-driven insights while maintaining appropriate confidentiality. Focus on actionable recommendations for residence life leadership.

DUTY REPORTS DATA:
{reports_text}

Please provide a comprehensive supervisory analysis:
"""

        # Use Gemini 2.5 Flash for better quota efficiency  
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        
        with st.spinner(f"AI is analyzing {len(selected_forms)} duty reports..."):
            result = model.generate_content(prompt)
            if not result or not getattr(result, 'text', None) or not result.text.strip():
                return "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."
            return result.text
            
    except Exception as e:
        return f"Error generating duty report summary: {str(e)}"

# --- Engagement Analysis Functions ---
def analyze_engagement_forms_with_ai(selected_forms, report_type, filter_info):
    """Wrapper function to call appropriate engagement analysis function based on report type"""
    if report_type == "📅 Weekly Summary Report":
        return create_weekly_engagement_report_summary(selected_forms, filter_info)
    else:
        return create_engagement_report_summary(selected_forms, filter_info)

def create_weekly_engagement_report_summary(selected_forms, filter_info):
    """
    Create a weekly engagement report that looks at completed events from the past week
    and provides an outlook on approved events coming in the next 7 days.
    """
    if not selected_forms:
        return None
    
    try:
        from datetime import timedelta
        
        # Get current date for weekly analysis
        today = datetime.now().date()
        week_start = today - timedelta(days=7)
        week_end = today
        next_week_start = today + timedelta(days=1)
        next_week_end = today + timedelta(days=7)
        
        # Process all forms to categorize events
        completed_events = []  # Events that happened in past week with completion status
        upcoming_events = []   # Approved events happening in next 7 days
        all_semester_events = []  # All events for context
        
        for form in selected_forms:
            current_revision = form.get('current_revision', {})
            responses = current_revision.get('responses', [])
            
            # Extract key event information
            event_info = {
                'name': 'Unknown Event',
                'date': None,
                'approval': None,
                'hall': 'Unknown Hall',
                'organizer': current_revision.get('author', 'Unknown'),
                'attendance_planned': 0,
                'attendance_actual': None
            }
            
            # Map form responses
            for response in responses:
                field_label = response.get('field_label', '')
                field_response = str(response.get('response', '')).strip()
                
                if not field_response or field_response in ['None', 'null', '']:
                    continue
                
                # Event name
                if field_label == 'Name of Event':
                    event_info['name'] = field_response
                
                # Event approval status - CRITICAL for categorization
                elif field_label == 'Event approval' or field_label == 'Event Approval':
                    event_info['approval'] = field_response
                
                # Event date
                elif field_label == 'Date and Event Start Time':
                    parsed_date, _, _ = parse_event_datetime(field_response)
                    if parsed_date:
                        event_info['date'] = parsed_date
                
                # Location
                elif field_label == 'Hall':
                    event_info['hall'] = field_response
                
                # Planned attendance
                elif field_label == 'Anticipated Number Attendees':
                    try:
                        import re
                        numbers = re.findall(r'\d+', field_response)
                        if numbers:
                            event_info['attendance_planned'] = int(numbers[0])
                    except:
                        pass
            
            all_semester_events.append(event_info)
            
            # Categorize events based on date and approval
            if event_info['date'] and event_info['approval'] == 'Approved':
                if week_start <= event_info['date'] <= week_end:
                    # Completed events from past week
                    completed_events.append(event_info)
                elif next_week_start <= event_info['date'] <= next_week_end:
                    # Upcoming events next week
                    upcoming_events.append(event_info)
        
        # Create weekly engagement analysis text
        analysis_text = f"""
=== WEEKLY ENGAGEMENT ANALYSIS ===
Analysis Date: {today.strftime('%B %d, %Y')}
Past Week: {week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}
Next Week Outlook: {next_week_start.strftime('%B %d')} - {next_week_end.strftime('%B %d, %Y')}

COMPLETED EVENTS (Past Week):
"""
        
        if completed_events:
            for i, event in enumerate(completed_events, 1):
                analysis_text += f"\n{i}. {event['name']}"
                analysis_text += f"\n   Date: {event['date'].strftime('%B %d, %Y') if event['date'] else 'Unknown'}"
                analysis_text += f"\n   Hall: {event['hall']}"
                analysis_text += f"\n   Organizer: {event['organizer']}"
                analysis_text += f"\n   Planned Attendance: {event['attendance_planned']}"
                if event['attendance_actual']:
                    analysis_text += f"\n   Actual Attendance: {event['attendance_actual']}"
                analysis_text += "\n"
        else:
            analysis_text += "\nNo approved events were completed in the past week.\n"
        
        analysis_text += f"\n\nUPCOMING EVENTS (Next 7 Days):\n"
        
        if upcoming_events:
            for i, event in enumerate(upcoming_events, 1):
                analysis_text += f"\n{i}. {event['name']}"
                analysis_text += f"\n   Date: {event['date'].strftime('%B %d, %Y') if event['date'] else 'Unknown'}"
                analysis_text += f"\n   Hall: {event['hall']}"
                analysis_text += f"\n   Organizer: {event['organizer']}"
                analysis_text += f"\n   Expected Attendance: {event['attendance_planned']}"
                analysis_text += "\n"
        else:
            analysis_text += "\nNo approved events are scheduled for the next 7 days.\n"
        
        # Add semester overview for context
        approved_count = len([e for e in all_semester_events if e['approval'] == 'Approved'])
        pending_count = len([e for e in all_semester_events if not e['approval'] or e['approval'] not in ['Approved', 'Cancelled']])
        cancelled_count = len([e for e in all_semester_events if e['approval'] in ['Cancelled', 'Canceled']])
        
        analysis_text += f"""

FALL SEMESTER OVERVIEW:
- Total Event Submissions: {len(all_semester_events)}
- Approved Events: {approved_count}
- Pending Approval: {pending_count}
- Cancelled Events: {cancelled_count}
- Events Completed This Week: {len(completed_events)}
- Events Scheduled Next Week: {len(upcoming_events)}
"""
        
        # AI prompt for comprehensive weekly engagement analysis
        prompt = f"""
You are a senior Housing & Residence Life administrator analyzing weekly engagement patterns. Based on the event data provided, create a comprehensive weekly engagement report.

{analysis_text}

Please provide a professional analysis with these sections:

## WEEKLY ENGAGEMENT ANALYSIS

### Executive Summary
- Overview of engagement activity for the past week
- Key metrics and participation trends
- Notable successes and areas for improvement

### Completed Events Analysis (Past Week)
- Assessment of events that took place
- Attendance patterns and community response  
- Staff performance and event execution
- Programming themes and effectiveness

### Upcoming Events Outlook (Next 7 Days)
- Preview of scheduled approved events
- Anticipated attendance and participation
- Resource and support requirements
- Coordination and preparation recommendations

### Fall Semester Progress Assessment
- Overall programming momentum and trajectory
- Approval and planning pipeline health
- Staff development and programming growth
- Strategic recommendations for remainder of semester

### Supervisory Action Items
- Immediate support needed for upcoming events
- Staff recognition and development opportunities
- Resource allocation recommendations
- Policy or process improvements needed

Focus on actionable insights that will help supervisors support staff and enhance resident engagement through quality programming.
"""

        # Generate AI analysis
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        
        with st.spinner(f"AI is analyzing weekly engagement patterns..."):
            result = model.generate_content(prompt)
            
            return {
                'summary': result.text,
                'report_type': "📅 Weekly Engagement Summary", 
                'selected_forms': selected_forms,
                'filter_info': filter_info,
                'completed_events_count': len(completed_events),
                'upcoming_events_count': len(upcoming_events),
                'semester_stats': {
                    'total_submissions': len(all_semester_events),
                    'approved_events': approved_count,
                    'pending_events': pending_count,
                    'cancelled_events': cancelled_count
                }
            }
            
    except Exception as e:
        return {
            'summary': f"Error generating weekly engagement analysis: {str(e)}",
            'report_type': "📅 Weekly Engagement Summary",
            'selected_forms': selected_forms,
            'filter_info': filter_info,
            'error': True
        }

def create_engagement_report_summary(selected_forms, filter_info):
    """Create a standard comprehensive engagement analysis"""
    if not selected_forms:
        return None
    
    try:
        start_date = filter_info['start_date']
        end_date = filter_info['end_date']
        
        # Prepare engagement data for AI analysis
        events_text = f"\n=== ENGAGEMENT ANALYSIS ===\n"
        events_text += f"Date Range: {start_date} to {end_date}\n"
        events_text += f"Total Event Submissions: {len(selected_forms)}\n\n"
        
        for i, form in enumerate(selected_forms, 1):
            current_revision = form.get('current_revision', {})
            author = current_revision.get('author', 'Unknown')
            date_str = current_revision.get('date', '')
            
            form_date = "Unknown Date"
            if date_str:
                try:
                    form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    form_date = form_datetime.strftime('%Y-%m-%d %H:%M')
                except:
                    pass
            
            events_text += f"\n--- Event Submission {i} ---\n"
            events_text += f"Submitted by: {author}\n"
            events_text += f"Submission Date: {form_date}\n"
            
            responses = current_revision.get('responses', [])
            for response in responses:
                field_label = response.get('field_label', 'Unknown Field')
                field_response = str(response.get('response', '')).strip()
                if field_response and field_response != 'None':
                    events_text += f"{field_label}: {field_response}\n"
        
        # AI prompt for standard engagement analysis
        prompt = f"""
Analyze the following event submission data and provide a comprehensive engagement analysis for UND Housing & Residence Life.

{events_text}

Please provide a detailed analysis organized in these sections:

1. **EXECUTIVE SUMMARY**
   - Overall engagement activity level and trends
   - Key findings and notable events
   - Total events and estimated attendance figures

2. **EVENT PROGRAMMING ANALYSIS**  
   - Types of events being planned and conducted
   - Programming themes and target audiences
   - Educational vs. social vs. wellness programming balance
   - Innovation and creativity in event planning

3. **COMMUNITY ENGAGEMENT INSIGHTS**
   - Resident participation patterns and enthusiasm
   - Community building effectiveness through events
   - Cross-cultural and inclusive programming efforts
   - Collaboration between halls and staff

4. **STAFF DEVELOPMENT & LEADERSHIP**
   - Staff members demonstrating leadership in programming
   - Professional development through event coordination
   - Training needs or opportunities identified
   - Recognition of exceptional programming efforts

5. **FACILITIES & RESOURCE UTILIZATION**
   - Space usage patterns for events
   - Resource allocation and budget considerations
   - Technology and equipment needs
   - Partnership with campus departments

6. **UPCOMING EVENTS & STRATEGIC PLANNING**
   - Future events in planning stages
   - Seasonal programming considerations
   - Long-term engagement strategy recommendations
   - Calendar coordination and scheduling insights

7. **SUPERVISORY RECOMMENDATIONS**
   - Immediate support needed for upcoming events
   - Staff development opportunities
   - Resource allocation suggestions
   - Policy or procedural improvements for better programming

Provide actionable insights that will help supervisors support staff and enhance resident engagement through quality programming.
"""

        model = genai.GenerativeModel("models/gemini-2.5-flash")
        
        with st.spinner(f"AI is analyzing {len(selected_forms)} event submissions..."):
            result = model.generate_content(prompt)
            
            return {
                'summary': result.text,
                'report_type': "📊 Standard Analysis",
                'selected_forms': selected_forms,
                'filter_info': filter_info
            }
            
    except Exception as e:
        return None

def extract_engagement_quantitative_data(selected_forms):
    """
    Extract complete engagement data from Residence Life Event Submission forms.
    Now handles full semester view (August 22 - December 31) with proper event lifecycle management.
    """
    if not selected_forms:
        return {"success": False, "message": "No forms provided"}
    
    try:
        import json
        from collections import defaultdict
        
        # Statistics tracking
        processed_events = []
        semester_stats = {
            'total_submissions': 0,
            'approved_events': 0,
            'pending_events': 0,
            'cancelled_events': 0,
            'forms_with_errors': 0,
            'duplicate_forms': 0,
            'fall_semester_events': 0
        }
        
        # Fall semester date range (August 22 - December 31)
        fall_start = datetime(2024, 8, 22).date()
        fall_end = datetime(2024, 12, 31).date()
        
        # Process each form to extract complete engagement data
        for i, form in enumerate(selected_forms):
            semester_stats['total_submissions'] += 1
            current_revision = form.get('current_revision', {})
            author = current_revision.get('author', 'Unknown')
            submission_date_str = current_revision.get('date', '')
            
            # Extract form ID from Roompact - critical for uniqueness
            form_id = None
            if form.get('id'):
                form_id = str(form.get('id'))
            elif form.get('form_id'):
                form_id = str(form.get('form_id'))
            elif current_revision.get('id'):
                form_id = str(current_revision.get('id'))
            else:
                # Generate a unique ID if we can't find one
                form_id = f"FORM_{i}_{hash(str(form))}"
            
            # Initialize complete event data structure matching new schema
            event_data = {
                # Form metadata
                'form_submission_id': form_id,
                'submission_date': None,
                
                # Event basic information
                'event_name': None,
                'event_type': 'General Event',
                'event_description': None,
                
                # Event scheduling
                'event_date': None,
                'event_start_time': None,
                'event_end_time': None,
                'event_duration_hours': None,
                
                # Event approval and status (key change)
                'event_approval': None,  # This will determine event_status via generated column
                
                # Location information
                'hall': 'Unknown Hall',
                'specific_location': None,
                'location_notes': None,
                
                # Attendance information
                'anticipated_attendance': 0,
                'actual_attendance': None,
                
                # Staffing and organization
                'event_organizer': author,
                'co_organizers': None,
                'staff_advisor': None,
                
                # Programming details
                'programming_theme': None,
                'target_audience': None,
                'educational_objectives': None,
                
                # Budget and resources
                'estimated_budget': None,
                'actual_budget': None,
                'funding_source': None,
                'resources_needed': None,
                
                # Partnerships and collaboration
                'collaboration_partners': None,
                'campus_partners': None,
                'external_partners': None,
                
                # Marketing and promotion
                'marketing_plan': None,
                'promotional_materials': None,
                'registration_required': False,
                'registration_deadline': None,
                
                # Follow-up and assessment
                'assessment_method': None,
                'follow_up_actions': None,
                'event_feedback': None,
                'lessons_learned': None,
                
                # System fields
                'semester': 'Fall 2024',
                'academic_year': '2024-2025',
                'generated_by_user_id': None,  # Will be set by calling function
                
                # Store complete form as JSONB for future reference
                'form_responses': json.dumps(form),
                
                # Debug information
                'form_debug_info': {
                    'form_keys': list(form.keys()) if form else [],
                    'form_id_found': form_id,
                    'revision_keys': list(current_revision.keys()) if current_revision else [],
                    'responses_count': len(current_revision.get('responses', [])),
                    'processing_timestamp': datetime.now().isoformat()
                }
            }
            
            # Extract submission date
            if submission_date_str:
                try:
                    form_datetime = datetime.fromisoformat(submission_date_str.replace('Z', '+00:00'))
                    event_data['submission_date'] = form_datetime
                except Exception as e:
                    event_data['form_debug_info']['submission_date_error'] = str(e)
            
            # Process form responses with comprehensive field mapping
            responses = current_revision.get('responses', [])
            
            for response in responses:
                field_label = response.get('field_label', '')
                field_response = str(response.get('response', '')).strip()
                
                # Skip empty responses
                if not field_response or field_response in ['None', 'null', '']:
                    continue
                
                field_label_lower = field_label.lower()
                
                # CRITICAL: Map Event Approval field to determine status
                # Updated to handle actual field names from API
                if (field_label == 'Event approval' or  # Main approval field (lowercase 'a')
                    field_label == 'Event Approval' or  # Legacy/alternative format
                    'event approval' in field_label_lower or
                    field_label in ['Approval', 'Status', 'Event Status', 'Approval Status',
                                   'Event Approved-Supervisor Only', 'Tag Staff Program Approved For']):
                    event_data['event_approval'] = field_response
                    
                    # Track statistics
                    if field_response == 'Approved':
                        semester_stats['approved_events'] += 1
                    elif field_response in ['Cancelled', 'Canceled']:
                        semester_stats['cancelled_events'] += 1
                    else:
                        semester_stats['pending_events'] += 1
                
                # NEW COMPREHENSIVE FIELD MAPPING
                
                # Meeting and Date Information
                elif field_label == 'Date and Time of Meeting':
                    event_data['meeting_date_time'] = field_response
                elif field_label == 'Date':
                    event_data['form_date'] = field_response
                
                # Staff and Supervisor Information
                elif field_label == 'Tag your RD & CA':
                    event_data['tag_rd_ca'] = field_response
                elif field_label == 'Name of staff person(s) checking out master keys':
                    event_data['staff_checking_out_keys'] = field_response
                elif field_label == 'Duty Partner':
                    event_data['duty_partner'] = field_response
                
                # Key Management
                elif field_label == 'Checked Out - Date and Time':
                    event_data['key_checkout_datetime'] = field_response
                elif field_label == 'Checked In - Time ':
                    event_data['key_checkin_time'] = field_response
                elif field_label == 'Reason for checking out keys':
                    event_data['key_checkout_reason'] = field_response
                elif field_label == 'If assisting with a lockout, please tag the name of the resident':
                    event_data['lockout_resident_name'] = field_response
                
                # Cost and Purchasing Information
                elif field_label == 'Estimated Cost of Items for Meeting':
                    try:
                        event_data['estimated_meeting_cost'] = float(field_response) if field_response != '0' else 0
                    except:
                        pass
                elif field_label == 'Items to Purchase':
                    event_data['items_to_purchase'] = field_response
                elif field_label == 'Catering Order':
                    event_data['catering_order'] = field_response
                elif field_label == 'Total Expenses':
                    try:
                        event_data['total_expenses'] = float(field_response) if field_response != '0' else 0
                    except:
                        pass
                
                # Round/Duty Information
                elif field_label == 'Round Checklist: While on my first round, I did the following':
                    event_data['round_first_checklist'] = field_response
                elif field_label == 'Round Checklist: While on my second round, I completed the following':
                    event_data['round_second_checklist'] = field_response
                elif field_label == 'Round Checklist: While on my third round, I completed the following (Weekends Only)':
                    event_data['round_third_checklist'] = field_response
                elif field_label == 'I started my first round at':
                    event_data['round_first_start_time'] = field_response
                elif field_label == 'I ended my first round at':
                    event_data['round_first_end_time'] = field_response
                elif field_label == 'Round Summary: While on my first round, the following occurred':
                    event_data['round_first_summary'] = field_response
                elif field_label == 'I started my second round at':
                    event_data['round_second_start_time'] = field_response
                elif field_label == 'I ended my second round at':
                    event_data['round_second_end_time'] = field_response
                elif field_label == 'Round Summary: While on my second round, the following occurred':
                    event_data['round_second_summary'] = field_response
                elif field_label == 'I started my third round at (Weekends Only)':
                    event_data['round_third_start_time'] = field_response
                elif field_label == 'I ended my third round at (Weekends Only)':
                    event_data['round_third_end_time'] = field_response
                elif field_label == 'Round Summary: While on my third round, the following occurred (Weekends Only)':
                    event_data['round_third_summary'] = field_response
                elif field_label == 'Duty Notes:':
                    event_data['duty_notes'] = field_response
                
                # Evaluation Fields
                elif field_label == 'Evaluation Type':
                    event_data['evaluation_type'] = field_response
                elif field_label == 'Experience ':
                    event_data['experience_rating'] = field_response
                elif field_label == 'Experience Rating Justification':
                    event_data['experience_justification'] = field_response
                elif field_label == 'On Call Response ':
                    event_data['on_call_response'] = field_response
                elif field_label == 'On Call Rating Justification ':
                    event_data['on_call_justification'] = field_response
                elif field_label == 'Role Model':
                    event_data['role_model_rating'] = field_response
                elif field_label == 'Role Model Rating Justification ':
                    event_data['role_model_justification'] = field_response
                elif field_label == 'Community Development ':
                    event_data['community_development_rating'] = field_response
                elif field_label == 'Community Development Rating Justification ':
                    event_data['community_development_justification'] = field_response
                elif field_label == 'Goal Setting':
                    event_data['goal_setting'] = field_response
                elif field_label == 'At this time are you interested in returning to the RA position next academic year?':
                    event_data['returning_interest'] = field_response
                elif field_label == 'Outline how you will attract residents to the meeting, other than signs and/or advertisements. ':
                    event_data['meeting_attraction_plan'] = field_response
                
                # Additional Information
                elif field_label == 'Please provide any additional information about any phone calls received or incidents that occurred while not on rounds. ':
                    event_data['additional_phone_incidents'] = field_response
                elif field_label == 'If other, explain below':
                    # Could be added to a general notes field or specific context
                    if 'other_explanation' not in event_data:
                        event_data['other_explanation'] = field_response
                
                # EXISTING FIELD MAPPING (keep current logic)
                
                # Event name - exact field mapping
                elif (field_label == 'Name of Event' or field_label == 'Name of event' or
                      field_label in ['Event Name', 'Event Title', 'Program Name', 'Activity Name']):
                    event_data['event_name'] = field_response[:200]
                
                # Event type/category
                elif (field_label in ['Event Type', 'Program Type', 'Category', 'Type of Event', 'Event Category'] or
                      'event type' in field_label_lower or 'program type' in field_label_lower):
                    event_data['event_type'] = field_response[:100]
                
                # Event description
                elif (field_label in ['Description', 'Event Description', 'Program Description', 'Details'] or
                      'description' in field_label_lower):
                    event_data['event_description'] = field_response[:1000]
                
                # Event date and time - enhanced parsing
                elif (field_label == 'Date and Event Start Time' or 
                      field_label in ['Event Date', 'Date of Event', 'Program Date', 'When', 'Date', 'Start Date']):
                    
                    # Enhanced date/time parsing
                    parsed_date, parsed_start_time, parsed_end_time = parse_event_datetime(field_response)
                    
                    if parsed_date:
                        event_data['event_date'] = parsed_date
                        
                        # Check if event falls within fall semester
                        if fall_start <= parsed_date <= fall_end:
                            semester_stats['fall_semester_events'] += 1
                    
                    if parsed_start_time:
                        event_data['event_start_time'] = parsed_start_time
                    
                    if parsed_end_time:
                        event_data['event_end_time'] = parsed_end_time
                
                # Location - Hall field
                elif (field_label == 'Hall' or field_label_lower == 'hall' or
                      field_label in ['Location', 'Building', 'Where', 'Event Location']):
                    event_data['hall'] = field_response[:100]
                
                # Specific location details
                elif (field_label in ['Room', 'Specific Location', 'Room Number', 'Area'] or
                      'room' in field_label_lower or 'location' in field_label_lower):
                    event_data['specific_location'] = field_response[:200]
                
                # Attendance - exact field mapping
                elif (field_label == 'Anticipated Number Attendees' or 
                      field_label in ['Anticipated Attendance', 'Expected Attendance', 'Number of Attendees', 'Participants']):
                    try:
                        import re
                        # Extract first number from response
                        numbers = re.findall(r'\d+', field_response)
                        if numbers:
                            event_data['anticipated_attendance'] = int(numbers[0])
                    except:
                        pass
                
                # Programming theme
                elif (field_label in ['Theme', 'Programming Theme', 'Event Theme', 'Program Focus'] or
                      'theme' in field_label_lower):
                    event_data['programming_theme'] = field_response[:200]
                
                # Target audience
                elif (field_label in ['Target Audience', 'Audience', 'Who is this for', 'Participants'] or
                      'target audience' in field_label_lower or 'audience' in field_label_lower):
                    event_data['target_audience'] = field_response[:200]
                
                # Budget information
                elif (field_label in ['Budget', 'Estimated Budget', 'Cost', 'Funding', 'Budget Amount'] or
                      'budget' in field_label_lower):
                    try:
                        import re
                        # Extract dollar amount
                        amounts = re.findall(r'[\d,]+\.?\d*', field_response.replace('$', '').replace(',', ''))
                        if amounts:
                            event_data['estimated_budget'] = float(amounts[0])
                    except:
                        pass
                
                # Collaboration and partnerships
                elif (field_label in ['Partners', 'Collaboration', 'Co-sponsors', 'Partner Organizations'] or
                      'partner' in field_label_lower or 'collaboration' in field_label_lower):
                    event_data['collaboration_partners'] = field_response[:500]
                
                # Educational objectives
                elif (field_label in ['Learning Objectives', 'Goals', 'Educational Goals', 'Purpose'] or
                      'objective' in field_label_lower or 'goal' in field_label_lower):
                    event_data['educational_objectives'] = field_response[:500]
                
                # Marketing and promotion
                elif (field_label in ['Marketing', 'Promotion', 'Advertising', 'Publicity'] or
                      'marketing' in field_label_lower or 'promotion' in field_label_lower):
                    event_data['marketing_plan'] = field_response[:500]
                
                # Resources needed
                elif (field_label in ['Resources', 'Equipment', 'Materials', 'Supplies'] or
                      'resource' in field_label_lower or 'equipment' in field_label_lower):
                    event_data['resources_needed'] = field_response[:500]
                
                # Assessment method
                elif (field_label in ['Assessment', 'Evaluation', 'Feedback Method', 'How will you measure success'] or
                      'assessment' in field_label_lower or 'evaluation' in field_label_lower):
                    event_data['assessment_method'] = field_response[:500]
            
            processed_events.append(event_data)
        
        return {
            "success": True,
            "message": f"Processed {len(processed_events)} event submissions for Fall semester analysis",
            "events_data": processed_events,
            "semester_statistics": semester_stats,
            "fall_semester_range": {
                "start_date": fall_start.isoformat(),
                "end_date": fall_end.isoformat()
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error processing engagement data: {str(e)}",
            "error_details": str(e)
        }

def parse_event_datetime(datetime_string):
    """
    Enhanced date/time parsing for event scheduling.
    Returns tuple: (date, start_time, end_time)
    """
    try:
        import re
        from datetime import time
        
        if not datetime_string or datetime_string.strip() == '':
            return None, None, None
        
        # Try dateutil parser first if available
        try:
            from dateutil import parser as date_parser
            parsed = date_parser.parse(datetime_string)
            return parsed.date(), parsed.time(), None
        except:
            pass
        
        # Manual parsing for common formats
        date_formats = [
            '%Y-%m-%d %H:%M:%S',      # 2024-10-17 14:30:00
            '%Y-%m-%d %H:%M',         # 2024-10-17 14:30
            '%m/%d/%Y %H:%M:%S',      # 10/17/2024 2:30:00
            '%m/%d/%Y %H:%M',         # 10/17/2024 2:30
            '%m/%d/%Y %I:%M %p',      # 10/17/2024 2:30 PM
            '%Y-%m-%d',               # 2024-10-17
            '%m/%d/%Y',               # 10/17/2024
            '%B %d, %Y %H:%M',        # October 17, 2024 14:30
            '%B %d, %Y',              # October 17, 2024
        ]
        
        for date_format in date_formats:
            try:
                clean_date_str = ' '.join(datetime_string.strip().split())
                parsed_dt = datetime.strptime(clean_date_str, date_format)
                
                # Extract time if present in format
                if '%H:%M' in date_format or '%I:%M' in date_format:
                    return parsed_dt.date(), parsed_dt.time(), None
                else:
                    return parsed_dt.date(), None, None
            except:
                continue
        
        # Regex fallback for date extraction
        date_patterns = [
            r'(\d{4}-\d{1,2}-\d{1,2})',        # YYYY-MM-DD
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',  # MM/DD/YYYY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, datetime_string)
            if match:
                try:
                    date_part = match.group(1)
                    if '-' in date_part and date_part.startswith('20'):
                        return datetime.strptime(date_part, '%Y-%m-%d').date(), None, None
                    elif '/' in date_part:
                        return datetime.strptime(date_part, '%m/%d/%Y').date(), None, None
                except:
                    continue
        
        return None, None, None
        
    except Exception:
        return None, None, None

def safe_datetime_convert(value):
    """Convert datetime objects to ISO format strings for database storage"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dt_time):
        return value.isoformat()
    return value

def safe_json_convert(data):
    """Convert complex objects to JSON-serializable format"""
    if isinstance(data, dict):
        return {k: safe_json_convert(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [safe_json_convert(item) for item in data]
    elif isinstance(data, (datetime, date, dt_time)):
        return safe_datetime_convert(data)
    else:
        return data

def create_db_based_engagement_analysis():
    """Create analysis based on database data with correct event_status"""
    from collections import defaultdict
    
    st.write("🔍 **Database-Based Analysis** (Using Generated Event Status)")
    
    try:
        # Query engagement data with event_status (generated column)
        response = supabase.table("engagement_report_data").select(
            "form_submission_id, event_name, event_approval, event_status, hall, "
            "anticipated_attendance, total_attendees, author_first, author_last, "
            "parsed_event_date, submission_date_chicago, specific_location, "
            "event_description, target_audience, purchasing_items, business_purpose"
        ).execute()
        
        if not response.data:
            st.error("❌ No engagement data found in database. Please sync data first.")
            return
        
        # Analyze the data with proper event_status
        stats = {
            'total_events': len(response.data),
            'approved_events': 0,
            'pending_events': 0,
            'cancelled_events': 0
        }
        
        events_by_status = defaultdict(list)
        
        for event in response.data:
            status = event.get('event_status', 'pending')
            events_by_status[status].append(event)
            
            # Count by status (using the generated column)
            if status == 'approved':
                stats['approved_events'] += 1
            elif status == 'cancelled':
                stats['cancelled_events'] += 1
            else:
                stats['pending_events'] += 1
        
        # Display overall statistics
        st.write("📊 **Event Status Summary:**")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Events", stats['total_events'])
        with col2:
            st.metric("✅ Approved", stats['approved_events'])
        with col3:
            st.metric("⏳ Pending", stats['pending_events']) 
        with col4:
            st.metric("❌ Cancelled", stats['cancelled_events'])
        
        # Show breakdown by status
        st.write("🔍 **Event Status Details:**")
        
        for status, events in events_by_status.items():
            with st.expander(f"{status.title()} Events ({len(events)})", expanded=(status == 'approved')):
                
                if events:
                    for event in events[:5]:  # Show first 5
                        event_name = event.get('event_name', 'Unnamed Event')
                        hall = event.get('hall', 'Unknown Hall')
                        approval = event.get('event_approval', 'No approval data')
                        
                        st.write(f"**{event_name}** (Hall: {hall})")
                        st.write(f"   - Form ID: {event.get('form_submission_id', 'N/A')}")
                        st.write(f"   - Approval Field: '{approval}'")
                        st.write(f"   - Generated Status: `{status}`")
                        st.write("")
                    
                    if len(events) > 5:
                        st.write(f"   ... and {len(events) - 5} more")
        
        # Check if event_approval field extraction is working
        st.write("🧪 **Event Approval Field Analysis:**")
        
        approval_values = defaultdict(int)
        empty_approval = 0
        
        for event in response.data:
            approval = event.get('event_approval', '')
            if approval and approval.strip():
                approval_values[approval.strip()] += 1
            else:
                empty_approval += 1
        
        if approval_values:
            st.write("**Found approval values:**")
            for approval, count in approval_values.items():
                st.write(f"- '{approval}': {count} events")
        
        if empty_approval > 0:
            st.write(f"**Empty/Missing approval values:** {empty_approval} events")
            st.warning("⚠️ Some events have empty event_approval fields. This may indicate field mapping issues.")
        
        # Test the generated column logic
        with st.expander("🎯 **Generated Status Column Logic**", expanded=False):
            st.write("The database automatically sets event_status based on:")
            st.code("""
CASE 
    WHEN event_approval IS NULL OR event_approval = '' THEN 'pending'
    WHEN event_approval ILIKE '%approved%' THEN 'approved'  
    WHEN event_approval ILIKE '%cancelled%' OR event_approval ILIKE '%canceled%' THEN 'cancelled'
    ELSE 'pending'
END
            """)
            
            st.write("**This means:**")
            st.write("- Empty or null approval → 'pending'")
            st.write("- Contains 'approved' (case-insensitive) → 'approved'")
            st.write("- Contains 'cancelled'/'canceled' → 'cancelled'")
            st.write("- Everything else → 'pending'")
        
    except Exception as e:
        st.error(f"❌ Error loading engagement data: {e}")

def save_engagement_data(analysis_data, created_by_user_id=None):
    """
    Save or update engagement data using simplified approach that matches API structure.
    Stores data exactly as received from the API to avoid serialization issues.
    """
    try:
        # Test database connection first
        try:
            db_test = supabase.table("engagement_report_data").select("id").limit(1).execute()
        except Exception as db_error:
            error_msg = str(db_error).lower()
            if "does not exist" in error_msg or "relation" in error_msg:
                return {
                    "success": False, 
                    "message": "Database table 'engagement_report_data' does not exist",
                    "error_details": "Run the SIMPLIFIED_ENGAGEMENT_SCHEMA.sql script in Supabase to create the table"
                }
            else:
                return {
                    "success": False, 
                    "message": f"Database connection error: {str(db_error)}",
                    "error_details": str(db_error)
                }
        
        # Work directly with the selected forms (no complex extraction)
        selected_forms = analysis_data['selected_forms']
        
        if not selected_forms:
            return {"success": False, "message": "No forms provided for saving"}
        
        # Simple statistics tracking
        total_saved = 0
        skipped_count = 0
        errors = []
        
        # Process each form directly - extract CSV-like structure from API data
        for form in selected_forms:
            try:
                # Get basic form info
                form_id = form.get('form_submission_id', '')
                if not form_id:
                    errors.append("Form missing form_submission_id")
                    continue
                
                # Get current revision for parsing
                current_revision = form.get('current_revision', {})
                responses = current_revision.get('responses', [])
                
                # Initialize all CSV fields
                csv_record = {
                    'form_submission_id': form_id,
                    'author_first': '',
                    'author_last': '',
                    'author_email': '',
                    'author_student_id': '',
                    'author_current_assignment': '',
                    'author_assignment_at_submission': '',
                    'submission_date_chicago': current_revision.get('date', ''),
                    'last_revised_by': '',
                    'last_revised_by_email': '',
                    'last_revised_date_chicago': '',
                    'hall': '',
                    'tag_other_staff': '',
                    'contact_info_organizer': '',
                    'event_name': '',
                    'event_date_start_time': '',
                    'event_end_time': '',
                    'specific_location': '',
                    'event_description': '',
                    'event_outline': '',
                    'target_audience': '',
                    'llc_sponsored_status': '',
                    'purchasing_items': False,
                    'purchasing_food': False,
                    'vendor_name': '',
                    'jp_morgan_location': '',
                    'funding_account': '',
                    'type_items_purchased': '',
                    'list_items_purchased': '',
                    'business_purpose': '',
                    'total_cost_vendor': None,
                    'total_cost_all': None,
                    'prize_receipts_needed': 0,
                    'receipt_acknowledgment': False,
                    'anticipated_attendance': 0,
                    'minors_attending': False,
                    'funds_requester': '',
                    'event_approval': '',
                    'supervisor_comments': '',
                    'event_attendance_tracking': '',
                    'total_attendees': None,
                    'assessment_summary': '',
                    # NEW FIELDS FROM COMPREHENSIVE MAPPING
                    'meeting_date_time': '',
                    'tag_rd_ca': '',
                    'estimated_meeting_cost': None,
                    'items_to_purchase': '',
                    'catering_order': '',
                    'total_expenses': None,
                    'staff_checking_out_keys': '',
                    'key_checkout_datetime': '',
                    'key_checkin_time': '',
                    'key_checkout_reason': '',
                    'lockout_resident_name': '',
                    'additional_phone_incidents': '',
                    'round_first_checklist': '',
                    'round_second_checklist': '',
                    'round_third_checklist': '',
                    'round_first_start_time': '',
                    'round_first_end_time': '',
                    'round_first_summary': '',
                    'round_second_start_time': '',
                    'round_second_end_time': '',
                    'round_second_summary': '',
                    'round_third_start_time': '',
                    'round_third_end_time': '',
                    'round_third_summary': '',
                    'duty_notes': '',
                    'duty_partner': '',
                    'evaluation_type': '',
                    'experience_rating': '',
                    'experience_justification': '',
                    'on_call_response': '',
                    'on_call_justification': '',
                    'role_model_rating': '',
                    'role_model_justification': '',
                    'community_development_rating': '',
                    'community_development_justification': '',
                    'goal_setting': '',
                    'returning_interest': '',
                    'meeting_attraction_plan': '',
                    'form_date': '',
                    # EXISTING SYSTEM FIELDS
                    'parsed_event_date': None,
                    'parsed_event_start_time': None,
                    'parsed_submission_date': None,
                    'semester': 'Academic Year 2025-2026',
                    'academic_year': '2025-2026',
                    'generated_by_user_id': created_by_user_id,
                    'form_responses': json.dumps(form),
                    'form_debug_info': json.dumps({
                        'processing_timestamp': datetime.now().isoformat(),
                        'responses_count': len(responses),
                        'form_template': form.get('form_template_name', '')
                    })
                }
                
                # Extract author info from revision
                author_name = current_revision.get('author', '')
                if author_name:
                    name_parts = author_name.split(' ', 1)
                    csv_record['author_first'] = name_parts[0] if len(name_parts) > 0 else ''
                    csv_record['author_last'] = name_parts[1] if len(name_parts) > 1 else ''
                
                # Extract key fields from form responses (matching CSV columns)
                for response in responses:
                    field_label = response.get('field_label', '').lower()
                    response_value = response.get('response')
                    
                    if not response_value:
                        continue
                        
                    # Map form fields to CSV columns
                    if 'name of event' in field_label:
                        csv_record['event_name'] = str(response_value)
                    elif 'date and event start time' in field_label:
                        csv_record['event_date_start_time'] = str(response_value)
                        # Try to parse the date
                        try:
                            event_datetime = datetime.fromisoformat(str(response_value).replace('Z', '+00:00'))
                            csv_record['parsed_event_date'] = event_datetime.date().isoformat()
                            csv_record['parsed_event_start_time'] = event_datetime.time().isoformat()
                        except:
                            pass
                    elif 'event end time' in field_label:
                        csv_record['event_end_time'] = str(response_value)
                    elif 'specific location' in field_label:
                        csv_record['specific_location'] = str(response_value)
                    elif 'description of event' in field_label:
                        csv_record['event_description'] = str(response_value)
                    elif 'outline of event' in field_label:
                        csv_record['event_outline'] = str(response_value)
                    elif 'hall' in field_label:
                        # Handle array response for hall
                        if isinstance(response_value, list):
                            hall_names = [item.get('tag_name', '') for item in response_value if isinstance(item, dict)]
                            csv_record['hall'] = ', '.join(hall_names)
                        else:
                            csv_record['hall'] = str(response_value)
                    elif 'target audience' in field_label:
                        # Handle array response for target audience
                        if isinstance(response_value, list):
                            audience_names = [item.get('tag_name', '') for item in response_value if isinstance(item, dict)]
                            csv_record['target_audience'] = ', '.join(audience_names)
                        else:
                            csv_record['target_audience'] = str(response_value)
                    elif 'llc sponsored' in field_label:
                        if isinstance(response_value, list):
                            llc_names = [item.get('tag_name', '') for item in response_value if isinstance(item, dict)]
                            csv_record['llc_sponsored_status'] = ', '.join(llc_names)
                        else:
                            csv_record['llc_sponsored_status'] = str(response_value)
                    elif 'anticipated number' in field_label and 'attend' in field_label:
                        try:
                            csv_record['anticipated_attendance'] = int(response_value)
                        except:
                            pass
                    elif 'purchasing items' in field_label:
                        csv_record['purchasing_items'] = str(response_value).lower() == 'yes'
                    elif 'purchasing food' in field_label:
                        csv_record['purchasing_food'] = str(response_value).lower() == 'yes'
                    elif 'vendor name' in field_label:
                        csv_record['vendor_name'] = str(response_value)
                    elif 'contact information' in field_label and 'organizer' in field_label:
                        csv_record['contact_info_organizer'] = str(response_value)
                    elif ('event approval' in field_label or 
                          'approval' in field_label or 
                          'event status' in field_label or
                          'status' in field_label and 'event' in field_label):
                        csv_record['event_approval'] = str(response_value)
                    elif 'supervisor' in field_label and ('comment' in field_label or 'revision' in field_label):
                        csv_record['supervisor_comments'] = str(response_value)
                    elif 'business purpose' in field_label:
                        csv_record['business_purpose'] = str(response_value)
                    elif 'total cost' in field_label and 'vendor' in field_label:
                        try:
                            csv_record['total_cost_vendor'] = float(response_value)
                        except:
                            pass
                    elif 'total cost' in field_label and ('all' in field_label or 'items' in field_label):
                        try:
                            csv_record['total_cost_all'] = float(response_value)
                        except:
                            pass
                    elif 'minors' in field_label and 'attending' in field_label:
                        csv_record['minors_attending'] = str(response_value).lower() == 'yes'
                    elif 'funds requester' in field_label or 'requesting funds' in field_label:
                        csv_record['funds_requester'] = str(response_value)
                    elif 'jp morgan' in field_label or 'purchasing card' in field_label:
                        csv_record['jp_morgan_location'] = str(response_value)
                    elif 'funding account' in field_label:
                        csv_record['funding_account'] = str(response_value)
                    elif 'items purchased' in field_label and 'type' in field_label:
                        csv_record['type_items_purchased'] = str(response_value)
                    elif 'items purchased' in field_label and 'list' in field_label:
                        csv_record['list_items_purchased'] = str(response_value)
                    elif 'receipt' in field_label and 'acknowledgment' in field_label:
                        csv_record['receipt_acknowledgment'] = str(response_value).lower() == 'yes'
                    elif 'total attendees' in field_label or 'number of attendees' in field_label:
                        try:
                            csv_record['total_attendees'] = int(response_value)
                        except:
                            pass
                    elif 'assessment summary' in field_label:
                        csv_record['assessment_summary'] = str(response_value)
                    
                    # NEW COMPREHENSIVE FIELD MAPPING FOR ALL UNMAPPED FIELDS
                    elif 'date and time of meeting' in field_label:
                        csv_record['meeting_date_time'] = str(response_value)
                    elif 'tag your rd & ca' in field_label or 'tag your rd and ca' in field_label:
                        csv_record['tag_rd_ca'] = str(response_value)
                    elif 'estimated cost of items for meeting' in field_label:
                        try:
                            csv_record['estimated_meeting_cost'] = float(response_value) if str(response_value) != '0' else None
                        except:
                            pass
                    elif 'items to purchase' in field_label and 'meeting' in field_label:
                        csv_record['items_to_purchase'] = str(response_value)
                    elif 'catering order' in field_label:
                        csv_record['catering_order'] = str(response_value)
                    elif 'total expenses' in field_label:
                        try:
                            csv_record['total_expenses'] = float(response_value) if str(response_value) != '0' else None
                        except:
                            pass
                    elif 'name of staff person' in field_label and 'checking out' in field_label:
                        csv_record['staff_checking_out_keys'] = str(response_value)
                    elif 'checked out - date and time' in field_label:
                        csv_record['key_checkout_datetime'] = str(response_value)
                    elif 'checked in - time' in field_label:
                        csv_record['key_checkin_time'] = str(response_value)
                    elif 'reason for checking out keys' in field_label:
                        csv_record['key_checkout_reason'] = str(response_value)
                    elif 'assisting with a lockout' in field_label and 'resident' in field_label:
                        csv_record['lockout_resident_name'] = str(response_value)
                    elif 'additional information' in field_label and 'phone calls' in field_label:
                        csv_record['additional_phone_incidents'] = str(response_value)
                    elif 'round checklist' in field_label and 'first round' in field_label:
                        csv_record['round_first_checklist'] = str(response_value)
                    elif 'round checklist' in field_label and 'second round' in field_label:
                        csv_record['round_second_checklist'] = str(response_value)
                    elif 'round checklist' in field_label and 'third round' in field_label:
                        csv_record['round_third_checklist'] = str(response_value)
                    elif 'started my first round at' in field_label:
                        csv_record['round_first_start_time'] = str(response_value)
                    elif 'ended my first round at' in field_label:
                        csv_record['round_first_end_time'] = str(response_value)
                    elif 'round summary' in field_label and 'first round' in field_label:
                        csv_record['round_first_summary'] = str(response_value)
                    elif 'started my second round at' in field_label:
                        csv_record['round_second_start_time'] = str(response_value)
                    elif 'ended my second round at' in field_label:
                        csv_record['round_second_end_time'] = str(response_value)
                    elif 'round summary' in field_label and 'second round' in field_label:
                        csv_record['round_second_summary'] = str(response_value)
                    elif 'started my third round at' in field_label:
                        csv_record['round_third_start_time'] = str(response_value)
                    elif 'ended my third round at' in field_label:
                        csv_record['round_third_end_time'] = str(response_value)
                    elif 'round summary' in field_label and 'third round' in field_label:
                        csv_record['round_third_summary'] = str(response_value)
                    elif 'duty notes' in field_label:
                        csv_record['duty_notes'] = str(response_value)
                    elif 'duty partner' in field_label:
                        csv_record['duty_partner'] = str(response_value)
                    elif 'evaluation type' in field_label:
                        csv_record['evaluation_type'] = str(response_value)
                    elif field_label == 'experience ' or field_label == 'experience':
                        csv_record['experience_rating'] = str(response_value)
                    elif 'experience rating justification' in field_label:
                        csv_record['experience_justification'] = str(response_value)
                    elif 'on call response' in field_label:
                        csv_record['on_call_response'] = str(response_value)
                    elif 'on call rating justification' in field_label:
                        csv_record['on_call_justification'] = str(response_value)
                    elif 'role model' in field_label and 'justification' not in field_label:
                        csv_record['role_model_rating'] = str(response_value)
                    elif 'role model rating justification' in field_label:
                        csv_record['role_model_justification'] = str(response_value)
                    elif 'community development' in field_label and 'justification' not in field_label:
                        csv_record['community_development_rating'] = str(response_value)
                    elif 'community development rating justification' in field_label:
                        csv_record['community_development_justification'] = str(response_value)
                    elif 'goal setting' in field_label:
                        csv_record['goal_setting'] = str(response_value)
                    elif 'returning to the ra position' in field_label:
                        csv_record['returning_interest'] = str(response_value)
                    elif 'attract residents to the meeting' in field_label:
                        csv_record['meeting_attraction_plan'] = str(response_value)
                    elif field_label == 'date' and 'time' not in field_label:
                        csv_record['form_date'] = str(response_value)
                
                # Parse submission date
                try:
                    if csv_record['submission_date_chicago']:
                        submission_dt = datetime.fromisoformat(csv_record['submission_date_chicago'].replace('Z', '+00:00'))
                        csv_record['parsed_submission_date'] = submission_dt.isoformat()
                except:
                    pass
                
                # Store data in database - try insert first, then update if exists
                try:
                    # Try insert first
                    result = supabase.table("engagement_report_data").insert(csv_record).execute()
                    
                    if result.data:
                        total_saved += 1
                        event_display_name = csv_record.get('event_name', f"Event {form_id}")
                        st.success(f"✅ Inserted: {event_display_name} (ID: {form_id})")
                    else:
                        errors.append(f"Database insert failed for {form_id}")
                        
                except Exception as insert_error:
                    # If insert failed due to duplicate, try update
                    if "duplicate key" in str(insert_error).lower() or "unique constraint" in str(insert_error).lower():
                        try:
                            # Update existing record
                            csv_record['last_updated'] = datetime.now().isoformat()
                            update_result = supabase.table("engagement_report_data").update(
                                csv_record
                            ).eq("form_submission_id", form_id).execute()
                            
                            if update_result.data:
                                total_saved += 1
                                event_display_name = csv_record.get('event_name', f"Event {form_id}")
                                st.success(f"✅ Updated: {event_display_name} (ID: {form_id})")
                            else:
                                errors.append(f"Database update failed for {form_id}")
                                
                        except Exception as update_error:
                            errors.append(f"Failed to update {form_id}: {update_error}")
                            st.error(f"❌ Update failed for {form_id}")
                    else:
                        # Re-raise if it's not a duplicate key error
                        raise insert_error
                        
            except Exception as e:
                error_msg = str(e)
                event_name = csv_record.get('event_name', 'Unknown') if 'csv_record' in locals() else 'Unknown'
                
                # Log the full error for debugging
                st.error(f"❌ Error processing {event_name}: {error_msg}")
                errors.append(f"Error processing {event_name}: {error_msg}")
                
                # Don't count database errors as "skipped duplicates" - they're actual errors
        
        # Prepare comprehensive result message
        result_messages = []
        
        if total_saved > 0:
            result_messages.append(f"✅ Processed {total_saved} events")
        
        if skipped_count > 0:
            result_messages.append(f"⏭️ Skipped {skipped_count} duplicates")
        
        if errors:
            result_messages.append(f"❌ {len(errors)} errors occurred")
        
        # Simple statistics
        total_processed = total_saved + skipped_count
        stats_msg = f"Academic Year 2025-2026: Processed {total_processed} events total"
        
        # Create simple semester statistics for compatibility
        simple_stats = {
            'approved_events': 0,  # Will be calculated by database generated column
            'pending_events': total_saved,  # Assume pending until approval status is set
            'cancelled_events': 0
        }
        
        return {
            "success": total_saved > 0,
            "message": " | ".join(result_messages) if result_messages else "No events processed",
            "detailed_message": stats_msg,
            "semester_statistics": simple_stats,
            "records_created": total_saved,
            "records_updated": 0,  # We're using upsert now, so no separate tracking
            "records_skipped": skipped_count,
            "errors": errors
        }
        
    except Exception as e:
        return {
            "success": False, 
            "message": f"Error saving engagement data: {str(e)}",
            "error_details": str(e)
        }

def save_engagement_analysis(analysis_data, week_ending_date, created_by_user_id=None):
    """Save an engagement analysis report to the database for permanent storage"""
    try:
        # Determine report type
        report_type = "weekly_summary" if analysis_data['report_type'] == "📅 Weekly Summary Report" else "standard_analysis"
        
        # Handle date conversions for database storage
        start_date = analysis_data['filter_info']['start_date']
        end_date = analysis_data['filter_info']['end_date']
        
        # Convert to ISO format strings if they're date objects
        if hasattr(start_date, 'isoformat'):
            start_date = start_date.isoformat()
        if hasattr(end_date, 'isoformat'):
            end_date = end_date.isoformat()
        
        # Extract upcoming events if available
        upcoming_events = extract_upcoming_events(analysis_data['selected_forms'])
        
        # Prepare data for saving
        save_data = {
            'week_ending_date': week_ending_date,
            'report_type': report_type,
            'date_range_start': start_date,
            'date_range_end': end_date,
            'events_analyzed': len(analysis_data['selected_forms']),
            'total_selected': len(analysis_data.get('all_selected_forms', analysis_data['selected_forms'])),
            'analysis_text': analysis_data['summary'],
            'upcoming_events': upcoming_events,
            'created_by': created_by_user_id,
            'updated_at': datetime.now().isoformat()
        }
        
        # Save to database with graceful error handling
        try:
            # Try simple insert first
            response = supabase.table("saved_engagement_analyses").insert(save_data).execute()
            
            if response.data:
                return {
                    "success": True, 
                    "message": f"Engagement analysis saved for week ending {week_ending_date}",
                    "saved_id": response.data[0]['id']
                }
            else:
                return {"success": False, "message": "Failed to save engagement analysis"}
                
        except Exception as e:
            error_msg = str(e)
            
            # Check if it's a table doesn't exist error
            if "does not exist" in error_msg or "relation" in error_msg:
                return {
                    "success": False, 
                    "message": "Database tables not found. Please run the database schema setup first. See database_schema_engagement_reports.sql"
                }
            # Check if it's a duplicate key error
            elif "duplicate key" in error_msg or "already exists" in error_msg:
                return {
                    "success": True,
                    "message": f"Analysis for week ending {week_ending_date} already exists (no duplicate created)"
                }
            else:
                return {"success": False, "message": f"Database error: {error_msg}"}
            
    except Exception as e:
        return {"success": False, "message": f"Error saving engagement analysis: {str(e)}"}

def extract_upcoming_events(selected_forms):
    """Extract a formatted list of upcoming events from engagement forms"""
    try:
        upcoming_events = []
        current_date = datetime.now().date()
        
        for form in selected_forms:
            current_revision = form.get('current_revision', {})
            responses = current_revision.get('responses', [])
            
            event_info = {
                'title': 'Event',
                'date': None,
                'location': 'TBD',
                'organizer': current_revision.get('author', 'Unknown')
            }
            
            # Extract event details
            for response in responses:
                field_label = response.get('field_label', '').lower()
                field_response = str(response.get('response', '')).strip()
                
                if field_response and field_response != 'None':
                    if any(word in field_label for word in ['title', 'name', 'event']):
                        event_info['title'] = field_response
                    elif any(word in field_label for word in ['date', 'when', 'scheduled']):
                        try:
                            # Try to parse date and check if it's in the future
                            for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y']:
                                try:
                                    event_date = datetime.strptime(field_response, date_format).date()
                                    if event_date >= current_date:
                                        event_info['date'] = event_date
                                    break
                                except:
                                    continue
                        except:
                            pass
                    elif any(word in field_label for word in ['location', 'where', 'hall']):
                        event_info['location'] = field_response
            
            # Only include events with future dates
            if event_info['date'] and event_info['date'] >= current_date:
                upcoming_events.append(event_info)
        
        # Sort by date and format for display
        upcoming_events.sort(key=lambda x: x['date'])
        
        if upcoming_events:
            formatted_events = "## Upcoming Events\n\n"
            for event in upcoming_events[:10]:  # Limit to 10 events
                formatted_events += f"- **{event['title']}** - {event['date'].strftime('%B %d, %Y')} at {event['location']} (Organizer: {event['organizer']})\n"
            return formatted_events
        else:
            return "## Upcoming Events\n\nNo upcoming events found in the analyzed submissions.\n"
            
    except Exception as e:
        return f"## Upcoming Events\n\nError extracting upcoming events: {str(e)}\n"

# --- User Authentication & Profile Functions ---
def login_form():
    st.header("Login")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        if submit:
            try:
                user_session = supabase.auth.sign_in_with_password({"email": email, "password": password})
                if getattr(user_session, "user", None):
                    st.session_state["user"] = user_session.user
                    st.rerun()
                else:
                    st.error("Login failed. Please check your credentials.")
            except Exception:
                st.error("Login failed: Invalid login credentials or unconfirmed email.")


def signup_form():
    st.header("Create a New Account")
    with st.form("signup"):
        email = st.text_input("Email")
        full_name = st.text_input("Full Name")
        title = st.text_input("Position Title")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Create Account")
        if submit:
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})
                if getattr(res, "user", None):
                    new_user_id = res.user.id
                    supabase.table("profiles").update({"full_name": full_name, "title": title}).eq("id", new_user_id).execute()
                    st.success("Signup successful! Please check your email to confirm your account.")
                else:
                    st.error("Signup failed. A user may already exist with this email.")
            except Exception as e:
                if "already registered" in str(e):
                    st.error("This email address is already registered. Please try logging in.")
                else:
                    st.error(f"An error occurred during signup: {e}")


def logout():
    keys_to_delete = ["user", "role", "title", "full_name", "last_summary", "report_to_edit", "draft_report", "is_supervisor"]
    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key]
    clear_form_state()

# --- Page Definitions ---
def profile_page():
    st.title("My Profile")
    st.write(f"**Email:** {st.session_state['user'].email}")
    st.write(f"**Role:** {st.session_state.get('role', 'N/A')}")
    with st.form("update_profile"):
        current_name = st.session_state.get("full_name", "")
        new_name = st.text_input("Full Name", value=current_name)
        current_title = st.session_state.get("title", "")
        new_title = st.text_input("Position Title", value=current_title)
        submitted = st.form_submit_button("Update Profile")
        if submitted:
            try:
                user_id = st.session_state["user"].id
                update_data = {"full_name": new_name, "title": new_title}
                supabase.table("profiles").update(update_data).eq("id", user_id).execute()
                st.session_state["full_name"] = new_name
                st.session_state["title"] = new_title
                st.success("Profile updated successfully!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"An error occurred: {e}")


def submit_and_edit_page():
    st.title("Submit / Edit Report")

    def show_report_list():
        st.subheader("Your Submitted Reports")
        user_id = st.session_state["user"].id
        user_reports_response = supabase.table("reports").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        user_reports = getattr(user_reports_response, "data", None) or []
        
        # Check for any draft reports that were previously finalized (unlocked by admin)
        unlocked_reports = [r for r in user_reports if r.get("status") == "draft" and r.get("individual_summary")]
        admin_created_reports = [r for r in user_reports if r.get("status") == "admin_created"]
        
        if unlocked_reports:
            st.info(f"📢 **Notice:** {len(unlocked_reports)} of your previously submitted reports have been unlocked by an administrator for editing. You can now make changes and resubmit them.")
        
        if admin_created_reports:
            st.warning(f"⏰ **Missed Deadline:** {len(admin_created_reports)} report(s) were created by an administrator because you missed the deadline. Please complete and submit them as soon as possible.")

        now = datetime.now(ZoneInfo("America/Chicago"))
        deadline_info = calculate_deadline_info(now)
        
        active_saturday = deadline_info["active_saturday"]
        is_grace_period = deadline_info["is_grace_period"]
        deadline_is_past = deadline_info["deadline_passed"]
        deadline_config = deadline_info["config"]

        if active_saturday:
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
                if st.button(button_label, use_container_width=True, type="primary"):
                    clear_form_state()
                    existing_report = next((r for r in user_reports if r.get("week_ending_date") == active_report_date_str), None)
                    st.session_state["report_to_edit"] = existing_report if existing_report else {"week_ending_date": active_report_date_str}
                    st.rerun()
            elif has_finalized_for_active_week:
                st.info(f"You have already finalized your report for the week ending {active_saturday.strftime('%m/%d/%Y')}.")
            elif deadline_is_past:
                deadline_day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][deadline_config["day_of_week"]]
                st.warning(f"The submission deadline ({deadline_day_name} at {deadline_config['hour']:02d}:{deadline_config['minute']:02d}) for the report ending {active_saturday.strftime('%m/%d/%Y')} has passed. Contact your administrator if you need to submit a report.")

        # Option to create reports for previous weeks
        st.divider()
        st.markdown("##### Create Report for Previous Week")
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info("💡 Need to submit a report for a previous week? Select any Saturday (week ending date) below.")
        with col2:
            if st.button("📝 Create Previous Week Report", use_container_width=True):
                # Calculate previous Saturdays as options
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
        for report in user_reports:
            status = (report.get("status") or "draft").capitalize()
            with st.expander(f"Report for week ending {report.get('week_ending_date','Unknown')} (Status: {status})"):
                if report.get("individual_summary"):
                    st.info(f"**Your AI-Generated Summary:**\n\n{clean_summary_response(report.get('individual_summary'))}")
                report_body = report.get("report_body") or {}
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
                st.write(report.get("professional_development", ""))
                st.markdown("**Lookahead:**")
                st.write(report.get("key_topics_lookahead", ""))
                st.markdown("**Personal Check-in Details:**")
                st.write(report.get("personal_check_in", ""))
                # Only show Director concerns to admins or the report owner
                if report.get('director_concerns'):
                    viewer_role = st.session_state.get('role')
                    viewer_id = st.session_state['user'].id
                    report_owner_id = report.get('user_id')
                    if viewer_role == 'admin' or report_owner_id == viewer_id:
                        st.warning(f"**Concerns for Director:** {report.get('director_concerns')}")

                if status.lower() != "finalized":
                    if st.button("Edit This Report", key=f"edit_{report.get('id')}", use_container_width=True):
                        st.session_state["report_to_edit"] = report
                        st.rerun()

    @st.cache_data
    def process_report_with_ai(items_to_categorize):
        if not items_to_categorize:
            return None
        
        try:
            model = genai.GenerativeModel("models/gemini-2.5-pro")
            ascend_list = ", ".join(ASCEND_VALUES)
            north_list = ", ".join(NORTH_VALUES)
            items_json = json.dumps(items_to_categorize)
            prompt = f"""
            You are an expert AI assistant for a university housing department. Your task is to perform two actions on a list of weekly activities including campus events and committee participation:
            1. Categorize each activity with one ASCEND and one Guiding NORTH category.
            2. Generate a concise 2-4 sentence individual summary that includes mention of campus engagement and its alignment with frameworks.
            
            ASCEND Categories: {ascend_list}
            Guiding NORTH Categories: {north_list}

            For campus events/committee participation, consider how attendance demonstrates:
            - Community engagement and service (Community, Service)
            - Professional development and learning (Development, Excellence)
            - Supporting university initiatives (Accountability, Nurturing)
            - Building relationships with stakeholders (Service, Transformative)

            Also consider UND LEADS alignment in your summary:
            - Learning: Training, workshops, skill development, educational activities
            - Equity: Diversity events, inclusion initiatives, accessibility work
            - Affinity: Networking, relationship building, team activities, community engagement
            - Discovery: Innovation projects, research, exploring new methods, creative solutions
            - Service: Volunteer work, helping others, community service, supporting university goals

            Input JSON: {items_json}

            CRITICAL: You must categorize EVERY item from the input. Return exactly {len(items_to_categorize)} categorized items.

            Return valid JSON like:
            {{
              "categorized_items":[{{"id":0,"ascend_category":"Community","north_category":"Nurturing Student Success & Development"}}],
              "individual_summary":"This week showed strong alignment with both ASCEND and NORTH frameworks through various activities and campus engagement. The work also demonstrates UND LEADS values through learning opportunities and service to the community..."
            }}
            """
            
            # Try up to 3 times with different strategies
            for attempt in range(3):
                try:
                    response = model.generate_content(prompt)
                    clean_response = response.text.strip().replace("```json", "").replace("```", "")
                    result = json.loads(clean_response)
                    
                    # Validate the response
                    if (result and 
                        "categorized_items" in result and 
                        "individual_summary" in result and
                        isinstance(result["categorized_items"], list) and
                        len(result["categorized_items"]) >= len(items_to_categorize) * 0.8):  # Allow 80% match
                        
                        # Ensure we have categories for all items
                        categorized_ids = {item.get("id") for item in result["categorized_items"]}
                        missing_ids = [item["id"] for item in items_to_categorize if item["id"] not in categorized_ids]
                        
                        # Add default categories for missing items
                        for missing_id in missing_ids:
                            missing_item = next(item for item in items_to_categorize if item["id"] == missing_id)
                            default_category = {
                                "id": missing_id,
                                "ascend_category": "Development",  # Safe default
                                "north_category": "Nurturing Student Success & Development"  # Safe default
                            }
                            result["categorized_items"].append(default_category)
                        
                        return result
                        
                except json.JSONDecodeError as je:
                    if attempt == 2:  # Last attempt
                        st.warning(f"AI response parsing failed after {attempt + 1} attempts. Using fallback categorization.")
                        break
                    continue
                except Exception as e:
                    if attempt == 2:  # Last attempt
                        st.warning(f"AI processing failed after {attempt + 1} attempts: {str(e)}")
                        break
                    continue
            
            # Fallback: Create default categorization
            fallback_result = {
                "categorized_items": [
                    {
                        "id": item["id"],
                        "ascend_category": "Development",
                        "north_category": "Nurturing Student Success & Development"
                    } for item in items_to_categorize
                ],
                "individual_summary": "This week demonstrated continued professional development and engagement with various activities that support student success and departmental goals."
            }
            
            st.info("ℹ️ AI categorization used fallback defaults. You can manually review and adjust categories if needed.")
            return fallback_result
            
        except Exception as e:
            st.error(f"An AI error occurred during processing: {e}")
            return None

    def dynamic_entry_section(section_key, section_label, report_data):
        st.subheader(section_label)
        
        # Special handling for events section
        if section_key == "events":
            # Initialize events count if not exists
            if "events_count" not in st.session_state:
                existing_events = report_data.get("events", {}).get("successes", [])
                st.session_state["events_count"] = len(existing_events) if existing_events else 1
            
            # Display event entry fields
            for i in range(st.session_state["events_count"]):
                col1, col2 = st.columns([2, 1])
                default_event_name = ""
                default_event_date = datetime.now().date()
                
                # Load existing event data if editing - parse from text format
                existing_events = report_data.get("events", {}).get("successes", [])
                if i < len(existing_events):
                    event_text = existing_events[i].get("text", "")
                    # Try to parse "EventName on YYYY-MM-DD" format
                    if " on " in event_text:
                        parts = event_text.rsplit(" on ", 1)
                        if len(parts) == 2:
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
            # Regular successes/challenges format for other sections
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

    def show_submission_form():
        report_data = st.session_state["report_to_edit"]
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
                    supabase.table("reports").upsert(draft_data, on_conflict="user_id, week_ending_date").execute()
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
            col1, col2 = st.columns([3, 1])
            with col2:
                finalize_button = st.form_submit_button("Lock and Submit Report", type="primary", use_container_width=True)

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
                    "submitted_at": datetime.now(ZoneInfo("America/Chicago")).isoformat(),
                }

                try:
                    supabase.table("reports").upsert(final_data, on_conflict="user_id, week_ending_date").execute()
                    st.success("✅ Your final report has been saved successfully!")
                    is_update = bool(draft.get("report_id"))
                    if is_update:
                        supabase.table("weekly_summaries").delete().eq("week_ending_date", draft.get("week_ending_date")).execute()
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


def dashboard_page(supervisor_mode=False):
    # Ensure we always have the current user's id available (used for RPC/save logic)
    current_user_id = st.session_state['user'].id

    if supervisor_mode:
        st.title("Supervisor Dashboard")
        st.write("View your team's reports, track submissions, and generate weekly summaries.")

        # Get the direct reports (defensive)
        direct_reports_response = supabase.table("profiles").select("id, full_name, title").eq("supervisor_id", current_user_id).execute()
        direct_reports = getattr(direct_reports_response, "data", None) or []
        direct_report_ids = [u.get("id") for u in direct_reports if u.get("id")]

        st.caption(f"Found {len(direct_report_ids)} direct report(s).")
        if direct_reports:
            names = ", ".join([dr.get("full_name") or dr.get("title") or dr.get("id") for dr in direct_reports])
            st.write("Direct reports:", names)

        if not direct_report_ids:
            st.info("You do not have any direct reports assigned in the system.")
            return

        # Use RPC to fetch finalized reports for this supervisor (works with RLS)
        rpc_resp = supabase.rpc('get_finalized_reports_for_supervisor', {'sup_id': current_user_id}).execute()
        all_reports = rpc_resp.data or []

        st.caption(f"Found {len(all_reports)} finalized report(s) for your direct reports.")

        # Get staff records for display (only the supervisor's direct reports)
        all_staff_response = supabase.table('profiles').select('*').in_('id', direct_report_ids).execute()
        all_staff = getattr(all_staff_response, "data", None) or []

    else:
        st.title("Admin Dashboard")
        st.write("View reports, track submissions, and generate weekly summaries.")
        reports_response = supabase.table("reports").select("*").eq("status", "finalized").order("created_at", desc=True).execute()
        all_reports = getattr(reports_response, "data", None) or []
        all_staff_response = supabase.rpc("get_all_staff_profiles").execute()
        all_staff = getattr(all_staff_response, "data", None) or []

    if not all_reports:
        st.info("No finalized reports have been submitted yet.")
        return

    # Normalize week_ending_date values to ISO 'YYYY-MM-DD' so comparisons are consistent
    normalized_reports = []
    for r in all_reports:
        raw_week = r.get('week_ending_date')
        try:
            norm_week = pd.to_datetime(raw_week).date().isoformat()
        except Exception:
            norm_week = str(raw_week)
        r['_normalized_week'] = norm_week
        normalized_reports.append(r)

    st.caption(f"Found {len(normalized_reports)} finalized report(s) for this view.")

    all_dates = [r['_normalized_week'] for r in normalized_reports]
    unique_dates = sorted(list(set(all_dates)), reverse=True)

    st.divider()
    st.subheader("Weekly Submission Status (Finalized Reports)")
    selected_date_for_status = st.selectbox("Select a week to check status:", options=unique_dates)
    if selected_date_for_status and all_staff_response.data:
        # If supervisor_mode, use the reports we already fetched (RPC) to avoid RLS blocking a direct query.
        if supervisor_mode:
            submitted_user_ids = {r['user_id'] for r in normalized_reports if r.get('_normalized_week') == selected_date_for_status}
        else:
            submitted_response = supabase.table('reports').select('user_id').eq('week_ending_date', selected_date_for_status).eq('status', 'finalized').execute()
            submitted_user_ids = {item['user_id'] for item in submitted_response.data} if submitted_response.data else set()
        all_staff = all_staff_response.data; submitted_staff, missing_staff = [], []
        for staff_member in all_staff:
            name = staff_member.get("full_name") or staff_member.get("email") or staff_member.get("id")
            title = staff_member.get("title")
            display_info = f"{name} ({title})" if title else name
            if staff_member.get("id") in submitted_user_ids:
                submitted_staff.append(display_info)
            else:
                missing_staff.append(display_info)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"#### ✅ Submitted ({len(submitted_staff)})")
            for person in sorted(submitted_staff):
                st.markdown(f"- {person}")
        with col2:
            st.markdown(f"#### ❌ Missing ({len(missing_staff)})")
            for person in sorted(missing_staff):
                st.markdown(f"- {person}")

    st.divider()
    # Fetch saved summaries including creator info
    summaries_response = supabase.table('weekly_summaries').select('week_ending_date, summary_text, created_by').execute()
    # Map week -> (text, created_by)
    saved_summaries_raw = {s['week_ending_date']: (s['summary_text'], s.get('created_by')) for s in (summaries_response.data or [])}

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
        # Fetch ALL reports to get comprehensive date list
        all_reports_response = supabase.table("reports").select("*").order("created_at", desc=True).execute()
        all_reports_comprehensive = getattr(all_reports_response, "data", None) or []
        
        # Use all report dates, not just those visible in current view
        all_report_dates = [r.get("week_ending_date") for r in all_reports_comprehensive if r.get("week_ending_date")]
        all_unique_dates = sorted(list(set(all_report_dates)), reverse=True)
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
                                supabase.table("reports").update({"status": "draft"}).eq("id", report.get('id')).execute()
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
                            supabase.table("reports").update({"status": "draft"}).eq("week_ending_date", unlock_week).eq("status", "finalized").execute()
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
        all_reports_response = supabase.table("reports").select("*").order("created_at", desc=True).execute()
        all_reports_including_drafts = getattr(all_reports_response, "data", None) or []
        
        st.caption(f"Debug: Found {len(all_reports_including_drafts)} total reports (all statuses)")
        
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
            deadline_info = calculate_deadline_info(draft_unlock_week)
            deadline_passed = deadline_info["deadline_passed"]
            
            # Get draft reports for this week
            draft_reports = [r for r in all_reports_including_drafts if r.get("week_ending_date") == draft_unlock_week and r.get("status") == "draft"]
            
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
                                        "admin_note": f"Submission enabled by administrator after deadline. Enabled on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
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
                                    "admin_note": f"Submission enabled by administrator after deadline. Bulk enabled on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
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
        deadline_config = get_deadline_settings()
        
        # Get all unique dates from all reports for missed deadline management
        all_report_dates = [r.get("week_ending_date") for r in all_reports if r.get("week_ending_date")]
        all_unique_dates = sorted(list(set(all_report_dates)), reverse=True)
        missed_week = st.selectbox("Select week with missed deadlines:", options=all_unique_dates, key="missed_deadline_week")
        
        if missed_week:
            # Get all staff and check who hasn't submitted or has non-finalized reports
            all_staff_ids = [staff.get("id") for staff in all_staff]
            # Check for any existing reports (not just finalized ones)
            success, reports_data, error = safe_db_query(
                supabase.table("reports").select("user_id, status").eq("week_ending_date", missed_week),
                f"Checking reports for week {missed_week}"
            )
            
            if success:
                existing_user_ids = {r['user_id'] for r in reports_data}
                finalized_user_ids = {r['user_id'] for r in reports_data if r.get('status') == 'finalized'}
            else:
                st.error(f"❌ {error}")
                st.info("🔄 Please refresh the page and try again.")
                return  # Exit the function if we can't get the data
            
            # Staff who need attention: no report at all OR have non-finalized reports
            missing_staff = [staff for staff in all_staff if staff.get("id") not in finalized_user_ids]
            
            if missing_staff:
                finalized_count = len(finalized_user_ids)
                total_staff = len(all_staff)
                st.write(f"**{len(missing_staff)} staff member(s) need attention for week ending {missed_week}** ({finalized_count}/{total_staff} finalized):")
                
                for staff in missing_staff:
                    col1, col2, col3 = st.columns([3, 2, 2])
                    
                    with col1:
                        staff_name = staff.get("full_name") or staff.get("title") or staff.get("email", "Unknown")
                        st.write(f"**{staff_name}**")
                    
                    with col2:
                        st.write(staff.get("title", "No title"))
                    
                    with col3:
                        # Check if report already exists for this user and week
                        success, reports_data, error = safe_db_query(
                            supabase.table("reports").select("*").eq("user_id", staff.get("id")).eq("week_ending_date", missed_week),
                            f"Checking existing report for {staff.get('full_name', 'user')}"
                        )
                        
                        if success:
                            existing_report = reports_data[0] if reports_data else None
                        else:
                            st.error(f"❌ {error}")
                            st.info("🔄 Please refresh the page and try again.")
                            existing_report = None
                        
                        if existing_report:
                            # Report exists - offer to unlock or update it
                            current_status = existing_report.get("status", "draft")
                            if current_status == "finalized":
                                if st.button("� Unlock Report", key=f"unlock_{staff.get('id')}_{missed_week}", help="Unlock this finalized report for editing"):
                                    try:
                                        supabase.table("reports").update({
                                            "status": "unlocked",
                                            "admin_note": f"Report unlocked by administrator for editing. Unlocked on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
                                        }).eq("id", existing_report["id"]).execute()
                                        st.success(f"Report unlocked for {staff_name}. They can now edit and resubmit it.")
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to unlock report: {e}")
                            else:
                                st.write(f"📝 Report exists ({current_status})")
                        else:
                            # No report exists - offer to create one
                            if st.button("�📝 Create Report", key=f"create_{staff.get('id')}_{missed_week}", help="Create empty report for this staff member"):
                                try:
                                    # Create a basic report template for the staff member
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
                                        "status": "admin_created",
                                        "created_by_admin": st.session_state["user"].id,
                                        "admin_note": f"Report created by administrator due to missed deadline. Created on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
                                    }
                                    
                                    supabase.table("reports").insert(empty_report).execute()
                                    st.success(f"Empty report created for {staff_name}. They can now edit and submit it.")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to create report: {e}")
                
                # Bulk create option
                truly_missing_staff = []
                for staff in missing_staff:
                    existing_check = supabase.table("reports").select("id").eq("user_id", staff.get("id")).eq("week_ending_date", missed_week).execute()
                    if not existing_check.data:
                        truly_missing_staff.append(staff)
                
                if len(truly_missing_staff) > 1:
                    st.divider()
                    if st.button(f"📝 Create Empty Reports for All {len(truly_missing_staff)} Staff (No Existing Reports)", type="secondary"):
                        try:
                            bulk_reports = []
                            created_count = 0
                            for staff in truly_missing_staff:
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
                                    "status": "admin_created",
                                    "created_by_admin": st.session_state["user"].id,
                                    "admin_note": f"Report created by administrator due to missed deadline. Created on {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')}"
                                }
                                bulk_reports.append(empty_report)
                            
                            if bulk_reports:
                                supabase.table("reports").insert(bulk_reports).execute()
                                st.success(f"Empty reports created for {len(bulk_reports)} staff members!")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.info("No reports to create - all staff already have reports for this week.")
                        except Exception as e:
                            st.error(f"Failed to create bulk reports: {e}")
            else:
                st.success("✅ All staff have submitted reports for this week!")

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
                weekly_reports = [r for r in all_reports if r.get("week_ending_date") == selected_date_for_summary]
                if not weekly_reports:
                    st.warning("No reports found for the selected week.")
                else:
                    well_being_scores = [r.get("well_being_rating") for r in weekly_reports if r.get("well_being_rating") is not None]
                    average_score = round(sum(well_being_scores) / len(well_being_scores), 1) if well_being_scores else "N/A"
                    reports_text = ""
                    all_events_summary = []  # Collect all events for admin summary
                    
                    for r in weekly_reports:
                        reports_text += f"\n---\n**Report from: {r.get('team_member','Unknown')}**\n"
                        reports_text += f"Well-being Score: {r.get('well_being_rating')}/5\n"
                        reports_text += f"Personal Check-in: {r.get('personal_check_in')}\n"
                        reports_text += f"Lookahead: {r.get('key_topics_lookahead')}\n"
                        if not supervisor_mode:
                            reports_text += f"Concerns for Director: {r.get('director_concerns')}\n"
                        

                        
                        report_body = r.get("report_body") or {}
                        for sk, sn in CORE_SECTIONS.items():
                            section_data = report_body.get(sk)
                            if section_data and (section_data.get("successes") or section_data.get("challenges")):
                                reports_text += f"\n*{sn}*:\n"
                                if section_data.get("successes"):
                                    for success in section_data["successes"]:
                                        reports_text += f"- Success: {success.get('text')} `(ASCEND: {success.get('ascend_category','N/A')}, NORTH: {success.get('north_category','N/A')})`\n"
                                        # If this is the events section, also collect for summary
                                        if sk == "events":
                                            # Parse event text to extract name and date
                                            event_text = success.get('text', '')
                                            event_name = event_text
                                            event_date = ""
                                            
                                            if " on " in event_text:
                                                parts = event_text.rsplit(" on ", 1)
                                                if len(parts) == 2:
                                                    event_name = parts[0]
                                                    event_date = parts[1]
                                            
                                            all_events_summary.append({
                                                "event_name": event_name,
                                                "event_date": event_date,
                                                "attendee": r.get('team_member', 'Unknown'),
                                                "ascend_category": success.get('ascend_category', 'N/A'),
                                                "north_category": success.get('north_category', 'N/A'),
                                                "alignment": f"ASCEND: {success.get('ascend_category', 'N/A')}, NORTH: {success.get('north_category', 'N/A')}"
                                            })
                                if section_data.get("challenges"):
                                    for challenge in section_data["challenges"]:
                                        reports_text += f"- Challenge: {challenge.get('text')} `(ASCEND: {challenge.get('ascend_category','N/A')}, NORTH: {challenge.get('north_category','N/A')})`\n"

                    director_section = ""
                    if not supervisor_mode:
                        director_section = """
- **### For the Director's Attention:** Create this section. List any items specifically noted under "Concerns for Director," making sure to mention which staff member raised the concern. If no concerns were raised, state "No specific concerns were raised for the Director this week."
"""

                    # Check for saved weekly duty reports to integrate
                    duty_reports_section = ""
                    if 'weekly_duty_reports' in st.session_state and st.session_state['weekly_duty_reports']:
                        st.info("🛡️ **Including Weekly Duty Reports:** Found saved duty analysis reports to integrate into this summary.")
                        duty_reports_section = "\n\n=== WEEKLY DUTY REPORTS INTEGRATION ===\n"
                        for i, duty_report in enumerate(st.session_state['weekly_duty_reports'], 1):
                            duty_reports_section += f"\n--- DUTY REPORT {i} ---\n"
                            duty_reports_section += f"Generated: {duty_report['date_generated']}\n"
                            duty_reports_section += f"Date Range: {duty_report['date_range']}\n"
                            duty_reports_section += f"Reports Analyzed: {duty_report['reports_analyzed']}\n\n"
                            duty_reports_section += duty_report['summary']
                            duty_reports_section += "\n" + "="*50 + "\n"

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

                    # Unified prompt for both Admin and Supervisor summaries:
                    prompt = f"""
You are an executive assistant for the Director of Housing & Residence Life at UND. Your task is to synthesize multiple team reports from the week ending {selected_date_for_summary} into a single, comprehensive summary report.

IMPORTANT: Start your response immediately with the first section heading. Do not include any introductory text, cover page text, or phrases like "Here is the comprehensive summary report" or "Weekly Summary Report: Housing & Residence Life". Begin directly with the Executive Summary section.

DATA SOURCES AVAILABLE:
1. Weekly staff reports from residence life team members
2. Weekly duty reports analysis (if available) - quantitative data on incidents, safety, maintenance, and operations
3. Weekly engagement analysis (if available) - event programming, attendance data, community engagement activities

The report MUST contain the following sections, in this order, using markdown headings exactly as shown:

## Executive Summary
A 2-3 sentence high-level overview of the week's key takeaways.

## ASCEND Framework Summary
Summarize work aligned with the ASCEND framework (Accountability, Service, Community, Excellence, Nurture, Development). Start this section with the purpose statement: "ASCEND UND Housing is a unified performance framework for the University of North Dakota's Housing and Residence Life staff. It is designed to clearly define job expectations and drive high performance across the department." For each ASCEND category include a heading and bullet points that reference staff by name.

### Accountability
[Include relevant staff activities and names]

### Service
[Include relevant staff activities and names]

### Community
[Include relevant staff activities and names]

### Excellence
[Include relevant staff activities and names]

### Nurture
[Include relevant staff activities and names]

### Development
[Include relevant staff activities and names]

## Guiding NORTH Pillars Summary
Summarize work aligned with the Guiding NORTH pillars. Start with the purpose statement: "Guiding NORTH is our core communication standard for UND Housing & Residence Life. It's a simple, five-principle framework that ensures every interaction with students and parents is clear, consistent, and supportive. Its purpose is to build trust and provide reliable direction, making students feel valued and well-supported throughout their housing journey." For each pillar include a heading and bullet points that reference staff by name.

## UND LEADS Summary
Start with the purpose statement: "UND LEADS is a roadmap that outlines the university's goals and aspirations. It's built on the idea of empowering people to make a difference and passing on knowledge to future generations." Analyze all activities and categorize them under these UND LEADS pillars with staff names:

### Learning
Professional development, training, skill building, educational initiatives, mentoring

### Equity
Diversity initiatives, inclusive practices, accessibility improvements, fair treatment efforts

### Affinity
Community building, relationship development, team cohesion, campus connections

### Discovery
Research, innovation, new approaches, creative problem-solving, exploration of best practices

### Service
Community service, helping others, volunteer work, supporting university initiatives

## Overall Staff Well-being
Start by stating, "The average well-being score for the week was {average_score} out of 5." Provide a 1-2 sentence qualitative summary and include a subsection.

### Staff to Connect With
List staff who reported low scores or concerning comments, with a brief reason.

## Campus Events Summary
Create a markdown table with the exact format below:

| Event/Committee | Date | Attendees | Alignment |
|-----------------|------|-----------|-----------|
| Event Name | YYYY-MM-DD | Staff Member Name | ASCEND: Category, NORTH: Category |

Include all campus events and committee meetings attended by staff this week. Group multiple attendees for the same event in one row.

## For the Director's Attention
A clear list of items that require director-level attention; mention the staff member who raised each item. If none, state "No specific concerns were raised for the Director this week."

## Key Challenges
Bullet-point summary of significant or recurring challenges reported by staff, noting who reported them where relevant.

## Operational & Safety Summary
If duty reports data is available, create this section with:

### Quantitative Metrics
Create a hall-by-hall breakdown table using this exact format:

| Hall/Building | Total Reports | Lockouts | Maintenance | Policy Violations | Safety Concerns | Staff Responses |
|---------------|---------------|----------|-------------|-------------------|-----------------|-----------------|
| Hall Name | # | # | # | # | # | # |

Include summary totals row at the bottom.

### Trending Issues
Bullet-point summary of patterns in lockouts, maintenance requests, policy violations based on the quantitative data above.

### Staff Response Effectiveness  
Assessment of duty staff performance and response times based on staff response data.

### Safety & Security Highlights
Critical incidents and follow-up actions needed based on safety concerns identified.

## Upcoming Projects & Initiatives
Bullet-point list of key upcoming projects based on the 'Lookahead' sections of the reports.
 
CRITICAL FORMATTING REQUIREMENTS:
- Use EXACTLY the markdown headings shown above (## for main sections, ### for subsections)
- Follow the section structure precisely - do not skip sections or change the order
- When summarizing activities under each framework/pillar, reference the team member name (e.g., "Ashley Vandal demonstrated Accountability by...")
- For UND LEADS, actively look for activities that demonstrate Learning (training, development), Equity (diversity, inclusion), Affinity (relationship building), Discovery (innovation, research), and Service (helping others, community engagement)
- Be concise and professional. Executive Summary must be 2-3 sentences. Other sections should use short paragraphs and bullets
- Ensure every staff member's activities are analyzed for UND LEADS alignment - do not leave this section empty
- CREATE PROPER MARKDOWN TABLES: Use exact table formats shown, ensure proper alignment with | symbols
- If duty reports data is provided, create the Quantitative Metrics table using the hall-by-hall data provided, including totals row
- For Campus Events and Operational & Safety tables: follow exact column structures and formatting shown
Here is the raw report data from all reports for the week, which includes the names of each team member and their categorized activities:

STAFF REPORTS DATA:
{reports_text}

{duty_reports_section}

{engagement_reports_section}
"""
                    model = genai.GenerativeModel("models/gemini-2.5-pro")
                    ai_response = model.generate_content(prompt)
                    
                    # Clean up the response by removing unwanted intro text
                    cleaned_text = clean_summary_response(ai_response.text)
                    
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
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save summary: {e}")

    if not supervisor_mode:  # Only for admin dashboard
        st.divider()
        st.subheader("🏆 Weekly Staff Recognition")
        
        if st.button("Generate Staff Recognition"):
            with st.spinner("🤖 Evaluating staff performance against ASCEND and NORTH criteria..."):
                weekly_reports = [r for r in all_reports if r.get("week_ending_date") == selected_date_for_summary]
                if weekly_reports:
                    rubrics = load_rubrics()
                    if rubrics:
                        recognition = evaluate_staff_performance(weekly_reports, rubrics)
                        if recognition:
                            st.session_state['staff_recognition'] = {
                                "date": selected_date_for_summary,
                                "data": recognition
                            }
                            st.rerun()

        # Display recognition results
        if "staff_recognition" in st.session_state:
            recognition_data = st.session_state["staff_recognition"]
            if recognition_data.get("date") == selected_date_for_summary:
                st.markdown("### Staff Recognition Results")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    ascend_rec = recognition_data["data"].get("ascend_recognition", {})
                    if ascend_rec:
                        st.markdown("#### 🌟 ASCEND Recognition")
                        st.success(f"**{ascend_rec.get('staff_member')}** - {ascend_rec.get('category')}")
                        st.write(f"**Reasoning:** {ascend_rec.get('reasoning')}")
                        st.metric("Performance Score", f"{ascend_rec.get('score', 0)}/10")
                
                with col2:
                    north_rec = recognition_data["data"].get("north_recognition", {})
                    if north_rec:
                        st.markdown("#### 🧭 NORTH Recognition")
                        st.success(f"**{north_rec.get('staff_member')}** - {north_rec.get('category')}")
                        st.write(f"**Reasoning:** {north_rec.get('reasoning')}")
                        st.metric("Performance Score", f"{north_rec.get('score', 0)}/10")
                
                # Add save and download options for staff recognition
                st.markdown("---")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    # Create download data for staff recognition
                    recognition_download_data = f"""# Weekly Staff Recognition Report

**Week Ending:** {selected_date_for_summary}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 🌟 ASCEND Recognition
"""
                    if ascend_rec:
                        recognition_download_data += f"""**Recipient:** {ascend_rec.get('staff_member', 'Unknown')}
**Category:** {ascend_rec.get('category', 'Unknown')}
**Performance Score:** {ascend_rec.get('score', 0)}/10
**Reasoning:** {ascend_rec.get('reasoning', 'No reasoning provided')}

"""
                    else:
                        recognition_download_data += "No ASCEND recognition awarded this week.\n\n"
                    
                    recognition_download_data += """## 🧭 NORTH Recognition
"""
                    if north_rec:
                        recognition_download_data += f"""**Recipient:** {north_rec.get('staff_member', 'Unknown')}
**Category:** {north_rec.get('category', 'Unknown')}
**Performance Score:** {north_rec.get('score', 0)}/10
**Reasoning:** {north_rec.get('reasoning', 'No reasoning provided')}

"""
                    else:
                        recognition_download_data += "No NORTH recognition awarded this week.\n\n"
                    
                    recognition_download_data += """---
Generated by UND Housing & Residence Life Weekly Reporting Tool - Staff Recognition System"""
                    
                    st.download_button(
                        label="📄 Download Recognition",
                        data=recognition_download_data,
                        file_name=f"staff_recognition_{selected_date_for_summary}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown",
                        help="Download the staff recognition report as a markdown file",
                        key="download_staff_recognition"
                    )
                
                with col2:
                    # Save staff recognition button
                    if st.button("💾 Save Recognition", type="primary", key="save_staff_recognition", 
                               help="Save this staff recognition report to the database for permanent access"):
                        
                        user_id = st.session_state.get('user', {}).id if st.session_state.get('user') else None
                        
                        with st.spinner("Saving staff recognition..."):
                            save_result = save_staff_recognition(recognition_data["data"], selected_date_for_summary, user_id)
                        
                        if save_result["success"]:
                            st.success(f"✅ {save_result['message']}")
                        else:
                            st.error(f"❌ Save failed: {save_result['message']}")
                
                with col3:
                    # Clear recognition button
                    if st.button("🗑️ Clear Recognition", type="secondary", key="clear_staff_recognition", 
                               help="Clear the displayed recognition results"):
                        del st.session_state['staff_recognition']
                        st.rerun()

@st.cache_data
def load_rubrics():
    """Load ASCEND and NORTH rubrics from files"""
    rubrics = {}
    try:
        with open('rubrics-integration/rubrics/ascend_rubric.md', 'r', encoding='utf-8') as f:
            rubrics['ascend'] = f.read()
        with open('rubrics-integration/rubrics/north_rubric.md', 'r', encoding='utf-8') as f:
            rubrics['north'] = f.read()
        with open('rubrics-integration/rubrics/staff_evaluation_prompt.txt', 'r', encoding='utf-8') as f:
            rubrics['evaluation_prompt'] = f.read()
    except FileNotFoundError as e:
        st.error(f"Rubric file not found: {e}")
        return None
    return rubrics

@st.cache_data
def evaluate_staff_performance(weekly_reports, rubrics):
    """Use AI to evaluate staff performance against ASCEND and NORTH criteria"""
    if not weekly_reports or not rubrics:
        return None
    
    model = genai.GenerativeModel("models/gemini-2.5-pro")
    
    # Build staff performance data
    staff_data = []
    for report in weekly_reports:
        staff_info = {
            "name": report.get('team_member', 'Unknown'),
            "well_being_score": report.get('well_being_rating', 0),
            "activities": []
        }
        
        report_body = report.get("report_body", {})
        for section_key, section_data in report_body.items():
            if section_data:
                for success in section_data.get("successes", []):
                    staff_info["activities"].append({
                        "type": "success",
                        "text": success.get("text", ""),
                        "ascend_category": success.get("ascend_category", "N/A"),
                        "north_category": success.get("north_category", "N/A")
                    })
        staff_data.append(staff_info)
    
    staff_json = json.dumps(staff_data, indent=2)
    
    prompt = f"""
{rubrics['evaluation_prompt']}

ASCEND Rubric:
{rubrics['ascend']}

NORTH Rubric:
{rubrics['north']}

Staff Performance Data:
{staff_json}

Return JSON with:
{{
  "ascend_recognition": {{
    "staff_member": "Name",
    "category": "ASCEND Category", 
    "reasoning": "Why they exemplify this category",
    "score": 1-10
  }},
  "north_recognition": {{
    "staff_member": "Name", 
    "category": "NORTH Pillar",
    "reasoning": "Why they exemplify this pillar",
    "score": 1-10
  }}
}}
"""
    
    try:
        response = model.generate_content(prompt)
        clean_response = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_response)
    except Exception as e:
        st.error(f"AI evaluation error: {e}")
        return None

def supervisor_summaries_page():
    st.title("My Saved Team Summaries")
    st.write("Saved summaries you've generated for your team.")
    try:
        resp = supabase.rpc('get_supervisor_summaries', {'p_super': st.session_state['user'].id}).execute()
        summaries = resp.data or []
        if not summaries:
            st.info("You have no saved team summaries yet.")
            return
        for s in summaries:
            with st.expander(f"Week Ending {s['week_ending_date']} — Saved {s['created_at']}"):
                st.markdown(clean_summary_response(s['summary_text']))
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
    tab1, tab2 = st.tabs(["🛡️ Duty Analysis", "📊 General Form Analysis"])
    
    with tab1:
        duty_analysis_section()
    
    with tab2:
        general_form_analysis_section()

def duty_analysis_section():
    """Specialized section for duty report analysis"""
    st.subheader("🛡️ Duty Analysis")
    st.markdown("""
    **Focus:** Analyze specific duty reports from Resident Assistants, Community Assistants, RDs, and RMs.  
    **Purpose:** Monitor daily operations, incidents, and staff performance during duty shifts.
    """)
    
    # Predefined duty form types
    DUTY_FORM_TYPES = [
        "Resident Assistant Duty Report",
        "Community Assistant Duty Report", 
        "RD Duty Report",
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
            # Assumption: ~10 duty reports per day, ~10 forms per API page
            # For historical data, we need aggressive page limits to reach back far enough
            days_back = (datetime.now().date() - duty_start_date).days
            
            # Use generous page limits based on date range (always ensure sufficient pages)
            if days_back > 90:
                max_pages = 1000  # 3+ months - maximum pages
            elif days_back > 60:
                max_pages = 800   # 2+ months - high page limit
            elif days_back > 30:
                max_pages = 600   # 1+ months - moderate page limit  
            elif days_back > 14:
                max_pages = 400   # 2+ weeks - sufficient pages
            else:
                max_pages = 200   # Recent data - conservative but adequate
            
            st.info(f"📊 Searching up to {max_pages} pages for duty reports going back {days_back} days to {duty_start_date}")
            st.info(f"📈 **Estimate:** ~{days_back * 10} duty reports expected (10 per day × {days_back} days)")
            
            # Show expanded search warning for very old dates
            if days_back > 30:
                minutes_estimate = max(2, days_back // 20)  # Rough estimate: 1 minute per 20 days
                st.warning(f"⏳ **Extended Search:** Searching {max_pages} pages may take {minutes_estimate}-{minutes_estimate + 1} minutes to complete.")
            
            progress_placeholder = st.empty()
            
            def show_duty_progress(page_num, total_forms, oldest_date, reached_target):
                status = f"📄 Page {page_num}/{max_pages}: {total_forms} forms found"
                if oldest_date != "Unknown":
                    status += f" | Oldest: {oldest_date}"
                if reached_target:
                    status += f" | ✅ Reached {duty_start_date}"
                progress_placeholder.info(status)
            
            all_forms, error = fetch_roompact_forms(
                max_pages=max_pages,
                target_start_date=duty_start_date,
                progress_callback=show_duty_progress
            )
            
            if error:
                st.error(error)
                return
            
            if not all_forms:
                st.warning("No forms found.")
                return
            
            # Filter for duty reports only
            duty_forms, filter_error = filter_forms_by_date_and_type(
                all_forms, duty_start_date, duty_end_date, DUTY_FORM_TYPES
            )
            
            if filter_error:
                st.error(f"Error filtering duty reports: {filter_error}")
                return
            
            # Show actual date range of retrieved forms
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
                    
                    if datetime.strptime(oldest_retrieved, '%Y-%m-%d').date() > duty_start_date:
                        days_missing = (datetime.strptime(oldest_retrieved, '%Y-%m-%d').date() - duty_start_date).days
                        st.warning(f"⚠️ **Missing {days_missing} days of data** - oldest form found is {oldest_retrieved}, but you requested back to {duty_start_date}")
            
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
                st.success(f"✅ Found {len(duty_forms)} duty reports (from {len(all_forms)} total forms)")
            else:
                st.warning(f"No duty reports found in the date range {duty_start_date} to {duty_end_date}")
    
    # Display duty reports if available
    if 'duty_forms' in st.session_state and st.session_state['duty_forms']:
        duty_forms = st.session_state['duty_forms']
        filter_info = st.session_state.get('duty_filter_info', {})
        
        st.subheader(f"🛡️ Duty Reports Found ({len(duty_forms)} reports)")
        
        # Show filter summary
        if filter_info:
            st.info(f"""
            📊 **Analysis Ready:** {filter_info['filtered_count']} duty reports (from {filter_info['total_fetched']} total forms)  
            📅 **Date Range:** {filter_info['start_date']} to {filter_info['end_date']}  
            📋 **Report Types:** {', '.join(DUTY_FORM_TYPES)}
            """)
        
        # Form selection and analysis
        col_select, col_analyze = st.columns([2, 1])
        
        with col_select:
            st.markdown("**Select duty reports to analyze:**")
            
            # Group duty reports by type
            duty_by_type = {}
            for form in duty_forms:
                template_name = form.get('form_template_name', 'Unknown Form')
                if template_name not in duty_by_type:
                    duty_by_type[template_name] = []
                duty_by_type[template_name].append(form)
            
            selected_duty_forms = []
            
            for form_type, type_forms in duty_by_type.items():
                st.markdown(f"**{form_type}** ({len(type_forms)} reports)")
                
                # Select all checkbox for this type
                select_all_key = f"select_all_duty_{form_type.replace(' ', '_')}"
                if st.checkbox(f"Select all {form_type}", key=select_all_key):
                    selected_duty_forms.extend(type_forms)
                else:
                    # Individual report checkboxes (show first 15 per type)
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
                        
                        form_key = f"duty_form_{form_type}_{i}"
                        if st.checkbox(f"📄 {author} - {display_date}", key=form_key):
                            selected_duty_forms.append(form)
                
                st.write("---")
        
        with col_analyze:
            st.markdown("**Analysis Options:**")
            
            # Report type selection
            report_type = st.radio(
                "Report Type:",
                ["📊 Standard Analysis", "📅 Weekly Summary Report"],
                help="Choose between comprehensive analysis or weekly admin summary format"
            )
            
            max_duty_forms = st.slider("Max reports to analyze", 
                                min_value=1, 
                                max_value=1000, 
                                value=500,
                                help="Set high limit to analyze all reports (AI can handle large datasets)",
                                key="max_duty_forms")
            
            if len(selected_duty_forms) > 0:
                st.success(f"✅ {len(selected_duty_forms)} duty reports selected")
                
                # Show helpful message for large datasets
                if len(selected_duty_forms) > 100:
                    st.info(f"💪 **Large Dataset Ready:** You can analyze all {len(selected_duty_forms)} reports! Set the slider to {len(selected_duty_forms)} or higher.")
                
                if st.button("🤖 Generate Duty Analysis", type="primary", key="analyze_duty"):
                    reports_to_analyze = min(len(selected_duty_forms), max_duty_forms)
                    
                    if reports_to_analyze > 100:
                        st.info(f"📊 **Large Dataset Processing:** Analyzing {reports_to_analyze} reports...")
                        st.info("💡 **Batch Processing:** For very large datasets, reports are processed in manageable chunks to respect API limits.")
                    
                    if len(selected_duty_forms) > max_duty_forms:
                        st.warning(f"⚠️ Analyzing first {max_duty_forms} of {len(selected_duty_forms)} selected reports.")
                    
                    # Choose analysis type based on selection
                    if report_type == "📅 Weekly Summary Report":
                        summary = create_weekly_duty_report_summary(
                            selected_duty_forms[:max_duty_forms], 
                            filter_info['start_date'], 
                            filter_info['end_date']
                        )
                        report_label = "Weekly Duty Summary"
                        file_prefix = "weekly_duty_summary"
                        
                        # Immediately store weekly report in session state for admin integration
                        if 'weekly_duty_reports' not in st.session_state:
                            st.session_state['weekly_duty_reports'] = []
                        
                        weekly_report_data = {
                            'date_generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'date_range': f"{filter_info.get('start_date', 'N/A')} to {filter_info.get('end_date', 'N/A')}",
                            'reports_analyzed': min(len(selected_duty_forms), max_duty_forms),
                            'total_selected': len(selected_duty_forms),
                            'summary': summary
                        }
                        
                        st.session_state['weekly_duty_reports'].append(weekly_report_data)
                        
                    else:
                        summary = create_duty_report_summary(
                            selected_duty_forms[:max_duty_forms], 
                            filter_info['start_date'], 
                            filter_info['end_date']
                        )
                        report_label = "Duty Analysis"
                        file_prefix = "duty_analysis"
                    
                    # Store the current analysis in session state to persist after button clicks
                    st.session_state['last_duty_analysis'] = {
                        'summary': summary,
                        'report_label': report_label,
                        'file_prefix': file_prefix,
                        'report_type': report_type,
                        'selected_forms': selected_duty_forms[:max_duty_forms],
                        'filter_info': filter_info,
                        'max_forms': max_duty_forms,
                        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # Display results
                    st.subheader(f"📊 {report_label} Results")
                    st.markdown(summary)
                    
                    # Historical Data Storage Option
                    st.markdown("---")
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown("**📈 Historical Data Storage**")
                        st.info("Store incident data for historical analysis, trending, and graphing by hall, incident type, and date.")
                    
                    with col2:
                        # Get current user ID if available
                        user_id = None
                        if 'user' in st.session_state and st.session_state['user']:
                            user_id = st.session_state['user'].id
                        
                        # Store new data button
                        if st.button("💾 Store Data", type="secondary", key="store_duty_data", 
                                   help="Store individual incident records in database for future analysis and graphing"):
                            
                            with st.spinner("Checking for existing data..."):
                                storage_result = store_duty_report_data(
                                    selected_duty_forms[:max_duty_forms],
                                    filter_info['start_date'],
                                    filter_info['end_date'],
                                    user_id
                                )
                            
                            if storage_result["success"]:
                                st.success(f"✅ {storage_result['message']}")
                                st.info(f"📊 **Stored:** {storage_result.get('records_stored', 0)} incident records from {storage_result.get('reports_processed', 0)} reports")
                            elif storage_result.get("duplicate_detected"):
                                st.warning(f"⚠️ {storage_result['message']}")
                                st.info(f"📊 Found {storage_result.get('existing_count', 0)} existing records for this analysis period.")
                            else:
                                st.error(f"❌ Storage failed: {storage_result['message']}")
                        
                        # Replace existing data button (only show if duplicates might exist)
                        if st.button("🔄 Replace Existing Data", type="secondary", key="replace_duty_data",
                                   help="Delete existing records for this analysis period and store new data"):
                            
                            with st.spinner("Replacing existing incident data..."):
                                replace_result = replace_duty_report_data(
                                    selected_duty_forms[:max_duty_forms],
                                    filter_info['start_date'],
                                    filter_info['end_date'],
                                    user_id
                                )
                            
                            if replace_result["success"]:
                                st.success(f"✅ {replace_result['message']}")
                                st.info(f"📊 **Updated:** {replace_result.get('records_stored', 0)} incident records from {replace_result.get('reports_processed', 0)} reports")
                            else:
                                st.error(f"❌ Replacement failed: {replace_result['message']}")
                    
                    st.markdown("---")
                    
                    # Show success message for weekly reports (already saved above)
                    if report_type == "📅 Weekly Summary Report":
                        st.success("✅ **Weekly report saved!** This report is now available in the Admin Summary section for integration.")
                    
                    # Download option
                    date_range = f"{filter_info.get('start_date', 'N/A')} to {filter_info.get('end_date', 'N/A')}"
                    
                    if report_type == "📅 Weekly Summary Report":
                        summary_data = f"""# Weekly Duty Summary Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Report Types:** {', '.join(DUTY_FORM_TYPES)}  
**Date Range:** {date_range}  
**Reports Analyzed:** {min(len(selected_duty_forms), max_duty_forms)} of {len(selected_duty_forms)} selected  

{summary}

---
Generated by UND Housing & Residence Life Weekly Reporting Tool - Weekly Duty Analysis
Integration ready for Admin Weekly Summaries
"""
                    else:
                        summary_data = f"""# Duty Reports Analysis Summary

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Report Types:** {', '.join(DUTY_FORM_TYPES)}  
**Date Range:** {date_range}  
**Reports Analyzed:** {min(len(selected_duty_forms), max_duty_forms)} of {len(selected_duty_forms)} selected  

{summary}

---
Generated by UND Housing & Residence Life Weekly Reporting Tool - Duty Analysis Section
"""
                    
                    st.download_button(
                        label=f"📄 Download {report_label} Report",
                        data=summary_data,
                        file_name=f"{file_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown",
                        help=f"Download the {report_label.lower()} as a markdown file",
                        key="download_duty_analysis"
                    )
            else:
                st.info("Select duty reports above to enable analysis")
    
    # Display previously generated analysis if available (persists after button clicks)
    if 'last_duty_analysis' in st.session_state:
        analysis_data = st.session_state['last_duty_analysis']
        
        st.markdown("---")
        st.subheader("📋 Previously Generated Analysis")
        st.info(f"**{analysis_data['report_label']}** generated at {analysis_data['generated_at']} | **{analysis_data['filter_info'].get('start_date', 'N/A')} to {analysis_data['filter_info'].get('end_date', 'N/A')}** | **{len(analysis_data['selected_forms'])} reports analyzed**")
        
        # Show the analysis in an expander to save space
        with st.expander("📊 View Analysis Results", expanded=True):
            st.markdown(analysis_data['summary'])
        
        # Recreate the storage and download options for the persisted analysis
        st.markdown("**📈 Historical Data Storage**")
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.info("Store incident data from this analysis for historical trending and graphing.")
        
        with col2:
            # Get current user ID if available
            user_id = None
            if 'user' in st.session_state and st.session_state['user']:
                user_id = st.session_state['user'].id
            
            # Store new data button
            if st.button("💾 Store Data", type="secondary", key="store_persisted_duty_data", 
                       help="Store individual incident records from this analysis in database"):
                
                with st.spinner("Checking for existing data..."):
                    storage_result = store_duty_report_data(
                        analysis_data['selected_forms'],
                        analysis_data['filter_info']['start_date'],
                        analysis_data['filter_info']['end_date'],
                        user_id
                    )
                
                if storage_result["success"]:
                    st.success(f"✅ {storage_result['message']}")
                    st.info(f"📊 **Stored:** {storage_result.get('records_stored', 0)} incident records from {storage_result.get('reports_processed', 0)} reports")
                elif storage_result.get("duplicate_detected"):
                    st.warning(f"⚠️ {storage_result['message']}")
                    st.info(f"📊 Found {storage_result.get('existing_count', 0)} existing records for this analysis period.")
                else:
                    st.error(f"❌ Storage failed: {storage_result['message']}")
            
            # Replace existing data button
            if st.button("🔄 Replace Existing Data", type="secondary", key="replace_persisted_duty_data",
                       help="Delete existing records for this analysis period and store new data"):
                
                with st.spinner("Replacing existing incident data..."):
                    replace_result = replace_duty_report_data(
                        analysis_data['selected_forms'],
                        analysis_data['filter_info']['start_date'],
                        analysis_data['filter_info']['end_date'],
                        user_id
                    )
                
                if replace_result["success"]:
                    st.success(f"✅ {replace_result['message']}")
                    st.info(f"📊 **Updated:** {replace_result.get('records_stored', 0)} incident records from {replace_result.get('reports_processed', 0)} reports")
                else:
                    st.error(f"❌ Replacement failed: {replace_result['message']}")
        
        # Download option for persisted analysis
        date_range = f"{analysis_data['filter_info'].get('start_date', 'N/A')} to {analysis_data['filter_info'].get('end_date', 'N/A')}"
        
        if analysis_data['report_type'] == "📅 Weekly Summary Report":
            summary_data = f"""# Weekly Duty Summary Report

**Generated:** {analysis_data['generated_at']}  
**Report Types:** {', '.join(DUTY_FORM_TYPES)}  
**Date Range:** {date_range}  
**Reports Analyzed:** {len(analysis_data['selected_forms'])} selected  

{analysis_data['summary']}

---
Generated by UND Housing & Residence Life Weekly Reporting Tool - Weekly Duty Analysis
Integration ready for Admin Weekly Summaries
"""
        else:
            summary_data = f"""# Duty Reports Analysis Summary

**Generated:** {analysis_data['generated_at']}  
**Report Types:** {', '.join(DUTY_FORM_TYPES)}  
**Date Range:** {date_range}  
**Reports Analyzed:** {len(analysis_data['selected_forms'])} selected  

{analysis_data['summary']}

---
Generated by UND Housing & Residence Life Weekly Reporting Tool - Duty Analysis Section
"""
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.download_button(
                label=f"📄 Download Report",
                data=summary_data,
                file_name=f"{analysis_data['file_prefix']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                help=f"Download the {analysis_data['report_label'].lower()} as a markdown file",
                key="download_persisted_duty_analysis"
            )
        
        with col2:
            # Save analysis button
            if st.button("💾 Save Analysis", type="primary", key="save_duty_analysis", 
                       help="Save this analysis report to the database for permanent access"):
                
                # Calculate week ending date from the analysis date range
                end_date = analysis_data['filter_info']['end_date']
                
                # Handle both date objects and strings
                if isinstance(end_date, str):
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                # Find the next Sunday (week ending date)
                days_ahead = 6 - end_date.weekday()  # 6 = Sunday
                if days_ahead < 0:  # Target day already happened this week
                    days_ahead += 7
                week_ending = end_date + timedelta(days=days_ahead)
                
                user_id = st.session_state.get('user', {}).id if st.session_state.get('user') else None
                
                with st.spinner("Saving duty analysis..."):
                    save_result = save_duty_analysis(analysis_data, week_ending.isoformat(), user_id)
                
                if save_result["success"]:
                    st.success(f"✅ {save_result['message']}")
                else:
                    st.error(f"❌ Save failed: {save_result['message']}")
        
        with col3:
            # Clear analysis button
            if st.button("🗑️ Clear Analysis", type="secondary", key="clear_duty_analysis", help="Clear the displayed analysis"):
                del st.session_state['last_duty_analysis']
                st.rerun()
    
    else:
        st.info("👆 Click 'Fetch Duty Reports' to load reports from the four duty report types")

def engagement_analysis_section():
    """Specialized section for Residence Life Event Submission analysis - Full Semester Management"""
    st.subheader("🎉 Engagement Analysis - Fall Semester")
    st.markdown("""
    **Focus:** Complete Fall semester event lifecycle management (Aug 22 - Dec 31, 2024)  
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
            all_forms, error = fetch_roompact_forms(
                max_pages=max_pages,
                target_start_date=target_start_date,  # Stop at August 1, 2025
                progress_callback=show_engagement_progress
            )
            
            if error:
                st.error(error)
                return
            
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
                st.success(f"✅ Found {len(engagement_forms)} event submissions since August 1, 2025 (from {len(all_forms)} total forms)")
                
                # Automatically save/update all forms to database for semester-long management
                with st.spinner("🔄 Synchronizing all event submissions to engagement database..."):
                    # Create analysis data structure for saving
                    sync_analysis_data = {
                        'selected_forms': engagement_forms,
                        'filter_info': st.session_state['engagement_filter_info']
                    }
                    
                    # Get current user ID for tracking
                    user_id = st.session_state.get('user_id', None)
                    
                    # Save all events to database
                    sync_result = save_engagement_data(sync_analysis_data, user_id)
                    
                    if sync_result['success']:
                        created = sync_result.get('records_created', 0)
                        updated = sync_result.get('records_updated', 0)
                        skipped = sync_result.get('records_skipped', 0)
                        
                        sync_message = f"✅ **Database Sync Complete:** "
                        if created > 0:
                            sync_message += f"{created} new events created"
                        if updated > 0:
                            if created > 0:
                                sync_message += f", {updated} events updated"
                            else:
                                sync_message += f"{updated} events updated"
                        if skipped > 0:
                            if created > 0 or updated > 0:
                                sync_message += f", {skipped} duplicates skipped"
                            else:
                                sync_message += f"{skipped} records already current"
                        
                        st.success(sync_message)
                        
                        # Show academic year statistics
                        if 'semester_statistics' in sync_result:
                            stats = sync_result['semester_statistics']
                            st.info(f"📊 **Academic Year Status:** {stats.get('approved_events', 0)} approved events | {stats.get('pending_events', 0)} pending approval | {stats.get('cancelled_events', 0)} cancelled")
                    else:
                        sync_error_msg = sync_result.get('message', 'Database sync encountered issues')
                        error_details = sync_result.get('error_details', '')
                        errors = sync_result.get('errors', [])
                        
                        st.error(f"⚠️ **Sync Issue:** {sync_error_msg}")
                        
                        # Show detailed error information for debugging
                        with st.expander("🔍 **Error Details** (Click to view)", expanded=False):
                            if error_details:
                                st.code(f"Technical Error: {error_details}")
                            if errors:
                                st.write("**Individual Event Errors:**")
                                for error in errors[:10]:  # Show first 10 errors
                                    st.write(f"• {error}")
                                if len(errors) > 10:
                                    st.write(f"... and {len(errors) - 10} more errors")
                        
                        # Add database connectivity test button
                        if st.button("🔧 Test Database Connection", key="test_db_connection"):
                            with st.spinner("Testing database connection..."):
                                try:
                                    # Test basic connection
                                    test_result = supabase.table("engagement_report_data").select("id").limit(1).execute()
                                    if test_result.data is not None:
                                        st.success("✅ Database connection successful")
                                        
                                        # Test table structure
                                        try:
                                            schema_test = supabase.table("engagement_report_data").select(
                                                "form_submission_id, event_name, event_approval, hall, semester"
                                            ).limit(1).execute()
                                            st.success("✅ Table structure is accessible")
                                        except Exception as schema_error:
                                            st.error(f"❌ Table structure issue: {str(schema_error)}")
                                            
                                            # Check if it's a "table doesn't exist" error
                                            if "does not exist" in str(schema_error).lower() or "relation" in str(schema_error).lower():
                                                st.info("💡 **Solution:** The `engagement_report_data` table needs to be created in your Supabase database.")
                                                st.info("📝 **Next Steps:**")
                                                st.code("""
1. Open your Supabase Dashboard
2. Go to SQL Editor
3. Copy and paste the ENHANCED_ENGAGEMENT_SCHEMA_FIXED.sql file content
4. Run the SQL to create the table
5. Come back and try the sync again
                                                """)
                                                
                                                with st.expander("📄 **Quick SQL Reference**", expanded=False):
                                                    st.info("Use the ENHANCED_ENGAGEMENT_SCHEMA_FIXED.sql file in your project to create the table.")
                                                    st.info("The file contains the complete schema with all required columns and constraints.")
                                    else:
                                        st.error("❌ Database connection failed - no data returned")
                                except Exception as db_error:
                                    error_str = str(db_error).lower()
                                    if "does not exist" in error_str or "relation" in error_str:
                                        st.error(f"❌ Database table missing: {str(db_error)}")
                                        st.info("💡 **The engagement_report_data table doesn't exist in your database.**")
                                        st.info("🔧 **To fix this:** Run the ENHANCED_ENGAGEMENT_SCHEMA_FIXED.sql script in your Supabase SQL Editor.")
                                    else:
                                        st.error(f"❌ Database connection error: {str(db_error)}")
            else:
                st.warning(f"No {ENGAGEMENT_FORM_TYPE} forms found in the system")
    
    # Display engagement forms if available
    if 'engagement_forms' in st.session_state and st.session_state['engagement_forms']:
        engagement_forms = st.session_state['engagement_forms']
        filter_info = st.session_state.get('engagement_filter_info', {})
        
        st.subheader(f"🎉 Event Submissions Found ({len(engagement_forms)} submissions)")
        
        # Show academic year management summary
        if filter_info:
            st.info(f"""
            🏫 **Academic Year Management:** {filter_info['filtered_count']} event submissions loaded (from {filter_info['total_fetched']} total forms)  
            📅 **Time Period:** {filter_info['start_date']} to {filter_info['end_date']}  
            📋 **Form Type:** {ENGAGEMENT_FORM_TYPE}  
            🔄 **Management Mode:** {filter_info.get('management_mode', 'academic_year')}
            """)
        
        # Form selection and analysis
        col_select, col_analyze = st.columns([2, 1])
        
        with col_select:
            st.markdown("**Select event submissions to analyze:**")
            
            # Group submissions by month for better organization
            submissions_by_month = {}
            for form in engagement_forms:
                current_revision = form.get('current_revision', {})
                date_str = current_revision.get('date', '')
                
                if date_str:
                    try:
                        form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        month_key = form_datetime.strftime('%Y-%m (%B)')
                    except:
                        month_key = "Unknown Month"
                else:
                    month_key = "Unknown Month"
                    
                if month_key not in submissions_by_month:
                    submissions_by_month[month_key] = []
                submissions_by_month[month_key].append(form)
            
            selected_engagement_forms = []
            
            for month, month_forms in sorted(submissions_by_month.items()):
                st.markdown(f"**{month}** ({len(month_forms)} submissions)")
                
                # Select all checkbox for this month
                select_all_key = f"select_all_engagement_{month.replace(' ', '_').replace('(', '').replace(')', '')}"
                if st.checkbox(f"Select all {month}", key=select_all_key):
                    selected_engagement_forms.extend(month_forms)
                else:
                    # Individual form selection with better display
                    for i, form in enumerate(month_forms):
                        current_revision = form.get('current_revision', {})
                        author = current_revision.get('author', 'Unknown')
                        date_str = current_revision.get('date', '')
                        
                        # Extract event title from responses if available
                        event_title = "Event"
                        responses = current_revision.get('responses', [])
                        for response in responses:
                            field_label = response.get('field_label', '').lower()
                            if any(word in field_label for word in ['title', 'name', 'event']):
                                event_title = str(response.get('response', 'Event'))[:50]
                                break
                        
                        form_date = "Unknown Date"
                        if date_str:
                            try:
                                form_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                form_date = form_datetime.strftime('%m/%d/%Y')
                            except:
                                pass
                        
                        form_key = f"engagement_form_{month}_{i}"
                        if st.checkbox(f"{event_title} - {author} ({form_date})", key=form_key):
                            selected_engagement_forms.append(form)
        
        with col_analyze:
            st.markdown("**Analysis Options:**")
            
            if selected_engagement_forms:
                st.success(f"🎯 **Selected:** {len(selected_engagement_forms)} submissions")
                
                # Report type selection
                engagement_report_type = st.selectbox(
                    "📋 Report Type",
                    ["📊 Standard Analysis", "📅 Weekly Summary Report"],
                    help="Choose the type of analysis to generate",
                    key="engagement_report_type"
                )
                
                # Database-based analysis option
                if st.button("🔍 Check Database Event Status", type="secondary", key="db_analysis"):
                    st.write("---")
                    create_db_based_engagement_analysis()
                
                if st.button("🤖 Generate Engagement Analysis", type="primary", key="analyze_engagement"):
                    with st.spinner("🧠 Analyzing event submissions with AI..."):
                        engagement_analysis_result = analyze_engagement_forms_with_ai(
                            selected_engagement_forms, 
                            engagement_report_type,
                            filter_info
                        )
                        
                        if engagement_analysis_result:
                            # Store the analysis
                            st.session_state['last_engagement_analysis'] = engagement_analysis_result
                            
                            # If this is a weekly report, also store it for admin summaries integration
                            if engagement_report_type == "📅 Weekly Summary Report":
                                if 'weekly_engagement_reports' not in st.session_state:
                                    st.session_state['weekly_engagement_reports'] = []
                                
                                weekly_engagement_data = {
                                    'date_generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'date_range': f"{filter_info.get('start_date', 'N/A')} to {filter_info.get('end_date', 'N/A')}",
                                    'events_analyzed': len(selected_engagement_forms),
                                    'total_selected': len(selected_engagement_forms),
                                    'summary': engagement_analysis_result['summary'],
                                    'upcoming_events': extract_upcoming_events(selected_engagement_forms)
                                }
                                
                                st.session_state['weekly_engagement_reports'].append(weekly_engagement_data)
                            
                            st.success("✅ Analysis complete!")
                        else:
                            st.error("❌ Analysis failed. Please try again.")
            else:
                st.info("👆 Select event submissions to analyze")
    
    # Display last analysis if available
    if 'last_engagement_analysis' in st.session_state:
        analysis_data = st.session_state['last_engagement_analysis']
        
        st.subheader("🎉 Engagement Analysis Results")
        
        # Display the analysis content
        st.markdown(analysis_data['summary'])
        
        # Show data extraction debug info
        with st.expander("🔍 Data Extraction Debug (Click to View)", expanded=False):
            try:
                quantitative_data = extract_engagement_quantitative_data(analysis_data['selected_forms'])
                if quantitative_data['success']:
                    events_data = quantitative_data.get('events_data', [])
                    st.write(f"**Successfully extracted data from {len(events_data)} events:**")
            except Exception as e:
                st.warning(f"⚠️ **Debug Info Error:** {str(e)} - This may be due to cached data. Try clearing analysis and regenerating.")
                quantitative_data = {'success': False}
                events_data = []
            
            if quantitative_data.get('success', False):
                
                for i, event in enumerate(events_data[:5]):  # Show first 5 events
                    st.write(f"**Event {i+1}:**")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"- **Title:** {event.get('event_title', 'N/A')}")
                        st.write(f"- **Type:** {event.get('event_type', 'N/A')}")
                        st.write(f"- **Date:** {event.get('event_date', 'N/A')}")
                        st.write(f"- **Hall:** {event.get('location_hall', 'N/A')}")
                    with col_b:
                        st.write(f"- **Estimated Attendance:** {event.get('estimated_attendance', 'N/A')}")
                        st.write(f"- **Budget:** ${event.get('budget_amount', 0)}")
                        st.write(f"- **Status:** {event.get('event_status', 'N/A')}")
                        st.write(f"- **Form ID:** {event.get('form_submission_id', 'N/A')}")
                    
                    # Show form structure debug info
                    if event.get('_debug_form_structure'):
                        with st.expander(f"Form Structure Debug (Event {i+1})", expanded=False):
                            debug_info = event['_debug_form_structure']
                            st.write(f"**Form Keys Available:** {debug_info.get('form_keys', [])}")
                            st.write(f"**Form ID Found:** {debug_info.get('form_id_found', 'None')}")
                            st.write(f"**Revision Keys:** {debug_info.get('revision_keys', [])}")
                    
                    # Show original field labels for debugging
                    if event.get('_debug_fields'):
                        with st.expander(f"Original Form Fields (Event {i+1})", expanded=False):
                            for field_info in event['_debug_fields']:
                                st.text(field_info)
                    st.write("---")
                
                if len(events_data) > 5:
                    st.write(f"... and {len(events_data) - 5} more events")
            else:
                error_msg = quantitative_data.get('message', 'Unknown error occurred')
                st.error(f"Failed to extract data: {error_msg}")
        
        # Auto-save notification
        st.info("ℹ️ **Auto-Save:** Event data was automatically synchronized to the database when forms were fetched. Use Re-sync if you need to update database records.")
        
        # Analysis action buttons
        col1, col2, col3, col4 = st.columns(4)
        
        report_label = "Engagement Analysis"
        if analysis_data['report_type'] == "📅 Weekly Summary Report":
            report_label = "Weekly Engagement Summary"
        
        with col1:
            # Download button
            st.download_button(
                "📥 Download Analysis",
                data=analysis_data['summary'],
                file_name=f"engagement_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown",
                help="Download this engagement analysis as a markdown file",
                key="download_engagement_analysis"
            )
        
        with col2:
            # Re-sync database button (since data is auto-saved during fetch)
            if st.button("� Re-sync Database", key="resync_engagement_data", 
                        help="Re-synchronize event data with database (data is automatically saved during fetch)"):
                user_id = st.session_state.get('user', {}).id if st.session_state.get('user') else None
                
                with st.spinner("Re-synchronizing engagement data..."):
                    save_result = save_engagement_data(analysis_data, user_id)
                
                if save_result["success"]:
                    created = save_result.get('records_created', 0)
                    updated = save_result.get('records_updated', 0) 
                    skipped = save_result.get('records_skipped', 0)
                    
                    if created == 0 and updated == 0:
                        st.info("✅ Database already synchronized - no changes needed")
                    else:
                        st.success(f"✅ Re-sync complete: {created} created, {updated} updated, {skipped} skipped")
                else:
                    st.error(f"❌ Re-sync failed: {save_result['message']}")
        
        with col3:
            # Save weekly analysis button  
            if st.button("📋 Save Weekly Analysis", key="save_engagement_analysis",
                        help="Save this analysis report for future reference"):
                # Calculate week ending date from analysis period
                end_date = analysis_data['filter_info']['end_date']
                
                # Handle both date objects and strings
                if isinstance(end_date, str):
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                # Find the next Sunday (week ending date)
                days_ahead = 6 - end_date.weekday()  # 6 = Sunday
                if days_ahead < 0:  # Target day already happened this week
                    days_ahead += 7
                week_ending = end_date + timedelta(days=days_ahead)
                
                user_id = st.session_state.get('user', {}).id if st.session_state.get('user') else None
                
                with st.spinner("Saving engagement analysis..."):
                    save_result = save_engagement_analysis(analysis_data, week_ending.isoformat(), user_id)
                
                if save_result["success"]:
                    st.success(f"✅ {save_result['message']}")
                else:
                    st.error(f"❌ Save failed: {save_result['message']}")
        
        with col4:
            # Clear analysis button
            if st.button("🗑️ Clear Analysis", type="secondary", key="clear_engagement_analysis", help="Clear the displayed analysis"):
                del st.session_state['last_engagement_analysis']
                st.rerun()
    
    else:
        st.info("👆 Click 'Fetch Event Submissions' to load Residence Life Event Submission forms")

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
                    total_forms = test_data.get('total_records', 0)
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
            
            all_forms, error = fetch_roompact_forms(
                max_pages=max_pages,
                target_start_date=start_date,
                progress_callback=show_fetch_progress
            )
            
            if error:
                st.error(error)
                return
            
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


def admin_settings_page():
    st.title("Administrator Settings")
    st.write("Configure system settings and deadlines.")
    
    tab1, tab2, tab3 = st.tabs(["📅 Deadline Settings", "📊 Submission Tracking", "📧 Email Configuration"])
    
    with tab1:
        st.subheader("Weekly Report Deadline Configuration")
        
        # Get current deadline settings using the proper function
        deadline_config = get_deadline_settings()
        current_day = deadline_config.get("day_of_week", 0)  # 0 = Monday
        current_hour = deadline_config.get("hour", 16)  # 4 PM
        current_minute = deadline_config.get("minute", 0)
        current_grace = deadline_config.get("grace_hours", 16)
        
        st.info(f"**Current Settings:** Reports due every **{['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][current_day]}** at **{current_hour:02d}:{current_minute:02d}** with **{current_grace}** hour grace period")
        
        with st.form("deadline_settings"):
            st.write("Set when weekly reports are due:")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                deadline_day = st.selectbox(
                    "Day of Week",
                    options=[0, 1, 2, 3, 4, 5, 6],
                    format_func=lambda x: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][x],
                    index=current_day
                )
            
            with col2:
                deadline_hour = st.selectbox(
                    "Hour (24-hour format)",
                    options=list(range(24)),
                    format_func=lambda x: f"{x:02d}:00",
                    index=current_hour
                )
            
            with col3:
                deadline_minute = st.selectbox(
                    "Minute",
                    options=[0, 15, 30, 45],
                    format_func=lambda x: f"{x:02d}",
                    index=[0, 15, 30, 45].index(current_minute) if current_minute in [0, 15, 30, 45] else 0
                )
            
            grace_period = st.number_input(
                "Grace Period (hours after deadline for editing)",
                min_value=0,
                max_value=72,
                value=current_grace,
                help="How many hours after the deadline staff can still edit their reports"
            )
            
            st.info(f"Current setting: Reports due every **{['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][deadline_day]}** at **{deadline_hour:02d}:{deadline_minute:02d}** with **{grace_period}** hour grace period")
            
            if st.form_submit_button("Save Deadline Settings", type="primary"):
                try:
                    new_settings = {
                        "day_of_week": deadline_day,
                        "hour": deadline_hour,
                        "minute": deadline_minute,
                        "grace_hours": grace_period
                    }
                    
                    admin_user_id = st.session_state["user"].id
                    
                    with st.spinner("Saving settings to database..."):
                        # Save to admin_settings table in database
                        result = supabase.table("admin_settings").upsert({
                            "setting_name": "report_deadline",
                            "setting_value": new_settings,
                            "updated_by": admin_user_id
                        }, on_conflict="setting_name").execute()
                        
                        st.write(f"Debug: Database response: {result}")  # Debug info
                    
                    # Also update session state for immediate use
                    st.session_state["admin_deadline_settings"] = new_settings
                    
                    st.success("✅ Deadline settings saved successfully to database!")
                    st.info(f"Saved: Reports due **{['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][deadline_day]}** at **{deadline_hour:02d}:{deadline_minute:02d}** with **{grace_period}** hour grace period")
                    time.sleep(2)
                    st.rerun()
                        
                except Exception as e:
                    st.error(f"Failed to save settings: {e}")
    
    with tab2:
        st.subheader("Submission Tracking Dashboard")
        st.write("Track when reports are submitted and identify late submissions.")
        
        # Get recent submissions with timing data
        try:
            recent_reports = supabase.table("reports").select("*").eq("status", "finalized").order("submitted_at", desc=True).limit(50).execute()
            if recent_reports.data:
                
                # Get current deadline settings for analysis using helper function
                deadline_config = get_deadline_settings()
                
                # Create submission analysis
                submission_data = []
                for report in recent_reports.data:
                    submitted_at = report.get("submitted_at")
                    if submitted_at:
                        submission_time = pd.to_datetime(submitted_at)
                        
                        # Calculate if submission was on time based on deadline settings
                        week_ending = pd.to_datetime(report.get("week_ending_date"))
                        # Calculate deadline for that week
                        deadline_day = deadline_config["day_of_week"]
                        deadline_hour = deadline_config["hour"] 
                        deadline_minute = deadline_config["minute"]
                        
                        # Deadline is typically the Monday after the Saturday week ending
                        days_after_saturday = (deadline_day - 5) % 7 + (1 if deadline_day <= 5 else 0)
                        deadline_date = week_ending + timedelta(days=days_after_saturday)
                        deadline_datetime = datetime.combine(deadline_date.date(), 
                                                           datetime.min.time().replace(hour=deadline_hour, minute=deadline_minute))
                        deadline_datetime = deadline_datetime.replace(tzinfo=ZoneInfo("America/Chicago"))
                        
                        # Compare submission time to deadline
                        was_on_time = submission_time <= deadline_datetime
                        was_in_grace = submission_time <= (deadline_datetime + timedelta(hours=deadline_config["grace_hours"]))
                        
                        if was_on_time:
                            status = "✅ On Time"
                        elif was_in_grace:
                            status = "⚠️ Grace Period"
                        else:
                            status = "❌ Late"
                        
                        submission_data.append({
                            "Staff Member": report.get("team_member", "Unknown"),
                            "Week Ending": report.get("week_ending_date", "Unknown"), 
                            "Submitted": submission_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "Day of Week": submission_time.strftime("%A"),
                            "Time": submission_time.strftime("%H:%M"),
                            "Deadline": deadline_datetime.strftime("%Y-%m-%d %H:%M"),
                            "Status": status,
                            "Admin Created": "Yes" if report.get("status") == "admin_created" or report.get("created_by_admin") else "No"
                        })
                
                if submission_data:
                    df = pd.DataFrame(submission_data)
                    st.dataframe(df, use_container_width=True)
                    
                    # Summary stats
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        on_time = len([s for s in submission_data if s["Status"] == "✅ On Time"])
                        st.metric("On Time", on_time)
                    with col2:
                        grace = len([s for s in submission_data if s["Status"] == "⚠️ Grace Period"])
                        st.metric("Grace Period", grace)
                    with col3:
                        late = len([s for s in submission_data if s["Status"] == "❌ Late"])
                        st.metric("Late", late)
                    with col4:
                        if submission_data:
                            rate = (on_time / len(submission_data)) * 100
                            st.metric("On-Time Rate", f"{rate:.1f}%")
                else:
                    st.info("No submission data available yet.")
            else:
                st.info("No reports found.")
        except Exception as e:
            st.error(f"Error loading submission data: {e}")
    
    with tab3:
        st.subheader("Email Configuration")
        st.write("Configure email settings for sending UND LEADS summaries.")
        
        st.info("""
        **Email Setup Instructions:**
        
        To enable email functionality, you need to configure email settings in your Streamlit secrets.
        
        **FOR GMAIL (Recommended):**
        
        1. **Enable 2-Step Verification** on your Gmail account:
           - Go to myaccount.google.com → Security → 2-Step Verification
           - Follow the setup process
        
        2. **Generate an App Password**:
           - Go to myaccount.google.com → Security → 2-Step Verification → App passwords
           - Select "Mail" and your device
           - Copy the 16-digit password (e.g., "abcd efgh ijkl mnop")
        
        3. **Update your secrets.toml**:
        ```toml
        EMAIL_ADDRESS = "your-gmail@gmail.com"
        EMAIL_PASSWORD = "abcd efgh ijkl mnop"  # 16-digit app password
        SMTP_SERVER = "smtp.gmail.com"
        ```
        
        **FOR UND/Office 365 Email:**
        ```toml
        EMAIL_ADDRESS = "your-email@und.edu"
        EMAIL_PASSWORD = "your-regular-password"
        SMTP_SERVER = "smtp.office365.com"
        ```
        
        **IMPORTANT:** 
        - Never use your regular Gmail password - only use App Passwords
        - Restart Streamlit after updating secrets.toml
        - Never commit secrets.toml to version control!
        """)
        
        # Test email configuration
        st.subheader("Test Email Configuration")
        
        with st.form("test_email"):
            test_email = st.text_input("Send test email to:", placeholder="your-email@und.edu")
            
            if st.form_submit_button("📧 Send Test Email"):
                if test_email:
                    test_subject = "UND Housing Reports - Email Test"
                    test_body = """This is a test email from the UND Housing Leadership Reports system.

If you received this email, your email configuration is working correctly!

Test sent at: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    with st.spinner("Sending test email..."):
                        success = send_email(test_email, test_subject, test_body)
                        if success:
                            st.success(f"✅ Test email sent successfully to {test_email}")
                        else:
                            st.error("❌ Failed to send test email. Please check your configuration.")
                else:
                    st.error("Please enter an email address for testing.")
        
        # Display current email configuration status
        st.subheader("Configuration Status")
        
        try:
            # More detailed debugging
            st.write("🔍 **Debug Information:**")
            
            # Show secrets file location
            import os
            current_dir = os.getcwd()
            secrets_path = os.path.join(current_dir, ".streamlit", "secrets.toml")
            st.info(f"**Secrets file location:** `{secrets_path}`")
            st.info(f"**File exists:** {os.path.exists(secrets_path)}")
            
            # Check if secrets exist at all
            try:
                secrets_keys = list(st.secrets.keys()) if hasattr(st.secrets, 'keys') else []
                st.write(f"Available secrets keys: {secrets_keys}")
            except Exception as e:
                st.write(f"Error accessing secrets keys: {e}")
            
            # Check each configuration item
            try:
                email_address = st.secrets["EMAIL_ADDRESS"]
                if email_address.startswith("your-") or "placeholder" in email_address.lower():
                    st.error(f"❌ EMAIL_ADDRESS still contains placeholder: {email_address}")
                    st.warning("Please update your .streamlit/secrets.toml with your real Gmail address")
                else:
                    st.success("✅ Email Address Found")
                    st.text(f"From: {email_address}")
            except KeyError:
                st.error("❌ EMAIL_ADDRESS key not found in secrets")
            except Exception as e:
                st.error(f"❌ Error accessing EMAIL_ADDRESS: {e}")
            
            try:
                email_password = st.secrets["EMAIL_PASSWORD"]
                if email_password.startswith("your-") or "placeholder" in email_password.lower() or len(email_password) != 16:
                    st.error(f"❌ EMAIL_PASSWORD appears to be placeholder or wrong length (should be 16 chars)")
                    st.warning("Please update your .streamlit/secrets.toml with your real Gmail App Password")
                else:
                    st.success("✅ Email Password Found")
                    st.text("Password: [HIDDEN - 16 characters detected]")
            except KeyError:
                st.error("❌ EMAIL_PASSWORD key not found in secrets")
            except Exception as e:
                st.error(f"❌ Error accessing EMAIL_PASSWORD: {e}")
            
            try:
                smtp_server = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
                st.success("✅ SMTP Server Available")
                st.text(f"Server: {smtp_server}")
            except Exception as e:
                st.error(f"❌ Error accessing SMTP_SERVER: {e}")
                
        except Exception as e:
            st.error(f"Error checking configuration: {e}")
            
        # Instructions for common issues
        st.subheader("Troubleshooting")
        st.warning("""
        **Common Issues:**
        
        1. **File Location**: Make sure `.streamlit/secrets.toml` is in your project root directory
        2. **File Format**: Ensure the file uses TOML format with quotes around values
        3. **Restart Required**: Restart Streamlit after modifying secrets.toml
        4. **File Permissions**: Check that the secrets file is readable
        
        **Example secrets.toml:**
        ```toml
        EMAIL_ADDRESS = "your-email@und.edu"
        EMAIL_PASSWORD = "your-password"
        SMTP_SERVER = "smtp.office365.com"
        ```
        """)

def saved_reports_page():
    """View saved duty analyses, staff recognition reports, and weekly summaries"""
    st.title("Saved Reports Archive")
    st.write("View all saved reports: duty analyses, staff recognition, and weekly summaries.")
    
    # Tab selection for different report types
    tab1, tab2, tab3 = st.tabs(["🛡️ Duty Analyses", "🏆 Staff Recognition", "📅 Weekly Summaries"])
    
    with tab1:
        st.subheader("Saved Duty Analyses")
        
        try:
            # Get all saved duty analyses
            analyses_response = supabase.table('saved_duty_analyses').select('*').order('week_ending_date', desc=True).execute()
            analyses = analyses_response.data or []
            
            if not analyses:
                st.info("No saved duty analyses yet.")
            else:
                # Group analyses by year for better organization
                analyses_by_year = {}
                for analysis in analyses:
                    try:
                        year = pd.to_datetime(analysis['week_ending_date']).year
                        if year not in analyses_by_year:
                            analyses_by_year[year] = []
                        analyses_by_year[year].append(analysis)
                    except:
                        # If date parsing fails, group under "Unknown"
                        if "Unknown" not in analyses_by_year:
                            analyses_by_year["Unknown"] = []
                        analyses_by_year["Unknown"].append(analysis)
                
                # Display analyses by year
                for year in sorted(analyses_by_year.keys(), reverse=True):
                    st.subheader(f"📅 {year}")
                    year_analyses = analyses_by_year[year]
                    
                    for analysis in year_analyses:
                        week_date = analysis.get('week_ending_date', 'Unknown')
                        created_date = analysis.get('created_at', '')[:10] if analysis.get('created_at') else 'Unknown'
                        created_by = analysis.get('created_by', 'Unknown')
                        report_type = analysis.get('report_type', 'standard_analysis')
                        reports_analyzed = analysis.get('reports_analyzed', 0)
                        
                        # Get creator name if possible
                        creator_name = "Unknown"
                        if created_by and created_by != 'Unknown':
                            try:
                                profile_resp = supabase.table('profiles').select('full_name, title').eq('id', created_by).execute()
                                if profile_resp.data:
                                    profile = profile_resp.data[0]
                                    creator_name = profile.get('full_name') or profile.get('title') or 'Unknown'
                            except:
                                creator_name = "Unknown"
                        
                        report_type_display = "Weekly Summary" if report_type == "weekly_summary" else "Standard Analysis"
                        
                        with st.expander(f"Week Ending {week_date} — {report_type_display} ({reports_analyzed} reports) — Created {created_date} by {creator_name}"):
                            st.markdown(analysis.get('analysis_text', 'No content available'))
                            
                            st.divider()
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                # Download button
                                download_filename = f"duty_analysis_{report_type}_{week_date}_{created_date}.md"
                                st.download_button(
                                    label="📄 Download Analysis",
                                    data=analysis.get('analysis_text', ''),
                                    file_name=download_filename,
                                    mime="text/markdown",
                                    help="Download this duty analysis as a markdown file",
                                    key=f"download_duty_{analysis.get('id', week_date)}"
                                )
                            
                            with col2:
                                # Delete button (only for creator or admin)
                                user_id = st.session_state.get('user', {}).id if st.session_state.get('user') else None
                                if user_id and (user_id == created_by):  # Could add admin check here
                                    if st.button(f"🗑️ Delete", key=f"delete_duty_{analysis.get('id', week_date)}", 
                                               type="secondary", help="Delete this saved analysis"):
                                        try:
                                            supabase.table('saved_duty_analyses').delete().eq('id', analysis['id']).execute()
                                            st.success("Analysis deleted!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Failed to delete: {e}")
        
        except Exception as e:
            st.error(f"Failed to fetch saved duty analyses: {e}")
    
    with tab2:
        st.subheader("Saved Staff Recognition Reports")
        
        try:
            # Get all saved staff recognition reports
            recognition_response = supabase.table('saved_staff_recognition').select('*').order('week_ending_date', desc=True).execute()
            recognitions = recognition_response.data or []
            
            if not recognitions:
                st.info("No saved staff recognition reports yet.")
            else:
                # Group recognitions by year for better organization
                recognitions_by_year = {}
                for recognition in recognitions:
                    try:
                        year = pd.to_datetime(recognition['week_ending_date']).year
                        if year not in recognitions_by_year:
                            recognitions_by_year[year] = []
                        recognitions_by_year[year].append(recognition)
                    except:
                        if "Unknown" not in recognitions_by_year:
                            recognitions_by_year["Unknown"] = []
                        recognitions_by_year["Unknown"].append(recognition)
                
                # Display staff recognitions by year
                for year in sorted(recognitions_by_year.keys(), reverse=True):
                    st.write(f"### � {year} Staff Recognition Reports")
                    
                    year_recognitions = recognitions_by_year[year]
                    for recognition in year_recognitions:
                        # Get creator info
                        creator_name = "Unknown User"
                        if recognition.get('created_by'):
                            try:
                                profile_response = supabase.table('profiles').select('full_name').eq('id', recognition['created_by']).execute()
                                if profile_response.data:
                                    creator_name = profile_response.data[0]['full_name']
                            except:
                                pass
                        
                        # Format dates
                        week_date = recognition['week_ending_date']
                        created_date = recognition['created_at'][:10] if recognition.get('created_at') else 'Unknown'
                        
                        # Display recognition info
                        with st.expander(f"Week Ending {week_date} - Staff Recognition - {creator_name}"):
                            st.write(f"**Staff Recognized:** {recognition.get('staff_recognized', 0)}")
                            st.write(f"**Created:** {created_date} by {creator_name}")
                            
                            # Show recognition summary
                            if recognition.get('summary'):
                                st.markdown("**Recognition Summary:**")
                                st.markdown(recognition['summary'])
                            
                            # Action buttons
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                # Download button
                                st.download_button(
                                    "📥 Download",
                                    data=analysis['analysis_text'],
                                    file_name=f"engagement_analysis_{week_date}.md",
                                    mime="text/markdown",
                                    help="Download this engagement analysis as a markdown file",
                                    key=f"download_engagement_{analysis['id']}"
                                )
                            
                            with col2:
                                # Email UND LEADS section button (if applicable)
                                if "UND LEADS" in analysis['analysis_text']:
                                    if st.button(f"📧 Email UND LEADS", key=f"email_engagement_leads_{analysis['id']}", 
                                               help="Extract and prepare UND LEADS section for email"):
                                        leads_section = extract_und_leads_section(analysis['analysis_text'])
                                        
                                        if leads_section and not leads_section.startswith("Could not find UND LEADS") and not leads_section.startswith("No summary text"):
                                            st.session_state['email_content'] = {
                                                'subject': f"UND LEADS Summary - Week Ending {week_date}",
                                                'body': leads_section,
                                                'week_date': week_date
                                            }
                                            st.success("📧 UND LEADS section extracted! You can now use the email form in Admin Summaries to send it.")
                                        else:
                                            st.warning(f"⚠️ {leads_section}")
                            
                            with col3:
                                # Delete button
                                if st.button("🗑️ Delete", key=f"delete_engagement_{analysis['id']}", 
                                           help="Permanently delete this engagement analysis"):
                                    try:
                                        supabase.table('saved_engagement_analyses').delete().eq('id', analysis['id']).execute()
                                        st.success("✅ Engagement analysis deleted!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to delete: {e}")
        
        except Exception as e:
            st.error(f"Failed to fetch saved engagement analyses: {e}")
    
    with tab3:
        st.subheader("Saved Staff Recognition Reports")
        
        try:
            # Get all saved staff recognition reports
            recognition_response = supabase.table('saved_staff_recognition').select('*').order('week_ending_date', desc=True).execute()
            recognitions = recognition_response.data or []
            
            if not recognitions:
                st.info("No saved staff recognition reports yet.")
            else:
                # Group recognitions by year
                recognitions_by_year = {}
                for recognition in recognitions:
                    try:
                        year = pd.to_datetime(recognition['week_ending_date']).year
                        if year not in recognitions_by_year:
                            recognitions_by_year[year] = []
                        recognitions_by_year[year].append(recognition)
                    except:
                        if "Unknown" not in recognitions_by_year:
                            recognitions_by_year["Unknown"] = []
                        recognitions_by_year["Unknown"].append(recognition)
                
                # Display recognitions by year
                for year in sorted(recognitions_by_year.keys(), reverse=True):
                    st.subheader(f"📅 {year}")
                    year_recognitions = recognitions_by_year[year]
                    
                    for recognition in year_recognitions:
                        week_date = recognition.get('week_ending_date', 'Unknown')
                        created_date = recognition.get('created_at', '')[:10] if recognition.get('created_at') else 'Unknown'
                        created_by = recognition.get('created_by', 'Unknown')
                        
                        # Get creator name
                        creator_name = "Unknown"
                        if created_by and created_by != 'Unknown':
                            try:
                                profile_resp = supabase.table('profiles').select('full_name, title').eq('id', created_by).execute()
                                if profile_resp.data:
                                    profile = profile_resp.data[0]
                                    creator_name = profile.get('full_name') or profile.get('title') or 'Unknown'
                            except:
                                creator_name = "Unknown"
                        
                        # Extract recognition summary for title
                        ascend_data = json.loads(recognition.get('ascend_recognition', '{}')) if recognition.get('ascend_recognition') else {}
                        north_data = json.loads(recognition.get('north_recognition', '{}')) if recognition.get('north_recognition') else {}
                        
                        recipients = []
                        if ascend_data.get('staff_member'):
                            recipients.append(f"ASCEND: {ascend_data['staff_member']}")
                        if north_data.get('staff_member'):
                            recipients.append(f"NORTH: {north_data['staff_member']}")
                        
                        recipients_text = " | ".join(recipients) if recipients else "No recipients"
                        
                        with st.expander(f"Week Ending {week_date} — {recipients_text} — Created {created_date} by {creator_name}"):
                            st.markdown(recognition.get('recognition_text', 'No content available'))
                            
                            st.divider()
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                # Download button
                                download_filename = f"staff_recognition_{week_date}_{created_date}.md"
                                st.download_button(
                                    label="📄 Download Recognition",
                                    data=recognition.get('recognition_text', ''),
                                    file_name=download_filename,
                                    mime="text/markdown",
                                    help="Download this staff recognition report as a markdown file",
                                    key=f"download_recognition_{recognition.get('id', week_date)}"
                                )
                            
                            with col2:
                                # Delete button (only for creator or admin)
                                user_id = st.session_state.get('user', {}).id if st.session_state.get('user') else None
                                if user_id and (user_id == created_by):  # Could add admin check here
                                    if st.button(f"🗑️ Delete", key=f"delete_recognition_{recognition.get('id', week_date)}", 
                                               type="secondary", help="Delete this saved recognition report"):
                                        try:
                                            supabase.table('saved_staff_recognition').delete().eq('id', recognition['id']).execute()
                                            st.success("Recognition report deleted!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Failed to delete: {e}")
        
        except Exception as e:
            st.error(f"Failed to fetch saved staff recognition reports: {e}")
    
    with tab3:
        st.subheader("Saved Weekly Summaries")
        
        try:
            # Get all saved weekly summaries
            summaries_response = supabase.table('weekly_summaries').select('*').order('week_ending_date', desc=True).execute()
            summaries = summaries_response.data or []
            
            if not summaries:
                st.info("No saved weekly summaries yet.")
            else:
                # Group summaries by year
                summaries_by_year = {}
                for summary in summaries:
                    try:
                        year = pd.to_datetime(summary['week_ending_date']).year
                        if year not in summaries_by_year:
                            summaries_by_year[year] = []
                        summaries_by_year[year].append(summary)
                    except:
                        if "Unknown" not in summaries_by_year:
                            summaries_by_year["Unknown"] = []
                        summaries_by_year["Unknown"].append(summary)
                
                # Display summaries by year
                for year in sorted(summaries_by_year.keys(), reverse=True):
                    st.subheader(f"📅 {year}")
                    year_summaries = summaries_by_year[year]
                    
                    for summary in year_summaries:
                        week_date = summary.get('week_ending_date', 'Unknown')
                        created_date = summary.get('created_at', '')[:10] if summary.get('created_at') else 'Unknown'
                        created_by = summary.get('created_by', 'Unknown')
                        
                        # Get creator name
                        creator_name = "Unknown"
                        if created_by and created_by != 'Unknown':
                            try:
                                profile_resp = supabase.table('profiles').select('full_name, title').eq('id', created_by).execute()
                                if profile_resp.data:
                                    profile = profile_resp.data[0]
                                    creator_name = profile.get('full_name') or profile.get('title') or 'Unknown'
                            except:
                                creator_name = "Unknown"
                        
                        with st.expander(f"Week Ending {week_date} — Created {created_date} by {creator_name}"):
                            st.markdown(clean_summary_response(summary.get('summary_text', 'No content available')))
                            
                            st.divider()
                            col1, col2, col3 = st.columns(3)
                            
                            # Download options (similar to admin_summaries_page)
                            with col1:
                                st.write("📄 **Download Options**")
                                
                                # HTML formatted download
                                html_data, html_filename, html_mime = create_formatted_document_download(
                                    clean_summary_response(summary.get('summary_text', '')), week_date, creator_name, "html"
                                )
                                st.download_button(
                                    label="📊 Download HTML Report",
                                    data=html_data,
                                    file_name=html_filename,
                                    mime=html_mime,
                                    help="Downloads a nicely formatted HTML document that can be opened in any browser or printed",
                                    key=f"download_html_archive_{summary.get('id', week_date)}"
                                )
                            
                            with col2:
                                # Plain text download
                                text_data, text_filename, text_mime = create_formatted_document_download(
                                    clean_summary_response(summary.get('summary_text', '')), week_date, creator_name, "text"
                                )
                                st.download_button(
                                    label="📄 Download Text Version",
                                    data=text_data,
                                    file_name=text_filename,
                                    mime=text_mime,
                                    help="Downloads a formatted text document",
                                    key=f"download_text_archive_{summary.get('id', week_date)}"
                                )
                            
                            with col3:
                                # Email UND LEADS section button
                                if st.button(f"📧 Email UND LEADS", key=f"email_leads_archive_{summary.get('id', week_date)}", 
                                           help="Extract and prepare UND LEADS section for email"):
                                    # Extract UND LEADS section
                                    leads_section = extract_und_leads_section(clean_summary_response(summary.get('summary_text', '')))
                                    if leads_section and not leads_section.startswith("Could not find UND LEADS") and not leads_section.startswith("No summary text"):
                                        # Store in session state for email form
                                        st.session_state['email_content'] = {
                                            'subject': f"UND LEADS Summary - Week Ending {week_date}",
                                            'body': leads_section,
                                            'week_date': week_date
                                        }
                                        st.success("📧 UND LEADS section extracted! You can now send the email below.")
                                    else:
                                        st.warning(f"⚠️ {leads_section}")
                                # Show email form if content is ready and matches this summary
                                if ('email_content' in st.session_state and st.session_state['email_content']['week_date'] == week_date):
                                    st.subheader("📧 Send UND LEADS Section")
                                    with st.form(f"email_form_archive_{week_date}"):
                                        to_email = st.text_input("Recipient Email:", placeholder="example@und.edu")
                                        subject = st.text_input("Subject:", value=st.session_state['email_content']['subject'])
                                        body = st.text_area("Email Body:", value=st.session_state['email_content']['body'], height=200)
                                        col_send, col_cancel = st.columns(2)
                                        with col_send:
                                            if st.form_submit_button("📧 Send Email", type="primary"):
                                                if to_email:
                                                    with st.spinner("Sending email..."):
                                                        success = send_email(to_email, subject, body)
                                                        if success:
                                                            st.success(f"✅ UND LEADS section emailed successfully to {to_email}")
                                                            if 'email_content' in st.session_state:
                                                                del st.session_state['email_content']
                                                            time.sleep(2)
                                                            st.rerun()
                                                        else:
                                                            st.error("Failed to send email. Please check email configuration.")
                                                else:
                                                    st.error("Please enter a recipient email address.")
                                        with col_cancel:
                                            if st.form_submit_button("Cancel"):
                                                if 'email_content' in st.session_state:
                                                    del st.session_state['email_content']
                                                st.rerun()
        
        except Exception as e:
            st.error(f"Failed to fetch saved weekly summaries: {e}")

def admin_summaries_page():
    st.title("Weekly Summaries - Email & Advanced Options")
    st.write("View weekly summaries with email functionality for UND LEADS sections. For general report viewing, use the Saved Reports Archive.")
    
    st.info("💡 **Tip:** For browsing all saved reports (duty analyses, staff recognition, and weekly summaries), visit the **Saved Reports Archive** page.")
    
    try:
        # Get all saved summaries
        summaries_response = supabase.table('weekly_summaries').select('*').order('week_ending_date', desc=True).execute()
        summaries = summaries_response.data or []
        
        if not summaries:
            st.info("No weekly summaries have been saved yet.")
            return
        
        # Group summaries by year for better organization
        summaries_by_year = {}
        for summary in summaries:
            try:
                year = pd.to_datetime(summary['week_ending_date']).year
                if year not in summaries_by_year:
                    summaries_by_year[year] = []
                summaries_by_year[year].append(summary)
            except:
                # If date parsing fails, group under "Unknown"
                if "Unknown" not in summaries_by_year:
                    summaries_by_year["Unknown"] = []
                summaries_by_year["Unknown"].append(summary)
        
        # Display summaries by year
        for year in sorted(summaries_by_year.keys(), reverse=True):
            st.subheader(f"📅 {year}")
            year_summaries = summaries_by_year[year]
            
            for summary in year_summaries:
                week_date = summary.get('week_ending_date', 'Unknown')
                created_date = summary.get('created_at', '')[:10] if summary.get('created_at') else 'Unknown'
                created_by = summary.get('created_by', 'Unknown')
                
                # Get creator name if possible
                creator_name = "Unknown"
                if created_by and created_by != 'Unknown':
                    try:
                        profile_resp = supabase.table('profiles').select('full_name, title').eq('id', created_by).execute()
                        if profile_resp.data:
                            profile = profile_resp.data[0]
                            creator_name = profile.get('full_name') or profile.get('title') or 'Unknown'
                    except:
                        creator_name = "Unknown"
                
                with st.expander(f"Week Ending {week_date} — Created {created_date} by {creator_name}"):
                    st.markdown(clean_summary_response(summary.get('summary_text', '')))
                    
                    st.divider()
                    col1, col2, col3 = st.columns(3)
                    
                    # Download button with format options
                    with col1:
                        st.write("📄 **Download Options**")
                        
                        # HTML formatted download
                        html_data, html_filename, html_mime = create_formatted_document_download(
                            clean_summary_response(summary.get('summary_text', '')), week_date, creator_name, "html"
                        )
                        st.download_button(
                            label="📊 Download Formatted Report (HTML)",
                            data=html_data,
                            file_name=html_filename,
                            mime=html_mime,
                            help="Downloads a nicely formatted HTML document that can be opened in any browser or printed",
                            key=f"download_html_{summary.get('summary_id', week_date)}"
                        )
                        
                        # Plain text download (original)
                        text_data, text_filename, text_mime = create_formatted_document_download(
                            clean_summary_response(summary.get('summary_text', '')), week_date, creator_name, "text"
                        )
                        st.download_button(
                            label="📄 Download Text Version",
                            data=text_data,
                            file_name=text_filename,
                            mime=text_mime,
                            help="Downloads a formatted text document",
                            key=f"download_text_{summary.get('summary_id', week_date)}"
                        )
                    
                    # Email UND LEADS section button
                    with col2:
                        if st.button(f"📧 Email UND LEADS Section", key=f"email_leads_{summary.get('summary_id', week_date)}"):
                            # Extract UND LEADS section
                            leads_section = extract_und_leads_section(clean_summary_response(summary.get('summary_text', '')))
                            
                            if leads_section and not leads_section.startswith("Could not find UND LEADS") and not leads_section.startswith("No summary text"):
                                # Store in session state for email form
                                st.session_state['email_content'] = {
                                    'subject': f"UND LEADS Summary - Week Ending {week_date}",
                                    'body': f"UND LEADS Summary for Week Ending {week_date}\n\n{leads_section}\n\n---\nGenerated from UND Housing Leadership Reports\nCreated {created_date} by {creator_name}",
                                    'week_date': week_date,
                                    'summary_id': summary.get('summary_id', week_date)
                                }
                                st.rerun()
                            else:
                                st.error(f"⚠️ {leads_section}")
                    
                    # Preview UND LEADS section button  
                    with col3:
                        if st.button(f"👁️ Preview UND LEADS", key=f"preview_leads_{summary.get('summary_id', week_date)}"):
                            leads_section = extract_und_leads_section(clean_summary_response(summary.get('summary_text', '')))
                            if leads_section and not leads_section.startswith("Could not find UND LEADS") and not leads_section.startswith("No summary text"):
                                st.session_state['preview_content'] = {
                                    'content': leads_section,
                                    'week_date': week_date
                                }
                                st.rerun()
                            else:
                                st.error(f"⚠️ {leads_section}")
                    
                    # Show email form if content is ready
                    if ('email_content' in st.session_state and 
                        st.session_state['email_content']['summary_id'] == summary.get('summary_id', week_date)):
                        
                        st.subheader("📧 Send UND LEADS Section")
                        with st.form(f"email_form_{summary.get('summary_id', week_date)}"):
                            to_email = st.text_input("Recipient Email:", placeholder="example@und.edu")
                            subject = st.text_input("Subject:", value=st.session_state['email_content']['subject'])
                            body = st.text_area("Email Body:", value=st.session_state['email_content']['body'], height=200)
                            
                            col_send, col_cancel = st.columns(2)
                            with col_send:
                                if st.form_submit_button("📧 Send Email", type="primary"):
                                    if to_email:
                                        with st.spinner("Sending email..."):
                                            success = send_email(to_email, subject, body)
                                            if success:
                                                st.success(f"✅ UND LEADS section emailed successfully to {to_email}")
                                                # Clear the email content from session state
                                                if 'email_content' in st.session_state:
                                                    del st.session_state['email_content']
                                                time.sleep(2)
                                                st.rerun()
                                            else:
                                                st.error("Failed to send email. Please check email configuration.")
                                    else:
                                        st.error("Please enter a recipient email address.")
                            
                            with col_cancel:
                                if st.form_submit_button("Cancel"):
                                    if 'email_content' in st.session_state:
                                        del st.session_state['email_content']
                                    st.rerun()
                    
                    # Show preview if requested
                    if ('preview_content' in st.session_state and 
                        st.session_state['preview_content']['week_date'] == week_date):
                        
                        st.subheader("👁️ UND LEADS Section Preview")
                        st.markdown(st.session_state['preview_content']['content'])
                        
                        if st.button("Close Preview", key=f"close_preview_{week_date}"):
                            if 'preview_content' in st.session_state:
                                del st.session_state['preview_content']
                            st.rerun()
        
    except Exception as e:
        st.error(f"Failed to fetch summaries: {e}")

def user_manual_page():
    st.title("User Manual")
    st.markdown("""
    This manual describes how to use the Weekly Impact Reporting Tool and explains differences between regular users, supervisors, and admins.

    ## 1. Account & Access
    - Sign Up: Use "Sign Up" in the sidebar. Provide email, full name, position title, and password.
    - Email Confirmation: After sign up you must confirm your email (Supabase confirmation link).
    - Login: Use "Login" in the sidebar. After logging in the sidebar shows pages available to your role.
    - Roles:
      - Regular staff: Submit and view your own reports.
      - Supervisor: Submit/view own reports; view team reports for direct reports; generate and save team summaries (supervisor-scoped).
      - Admin/Director: Full access to all finalized reports and archived weekly summaries.

    ## 2. Report Workflow (Draft → Review → Finalize)
    1. Go to "Submit / Edit Report".
    2. Create or edit the report for the active week (app calculates the current week and grace period).
    3. Fill Core Activities tabs and General Updates:
       - Core Activities: Sections include Students/Stakeholders, Projects, Collaborations, General Job Responsibilities, Staffing, KPIs.
       - For each section add Successes and Challenges; you can add multiple entries.
       - General Updates: Personal check-in, Professional development, Lookahead, and optional Director concerns (see privacy rules below).
    4. Save Draft: Saves your progress as a draft (you can come back later).
    5. Proceed to Review: The app sends your entries to the AI to categorize each item using ASCEND and Guiding NORTH, and to generate a concise individual summary.
    6. Review Screen: Edit categories, adjust the AI summary, confirm well-being score and general updates.
    7. Lock and Submit: Finalizes the report and marks it "finalized". Finalized reports cannot be edited without supervisor/admin assistance.

    ## 3. Privacy and Visibility Rules
    - Row-Level Security (RLS) is enforced: users only see rows they are permitted to view.
    - Regular staff can only view their own reports.
    - Supervisors can view finalized reports for their direct reports only.
    - Director concerns (the "Concerns for Director" field) are shown only to:
      - The report owner, or
      - Admin/Director accounts.
      Supervisors and other staff will not see director concerns for another person's report.
    - Admin/Director accounts have access to all reports and global weekly summaries.

    ## 4. Troubleshooting & Tips
    - If the app shows unexpected behavior, restart the app and check Streamlit logs for exceptions.
    - Missing finalized reports in the supervisor view: Confirm the report is finalized and profile.supervisor_id is set correctly.
    - AI errors: Simplify long or ambiguous entries and retry "Proceed to Review".
    """, unsafe_allow_html=False)

# --- MAIN APPLICATION LOGIC ---
def main():
    # Remove debug messages for production
    # st.write("Debug: App is loading...")
    # st.write("Debug: Supabase connected")
    
    # Check if user is logged in
    if "user" not in st.session_state:
        # Show login/signup forms
        st.sidebar.title("Welcome")
        tab1, tab2 = st.sidebar.tabs(["Login", "Sign Up"])
        
        with tab1:
            login_form()
        
        with tab2:
            signup_form()
        
        # Show welcome message on main page
        st.title("Weekly Impact Reporting Tool")
        st.write("Please login or create an account using the sidebar.")
        return
    
    # User is logged in - fetch profile info
    try:
        user_id = st.session_state["user"].id
        profile_response = supabase.table("profiles").select("*").eq("id", user_id).execute()
        profile_data = getattr(profile_response, "data", None)
        
        if profile_data:
            profile = profile_data[0]
            st.session_state["role"] = profile.get("role", "staff")
            st.session_state["full_name"] = profile.get("full_name", "")
            st.session_state["title"] = profile.get("title", "")
            st.session_state["is_supervisor"] = bool(profile.get("supervisor_id"))
            
            # Check if user is a supervisor
            supervisor_check = supabase.table("profiles").select("id").eq("supervisor_id", user_id).execute()
            if getattr(supervisor_check, "data", []):
                st.session_state["is_supervisor"] = True
    except Exception as e:
        st.error(f"Error fetching profile: {e}")
        return
    
    # Show sidebar with user info and logout
    st.sidebar.title("Navigation")
    st.sidebar.write(f"Welcome, {st.session_state.get('full_name') or st.session_state['user'].email}!")
    st.sidebar.write(f"Role: {st.session_state.get('role', 'staff').title()}")
    
    if st.sidebar.button("Logout"):
        logout()
        st.rerun()
    
    # Build pages based on user role
    pages = {
        "My Profile": profile_page,
        "Submit / Edit Report": submit_and_edit_page,
        "User Manual": user_manual_page
    }
    
    # Add role-specific pages
    if st.session_state.get("role") == "admin":
        pages["Admin Dashboard"] = lambda: dashboard_page(supervisor_mode=False)
        pages["Admin Settings"] = admin_settings_page
    # pages["Weekly Summaries (Email)"] = admin_summaries_page
        pages["📚 Saved Reports Archive"] = saved_reports_page
        pages["Supervisors Section"] = supervisors_section_page
    
    if st.session_state.get("is_supervisor"):
        pages["Supervisor Dashboard"] = lambda: dashboard_page(supervisor_mode=True)
        pages["My Team Summaries"] = supervisor_summaries_page
        pages["📚 Saved Reports Archive"] = saved_reports_page
        pages["Supervisors Section"] = supervisors_section_page
    
    # Page selection
    selected_page = st.sidebar.selectbox("Choose a page:", list(pages.keys()))
    
    # Run selected page
    if selected_page in pages:
        pages[selected_page]()

# Run the main application
if __name__ == "__main__":
    main()
