import os
import requests
import streamlit as st
import time
from datetime import datetime
from src.config import get_secret
from datetime import datetime, date, time as dt_time
import json
import re


def get_roompact_config():
    """Get Roompact API configuration from environment variables or secrets"""
    # Try to get from secrets first - check both possible names
    api_key = get_secret("roompact_api_token")  # Primary name in secrets file
    
    if not api_key:
        api_key = get_secret("roompact_api_key")  # Fallback name
    
    # If not in secrets, try environment variables
    if not api_key:
        api_key = os.environ.get("ROOMPACT_API_TOKEN")
        
    if not api_key:
        api_key = os.environ.get("ROOMPACT_API_KEY")
    
    # Get base URL - allow customization via secrets
    base_url = get_secret("roompact_base_url")
    if not base_url:
        base_url = os.environ.get("ROOMPACT_BASE_URL")
    if not base_url:
        base_url = "https://api.roompact.com/v1"  # Correct URL from official docs
        
    return {
        "api_key": api_key,
        "base_url": base_url
    }

def make_roompact_request(endpoint, params=None):
    """Make authenticated request to Roompact API"""
    config = get_roompact_config()
    if not config["api_key"]:
        return None, "Missing Roompact API key"
        
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Accept": "application/json"
    }
    
    url = f"{config['base_url']}/{endpoint}"
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        # Try to parse JSON
        try:
            return response.json(), None
        except json.JSONDecodeError as e:
            # Show what we actually got back
            error_msg = f"Invalid JSON response from API. Status: {response.status_code}, Content preview: {response.text[:200]}"
            return None, error_msg
            
    except requests.exceptions.RequestException as e:
        return None, str(e)

def fetch_roompact_forms(cursor=None, max_pages=600, target_start_date=None, progress_callback=None):
    """
    Fetch forms data from Roompact API with pagination and optional date-based stopping
    
    Args:
        cursor: Pagination cursor from previous request
        max_pages: Maximum number of pages to fetch (safety limit)
        target_start_date: datetime object. If provided, stop fetching when we reach forms older than this date.
        progress_callback: function(page_num, total_forms, oldest_date, reached_target) to report progress
    
    Returns:
        tuple: (forms_list, error_message) where error_message is None if successful
    """
    try:
        all_forms = []
        page = 0
        has_more = True
        reached_target_date = False
        
        while has_more and page < max_pages and not reached_target_date:
            # CRITICAL: Roompact API /forms endpoint has severe limitations:
            # 1. Does NOT return pagination data (no cursor, no page support)
            # 2. Only returns ~10 most recent forms
            # 3. Does NOT support date filtering
            # This makes historical data retrieval impossible via this endpoint
            
            params = {
                "limit": 100,      # Requested but likely ignored by API
                "per_page": 100,   # Alternative param
                "pageSize": 100,   # Alternative param
            }
            
            if cursor:
                params["cursor"] = cursor
                
            data, error = make_roompact_request("forms", params)
            
            if error:
                print(f"Error fetching page {page}: {error}")
                return [], error
                
            if not data or "data" not in data:
                break
                
            forms = data["data"]
            
            if not forms:
                break
                
            all_forms.extend(forms)
            
            # DEBUG: Print structure of first form to check for ID fields
            if len(all_forms) <= len(forms):  # Only for the first batch
                print(f"DEBUG: First form structure: {forms[0]}")
            
            # Check dates to see if we've gone far enough back
            oldest_date_in_batch = None
            forms_older_than_target = 0
            
            if target_start_date and forms:
                # Convert target_start_date to datetime if it's a date object
                if isinstance(target_start_date, date) and not isinstance(target_start_date, datetime):
                    target_start_date = datetime.combine(target_start_date, datetime.min.time())
                
                # Parse dates to check against target - use current_revision.date for consistency
                for form in forms:
                    current_revision = form.get('current_revision', {})
                    date_str = current_revision.get('date', '')
                    if date_str:
                        try:
                            # Roompact dates are usually ISO format
                            form_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            # Make offset-naive for comparison if needed
                            if form_date.tzinfo and not target_start_date.tzinfo:
                                form_date = form_date.replace(tzinfo=None)
                            
                            if not oldest_date_in_batch or form_date < oldest_date_in_batch:
                                oldest_date_in_batch = form_date
                                
                            if form_date < target_start_date:
                                forms_older_than_target += 1
                                
                        except (ValueError, TypeError):
                            continue
                
                # Stop if most forms in the batch are older than the target date
                # Use 80% threshold to handle out-of-order records while still stopping efficiently
                if len(forms) > 0 and forms_older_than_target >= (len(forms) * 0.8):
                    reached_target_date = True
                    print(f"DEBUG: Reached target date - {forms_older_than_target}/{len(forms)} forms older than {target_start_date}")
            
            # Setup for next page
            # CRITICAL FIX: Roompact API returns pagination in 'links' array, not 'pagination' object
            links = data.get('links', [])
            cursor = None
            
            for link in links:
                if link.get('rel') == 'next':
                    # Extract cursor from URI
                    next_uri = link.get('uri', '')
                    if 'cursor=' in next_uri:
                        cursor = next_uri.split('cursor=')[1].split('&')[0]
                    break
            

            
            # Report progress
            if progress_callback:
                # Handle both signature types for backward compatibility
                try:
                    progress_callback(page + 1, len(all_forms), oldest_date_in_batch, reached_target_date)
                except TypeError:
                    # If callback expects debug_info (from our recent change), pass None
                    progress_callback(page + 1, len(all_forms), oldest_date_in_batch, reached_target_date, None)
            
            # Determine if we should continue
            if cursor:
                has_more = True
            elif len(forms) > 0 and not reached_target_date:
                # If we got data but no cursor, we've reached the end
                has_more = False
            else:
                has_more = False
                
            page += 1
            
            # Rate limiting - be nice to the API
            time.sleep(0.1)  # Reduced slightly since we're doing many small requests
            
        # Deduplicate forms - keep only the latest revision
        # Roompact may return multiple revisions of the same form
        unique_forms = {}
        
        for form in all_forms:
            # Try to find a unique identifier
            form_id = None
            
            # PRIORITIZE form_submission_id as it represents the parent form
            # This stays constant across revisions
            if form.get('form_submission_id'):
                form_id = str(form.get('form_submission_id'))
            elif form.get('id'):
                form_id = str(form.get('id'))
            elif form.get('form_id'):
                form_id = str(form.get('form_id'))
            elif form.get('current_revision', {}).get('id'):
                form_id = str(form.get('current_revision', {}).get('id'))
                
            # If no ID, we can't reliably deduplicate, so keep it (or generate a hash)
            if not form_id:
                # Fallback: use a hash of the content if no ID exists
                import hashlib
                content_str = str(form.get('current_revision', {}))
                form_id = hashlib.md5(content_str.encode()).hexdigest()
                
            # Get the date of this revision
            date_str = form.get('current_revision', {}).get('date', '')
            this_date = datetime.min
            if date_str:
                try:
                    this_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    if this_date.tzinfo:
                        this_date = this_date.replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass
                    
            # Update if this is the first time seeing this ID or if this revision is newer
            if form_id not in unique_forms:
                unique_forms[form_id] = (this_date, form)
            else:
                existing_date, _ = unique_forms[form_id]
                if this_date > existing_date:
                    unique_forms[form_id] = (this_date, form)
        
        # Extract just the form objects
        deduplicated_forms = [form for _, form in unique_forms.values()]
        
        # Sort by date descending (newest first)
        deduplicated_forms.sort(
            key=lambda x: x.get('current_revision', {}).get('date', ''),
            reverse=True
        )
        
        return deduplicated_forms, None
    
    except Exception as e:
        error_msg = f"Error fetching Roompact forms: {str(e)}"
        print(f"Exception in fetch_roompact_forms: {error_msg}")
        return [], error_msg

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
                return [], error
            
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

def parse_event_datetime(datetime_string):
    """
    Enhanced date/time parsing for event scheduling.
    Returns tuple: (date, start_time, end_time)
    """
    try:
        
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

def extract_engagement_quantitative_data(selected_forms):
    """
    Extract complete engagement data from Residence Life Event Submission forms.
    Now handles full semester view (August 22 - December 31) with proper event lifecycle management.
    """
    if not selected_forms:
        return {"success": False, "message": "No forms provided"}
    
    try:
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
        fall_start = datetime(2025, 8, 22).date()
        fall_end = datetime(2025, 12, 31).date()
        
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
                'semester': 'Fall 2025',
                'academic_year': '2025-2026',
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

