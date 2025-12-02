import streamlit as st
import json
import re
from google import genai
from google.genai import types
from src.config import get_secret

client = None

def init_ai():
    global client
    api_key = get_secret("GOOGLE_API_KEY")
    if not api_key:
        st.error("❌ Missing Google AI API key. Please check your secrets or environment variables.")
        st.stop()
    try:
        client = genai.Client(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"❌ Google AI API key configuration failed: {e}")
        st.info("Please update your Google AI API key in secrets or environment variables.")
        st.stop()

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
    global client
    if client is None:
        init_ai()
    report_json = json.dumps(items_to_categorize, indent=2)
    prompt = f"""
You are an executive assistant for the Director of Housing & Residence Life at UND. Your task is to synthesize the following individual staff report into a concise summary for the week. Focus on professional development, engagement, successes, and challenges. Use clear, professional language and reference specific activities where possible.

STAFF REPORT DATA:
{report_json}
"""
    try:
        with st.spinner("AI is generating your individual summary..."):
            result = client.generate_content(
                model="gemini-2.5-pro",
                contents=prompt
            )
            summary_text = getattr(result, "text", None)
            if not summary_text or not summary_text.strip():
                return "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."
            return clean_summary_response(summary_text)
    except Exception as e:
        st.info(f"ℹ️ AI fallback used due to error: {e}. You can manually review and adjust summary if needed.")
        return "This week demonstrated continued professional development and engagement with various activities that support student success and departmental goals."
def generate_admin_dashboard_summary(
    selected_date_for_summary,
    reports_text,
    duty_reports_section,
    engagement_reports_section,
    average_score
):
    """Generate the admin dashboard summary using Gemini AI."""
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

{engagement_reports_section}
"""
    global client
    if client is None:
        init_ai()
    with st.spinner("AI is generating the admin dashboard summary..."):
        result = client.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
        response_text = getattr(result, "text", None)
        if not response_text or not response_text.strip():
            return "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."
        return clean_summary_response(response_text)
from google import genai
from google.genai import types
import streamlit as st
import re
from src.config import get_secret

client = None

# Initialize Google Gemini AI using google-genai SDK
def init_ai():
    global client
    api_key = get_secret("GOOGLE_API_KEY")
    if not api_key:
        st.error("❌ Missing Google AI API key. Please check your secrets or environment variables.")
        st.stop()
    try:
        client = genai.Client(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"❌ Google AI API key configuration failed: {e}")
        st.info("Please update your Google AI API key in secrets or environment variables.")
        st.stop()


# Return a list of available Gemini models
def get_gemini_models():
    global client
    if client is None:
        init_ai()
    try:
        models = list(client.list_models())
        return models
    except Exception as e:
        return f"Error listing models: {e}"

# Send a test prompt to Gemini and return the response or error
def gemini_test_prompt(prompt="Hello Gemini, are you working?", model_name="gemini-2.5-pro"):
    global client
    if client is None:
        init_ai()
    try:
        response = client.generate_content(
            model=model_name,
            contents=prompt
        )
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
        global client
        if client is None:
            init_ai()
        with st.spinner(f"AI is analyzing {len(selected_forms)} duty reports..."):
            result = client.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            response_text = getattr(result, "text", None)
            if not response_text or not response_text.strip():
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
Analyze the following form submissions and provide a summary:

{forms_text}

Format the response in clear markdown with headers and bullet points. Focus on actionable insights that help supervisors make informed decisions about their teams and operations.
"""

        # Use the same AI configuration as the rest of the app
        global client
        if client is None:
            init_ai()
        with st.spinner("AI is analyzing form submissions..."):
            result = client.generate_content(
                model="gemini-2.5-pro",
                contents=prompt
            )
            response_text = getattr(result, "text", None)
            if not response_text or not response_text.strip():
                st.info("Prompt sent to AI:")
                st.code(prompt)
                st.info("Input data summary:")
                st.code(forms_text)
                return "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."
            return response_text
            
    except Exception as e:
        return f"Error generating AI summary: {str(e)}"
