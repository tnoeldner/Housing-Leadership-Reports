import smtplib
import email.message
import streamlit as st
import re

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
