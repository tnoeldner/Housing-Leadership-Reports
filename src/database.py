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
    client = create_client(str(url), str(key))
    if access_token:
        client.auth.set_session(access_token, access_token)
    return client

def save_duty_analysis(analysis_data, week_ending_date, created_by_user_id=None):
    """Save a duty analysis report to the database for permanent storage"""
    pass
    

def save_weekly_summary(summary_data, week_ending_date, created_by_user_id=None):
    """Save or update a weekly summary report in the weekly_summaries table."""
    try:
        # Convert to ISO format strings if they're date objects
        start_date = summary_data.get('date_range_start')
        end_date = summary_data.get('date_range_end')
        if hasattr(start_date, 'isoformat'):
            start_date = start_date.isoformat()
        if hasattr(end_date, 'isoformat'):
            end_date = end_date.isoformat()

        # Prepare data for saving
        save_data = {
            'week_ending_date': week_ending_date,
            'report_type': summary_data.get('report_type', 'weekly_summary'),
            'date_range_start': start_date,
            'date_range_end': end_date,
            'reports_analyzed': summary_data.get('reports_analyzed'),
            'total_selected': summary_data.get('total_selected'),
            'analysis_text': summary_data.get('analysis_text'),
            'created_by': created_by_user_id,
            'updated_at': datetime.now().isoformat()
        }

        # Use upsert to insert or update on conflict
        response = supabase.table("weekly_summaries").upsert(save_data, on_conflict="week_ending_date").execute()
        if response.data and isinstance(response.data, list) and len(response.data) > 0:
            saved_id = response.data[0].get('id') if isinstance(response.data[0], dict) else None
            return {
                "success": True,
                "message": f"Weekly summary saved/updated for week ending {week_ending_date}",
                "saved_id": saved_id
            }
        else:
            return {"success": False, "message": "Failed to save weekly summary"}
    except Exception as e:
        return {"success": False, "message": f"Error saving weekly summary: {str(e)}"}
    
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
    """Save a duty analysis report to the database for permanent storage"""
    pass

