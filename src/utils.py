import os
import base64
import re
from datetime import datetime, timedelta, date, time as dt_time
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    # Fallback for older Python versions
    from datetime import timezone
    def ZoneInfo(tz):
        if tz == "US/Central":
            return timezone.utc  # Simplified fallback
        return timezone.utc
import streamlit as st
from src.config import ASCEND_VALUES, NORTH_VALUES
from src.ai import clean_summary_response

def get_deadline_settings(supabase_client):
    """Get the current deadline configuration from admin settings"""
    try:
        # Try to get from database first (when table exists)
        settings_response = supabase_client.table("admin_settings").select("*").eq("setting_name", "report_deadline").execute()
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

def calculate_deadline_info(now, supabase_client):
    """Calculate deadline information based on current time and settings"""
    deadline_config = get_deadline_settings(supabase_client)
    
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

def get_logo_base64():
    """Convert logo image to base64 for embedding in HTML"""
    try:
        # Get the directory where this script is located
        # Since this is in src/utils.py, we need to go up one level to root
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Look for logo in various possible locations
        possible_paths = [
            os.path.join(script_dir, "assets", "und_housing_logo.jpg"),
            os.path.join(script_dir, "assets", "und_housing_logo.png"),
            os.path.join(script_dir, "und_housing_logo.jpg"),
            os.path.join(script_dir, "und_housing_logo.png"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, "rb") as img_file:
                    img_data = base64.b64encode(img_file.read()).decode()
                    ext = path.split('.')[-1].lower()
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
