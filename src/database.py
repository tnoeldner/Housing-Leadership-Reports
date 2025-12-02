import streamlit as st
from supabase import create_client, Client
import time
from datetime import datetime
import json
from src.config import get_secret, CORE_SECTIONS
from src.utils import extract_upcoming_events

def init_connection():
    """Initialize Supabase connection"""
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    
    # Validate required keys exist
    if not url or not key:
        st.error("❌ Missing Supabase configuration. Please check your secrets or environment variables.")
        st.stop()
    
    return create_client(url, key)

def get_admin_client():
        print("[DEBUG] get_admin_client: Using service role key:", service_key[:8], "...")
    """Get a Supabase client with service role key for admin operations (bypasses RLS)"""
    url = get_secret("SUPABASE_URL")
    service_key = get_secret("SUPABASE_SERVICE_ROLE_KEY")
    
    if not url or not service_key:
        raise Exception("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    
    return create_client(url, service_key)

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


# Initialize the global supabase client (for public queries only)
supabase = init_connection()

def get_user_client():
    """
    Return a Supabase client authenticated as the current session user (using their access token).
    Usage: get_user_client()
    """
    import streamlit as st
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    access_token = st.session_state.get("access_token")
    client = create_client(url, key)
    if access_token:
        client.auth.set_session(access_token, access_token)
    return client

def save_duty_analysis(analysis_data, week_ending_date, created_by_user_id=None, db_client=None):
        print("[DEBUG] save_duty_analysis: client is admin?", getattr(db_client, 'auth', None) is None)
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
        # Use provided db_client or fallback to supabase
        client = db_client if db_client is not None else supabase
        # Check for existing analysis with same week ending date and user
        existing_query = client.table("saved_duty_analyses").select("*").eq("week_ending_date", week_ending_date)
        if created_by_user_id:
            existing_query = existing_query.eq("created_by", created_by_user_id)
        existing_response = existing_query.execute()
        existing_records = existing_response.data if existing_response.data else []
        # Prepare data for saving
        now = datetime.now().isoformat()
        save_data = {
            'week_ending_date': week_ending_date,
            'report_type': report_type,
            'date_range_start': start_date,
            'date_range_end': end_date,
            'reports_analyzed': len(analysis_data['selected_forms']),
            'total_selected': len(analysis_data.get('all_selected_forms', analysis_data['selected_forms'])),
            'analysis_text': analysis_data['summary'],
            'created_by': created_by_user_id,
            'created_at': now,
            'updated_at': now
        }
        print("[DEBUG] save_data to Supabase:", save_data)
        # Attach save_data to result for UI debug
        debug_save_data = save_data.copy()
        
        # Save to database with enhanced duplicate detection
        if existing_records:
            # Record already exists, provide feedback but don't create duplicate
            return {
                "success": True,
                "message": f"Duty analysis for week ending {week_ending_date} already exists (no duplicate created)",
                "existing_id": existing_records[0]['id'],
                "action": "duplicate_prevented",
                "debug_save_data": debug_save_data
            }
        else:
            # No existing record, safe to insert
            try:
                response = client.table("saved_duty_analyses").insert(save_data).execute()
                if response.data:
                    return {
                        "success": True, 
                        "message": f"✅ Duty analysis saved for week ending {week_ending_date}",
                        "saved_id": response.data[0]['id'],
                        "action": "created_new",
                        "debug_save_data": debug_save_data
                    }
                else:
                    return {"success": False, "message": "Failed to save duty analysis - no data returned", "debug_save_data": debug_save_data}
            except Exception as e:
                error_msg = str(e)
                # Check if it's a table doesn't exist error
                if "does not exist" in error_msg or "relation" in error_msg:
                    return {
                        "success": False, 
                        "message": "Database tables not found. Please run the database schema setup first. See database_schema_saved_reports.sql",
                        "debug_save_data": debug_save_data
                    }
                # Check if it's a duplicate key error (fallback)
                elif "duplicate key" in error_msg or "already exists" in error_msg or "violates unique constraint" in error_msg:
                    return {
                        "success": True,
                        "message": f"Duty analysis for week ending {week_ending_date} already exists (no duplicate created)",
                        "action": "duplicate_prevented",
                        "debug_save_data": debug_save_data
                    }
                else:
                    return {"success": False, "message": f"Database error: {error_msg}", "debug_save_data": debug_save_data}
                
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
**Performance Score:** {ascend_rec.get('score', 0)}/4
**Reasoning:** {ascend_rec.get('reasoning', 'No reasoning provided')}

"""
        else:
            recognition_text += "No ASCEND recognition awarded this week.\n\n"
        
        recognition_text += """## 🧭 NORTH Recognition
"""
        
        if north_rec:
            recognition_text += f"""**Recipient:** {north_rec.get('staff_member', 'Unknown')}
**Category:** {north_rec.get('category', 'Unknown')}
**Performance Score:** {north_rec.get('score', 0)}/4
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
            # Use upsert to allow overwriting previous recognition for the same week
            response = supabase.table("saved_staff_recognition").upsert(save_data, on_conflict=["week_ending_date"]).execute()

            if response.data:
                return {
                    "success": True,
                    "message": f"Staff recognition saved/updated for week ending {week_ending_date}",
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
            # Check for RLS error and try fallback
            elif "42501" in error_msg or "row-level security" in error_msg:
                try:
                    # Use admin client to bypass RLS
                    admin_client = get_admin_client()
                    response = admin_client.table("saved_staff_recognition").upsert(save_data, on_conflict=["week_ending_date"]).execute()
                    if response.data:
                        return {
                            "success": True,
                            "message": f"Staff recognition saved/updated for week ending {week_ending_date} (via admin override)",
                            "saved_id": response.data[0]['id']
                        }
                except Exception as admin_e:
                    admin_error_msg = str(admin_e)
                    return {"success": False, "message": f"Error saving staff recognition (admin override failed): {admin_error_msg}"}

                return {"success": False, "message": f"Database error: {error_msg}"}
            else:
                return {"success": False, "message": f"Database error: {error_msg}"}
            
    except Exception as e:
        return {"success": False, "message": f"Error saving staff recognition: {str(e)}"}

def save_staff_performance_scores(all_scores, week_ending_date, created_by_user_id=None):
    """Save individual staff performance scores to the database for historical tracking
    
    Args:
        all_scores: List of dicts with structure:
            [
                {
                    "staff_member": "Name",
                    "staff_member_id": "uuid",
                    "ascend_scores": [{"category": "A - Accountability", "score": 3, "reasoning": "..."}, ...],
                    "north_scores": [{"category": "N - Navigate", "score": 2, "reasoning": "..."}, ...]
                },
                ...
            ]
        week_ending_date: Date string for the week
        created_by_user_id: UUID of the user creating these scores
    
    Returns:
        dict with success status and message
    """
    try:
        # Build batch insert data
        insert_records = []
        
        for staff_data in all_scores:
            staff_name = staff_data.get("staff_member", "Unknown")
            staff_id = staff_data.get("staff_member_id")
            
            # Process ASCEND scores
            for ascend_score in staff_data.get("ascend_scores", []):
                if ascend_score.get("score") is not None:  # Only save if score exists
                    insert_records.append({
                        'week_ending_date': week_ending_date,
                        'staff_member_name': staff_name,
                        'staff_member_id': staff_id,
                        'category_type': 'ASCEND',
                        'category_name': ascend_score.get('category', 'Unknown'),
                        'score': ascend_score.get('score'),
                        'reasoning': ascend_score.get('reasoning', ''),
                        'created_by': created_by_user_id,
                        'created_at': datetime.now().isoformat()
                    })
            
            # Process NORTH scores
            for north_score in staff_data.get("north_scores", []):
                if north_score.get("score") is not None:  # Only save if score exists
                    insert_records.append({
                        'week_ending_date': week_ending_date,
                        'staff_member_name': staff_name,
                        'staff_member_id': staff_id,
                        'category_type': 'NORTH',
                        'category_name': north_score.get('category', 'Unknown'),
                        'score': north_score.get('score'),
                        'reasoning': north_score.get('reasoning', ''),
                        'created_by': created_by_user_id,
                        'created_at': datetime.now().isoformat()
                    })
        
        if not insert_records:
            return {"success": True, "message": "No scores to save (no activities found)", "saved_count": 0}
        
        # Batch insert to database
        try:
            response = supabase.table("staff_recognition_scores").insert(insert_records).execute()
            
            if response.data:
                return {
                    "success": True, 
                    "message": f"Saved {len(insert_records)} individual scores for week ending {week_ending_date}",
                    "saved_count": len(insert_records)
                }
            else:
                return {"success": False, "message": "Failed to save staff scores"}
                
        except Exception as e:
            error_msg = str(e)
            
            # Check if it's a table doesn't exist error
            if "does not exist" in error_msg or "relation" in error_msg:
                return {
                    "success": False, 
                    "message": "Database table not found. Please run database_schema_staff_scores.sql first."
                }
            # Check for RLS error and try fallback
            elif "42501" in error_msg or "row-level security" in error_msg:
                try:
                    # Use admin client to bypass RLS
                    admin_client = get_admin_client()
                    response = admin_client.table("staff_recognition_scores").insert(insert_records).execute()
                    if response.data:
                        return {
                            "success": True, 
                            "message": f"Saved {len(insert_records)} individual scores (via admin override)",
                            "saved_count": len(insert_records)
                        }
                except Exception as admin_e:
                    return {"success": False, "message": f"Error saving scores (admin override failed): {str(admin_e)}"}
                
                return {"success": False, "message": f"Database error: {error_msg}"}
            else:
                return {"success": False, "message": f"Database error: {error_msg}"}
            
    except Exception as e:
        return {"success": False, "message": f"Error saving staff scores: {str(e)}"}


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
