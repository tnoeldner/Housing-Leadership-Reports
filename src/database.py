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
try:
    supabase = init_connection()
except Exception as e:
    print(f"[WARN] Failed to initialize Supabase connection at module load: {e}")
    supabase = None

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
        # Ensure week_ending_date is a string
        if hasattr(week_ending_date, 'isoformat'):
            week_ending_date = week_ending_date.isoformat()
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
        # Ensure week_ending_date is a string
        if hasattr(week_ending_date, 'isoformat'):
            week_ending_date = week_ending_date.isoformat()
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
        
        # Ensure week_ending_date is a string
        if hasattr(week_ending_date, 'isoformat'):
            week_ending_date = week_ending_date.isoformat()
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


def select_monthly_winners(month, year):
    """
    Selects the monthly winners for ASCEND and NORTH recognition based on the number of weekly recognitions.
    """
    try:
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-31"

        print(f"\n[DEBUG] select_monthly_winners called for {year}-{month:02d}")
        print(f"[DEBUG] Date range: {start_date} to {end_date}")

        # First, let's see what dates actually exist in the database
        success_all, data_all, error_all = safe_db_query(
            supabase.table("saved_staff_recognition")
            .select("week_ending_date")
            .order("week_ending_date", desc=True)
            .limit(50),
            "Fetching recent dates to check what exists"
        )
        
        if success_all and data_all:
            print(f"[DEBUG] Recent dates in database: {[r.get('week_ending_date') for r in data_all[:10]]}")
            print(f"[DEBUG] Total records found in limit(50): {len(data_all)}")
        else:
            print(f"[DEBUG] Failed to fetch recent dates: {error_all}")

        # Try using admin client to bypass RLS
        print(f"[DEBUG] Attempting to fetch all records with admin client...")
        try:
            admin = get_admin_client()
            response = admin.table("saved_staff_recognition").select("week_ending_date, ascend_recognition, north_recognition").order("week_ending_date").execute()
            data_all_records = response.data if response else None
            if data_all_records:
                print(f"[DEBUG] Admin client returned {len(data_all_records)} total records")
                print(f"[DEBUG] Recent dates from admin: {[r.get('week_ending_date') for r in data_all_records[-10:]]}")
            else:
                print(f"[DEBUG] Admin client returned no data")
        except Exception as admin_error:
            print(f"[DEBUG] Admin client failed: {admin_error}")
            # Fallback to regular client
            success, data_all_records, error = safe_db_query(
                supabase.table("saved_staff_recognition")
                .select("week_ending_date, ascend_recognition, north_recognition")
                .order("week_ending_date"),
                "Fetching all recognitions"
            )
            print(f"[DEBUG] Regular client success: {success}, records: {len(data_all_records) if data_all_records else 0}")
            if not success:
                print(f"[DEBUG] Query failed: {error}")
                return {"success": False, "message": error}

        if not data_all_records:
            print(f"[DEBUG] No records returned at all!")
            return {
                "success": True,
                "status": "success",
                "ascend_winner": None,
                "north_winner": None,
                "debug": {
                    "records_found": 0,
                    "ascend_count": 0,
                    "north_count": 0,
                    "error": "No records found in database - check if saved_staff_recognition table exists and has data"
                }
            }

        # Filter to only records in the specified month
        data = []
        for record in data_all_records:
            week_date = record.get('week_ending_date', '')
            if week_date and start_date <= week_date <= end_date:
                data.append(record)
        
        # Debug: Check how many records were found
        print(f"[DEBUG] Found {len(data) if data else 0} records for {start_date} to {end_date}")
        if data:
            for i, record in enumerate(data):
                print(f"[DEBUG]   Record {i+1}: week_ending_date={record.get('week_ending_date')}, has_ascend={bool(record.get('ascend_recognition'))}, has_north={bool(record.get('north_recognition'))}")
        else:
            print(f"[DEBUG] No records in date range {start_date} to {end_date}")
            print(f"[DEBUG] Total records in DB: {len(data_all_records)}")

        ascend_counts = {}
        north_counts = {}

        for record in data or []:
            # Helper function to safely parse JSON with multiple levels of escaping
            def parse_json_value(value):
                """Parse JSON handling multiple levels of escaping"""
                if isinstance(value, dict):
                    return value
                if not isinstance(value, str):
                    return None
                
                # Remove surrounding quotes if present
                value = value.strip()
                while value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                
                # Handle escaped quotes
                value = value.replace('\\"', '"')
                value = value.replace('\\\\', '\\')
                
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return None
            
            # Process ASCEND recognition
            if record.get('ascend_recognition'):
                try:
                    ascend_rec = parse_json_value(record['ascend_recognition'])
                    if ascend_rec:
                        staff_member = ascend_rec.get('staff_member')
                        if staff_member:
                            ascend_counts[staff_member] = ascend_counts.get(staff_member, 0) + 1
                            print(f"[DEBUG] ASCEND: {staff_member} count = {ascend_counts[staff_member]}")
                    else:
                        print(f"[DEBUG] Could not parse ASCEND data: {record.get('ascend_recognition')[:100]}")
                except Exception as e:
                    print(f"[DEBUG] Error parsing ASCEND: {str(e)}")
                    pass

            # Process NORTH recognition
            if record.get('north_recognition'):
                try:
                    north_rec = parse_json_value(record['north_recognition'])
                    if north_rec:
                        staff_member = north_rec.get('staff_member')
                        if staff_member:
                            north_counts[staff_member] = north_counts.get(staff_member, 0) + 1
                            print(f"[DEBUG] NORTH: {staff_member} count = {north_counts[staff_member]}")
                    else:
                        print(f"[DEBUG] Could not parse NORTH data: {record.get('north_recognition')[:100]}")
                except Exception as e:
                    print(f"[DEBUG] Error parsing NORTH: {str(e)}")
                    pass
        
        print(f"[DEBUG] ASCEND counts: {ascend_counts}")
        print(f"[DEBUG] NORTH counts: {north_counts}")
        
        # Determine winners
        ascend_winner = max(ascend_counts, key=ascend_counts.get) if ascend_counts else None
        north_winner = max(north_counts, key=north_counts.get) if north_counts else None

        print(f"[DEBUG] Determined winners - ASCEND: {ascend_winner}, NORTH: {north_winner}")

        # If no winners found, return early with diagnostic info
        if not ascend_winner and not north_winner:
            print(f"[DEBUG] No winners determined - counts are empty")
            return {
                "success": True,
                "status": "success",
                "ascend_winner": None,
                "north_winner": None,
                "debug": {
                    "records_found": len(data) if data else 0,
                    "ascend_count": len(ascend_counts),
                    "north_count": len(north_counts),
                    "records": [{"week_ending_date": r.get('week_ending_date'), "has_ascend": bool(r.get('ascend_recognition')), "has_north": bool(r.get('north_recognition'))} for r in (data or [])]
                }
            }
        
        # Check for ties
        if ascend_winner and list(ascend_counts.values()).count(ascend_counts[ascend_winner]) > 1:
            tied_winners = [k for k, v in ascend_counts.items() if v == ascend_counts[ascend_winner]]
            return {"success": True, "status": "tie", "category": "ASCEND", "winners": tied_winners}

        if north_winner and list(north_counts.values()).count(north_counts[north_winner]) > 1:
            tied_winners = [k for k, v in north_counts.items() if v == north_counts[north_winner]]
            return {"success": True, "status": "tie", "category": "NORTH", "winners": tied_winners}

        # Save winners to the database
        recognition_month = f"{year}-{month:02d}-01"
        
        # Fetch the full recognition object for the winners
        ascend_winner_obj = {}
        if ascend_winner:
            for record in data or []:
                if record.get('ascend_recognition'):
                    try:
                        ascend_data = record['ascend_recognition']
                        # Check if it's already a dict or needs JSON parsing
                        if isinstance(ascend_data, dict):
                            ascend_rec = ascend_data
                        else:
                            # Remove surrounding quotes and handle escaping
                            cleaned = ascend_data.strip()
                            while cleaned.startswith('"') and cleaned.endswith('"'):
                                cleaned = cleaned[1:-1]
                            cleaned = cleaned.replace('\\"', '"').replace('\\\\', '\\')
                            ascend_rec = json.loads(cleaned)
                        
                        if ascend_rec.get('staff_member') == ascend_winner:
                            ascend_winner_obj = ascend_rec
                            break
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        continue
        
        north_winner_obj = {}
        if north_winner:
            for record in data or []:
                if record.get('north_recognition'):
                    try:
                        north_data = record['north_recognition']
                        # Check if it's already a dict or needs JSON parsing
                        if isinstance(north_data, dict):
                            north_rec = north_data
                        else:
                            # Remove surrounding quotes and handle escaping
                            cleaned = north_data.strip()
                            while cleaned.startswith('"') and cleaned.endswith('"'):
                                cleaned = cleaned[1:-1]
                            cleaned = cleaned.replace('\\"', '"').replace('\\\\', '\\')
                            north_rec = json.loads(cleaned)
                        
                        if north_rec.get('staff_member') == north_winner:
                            north_winner_obj = north_rec
                            break
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        continue

        save_data = {
            "recognition_month": recognition_month,
            "ascend_winner": json.dumps(ascend_winner_obj),
            "north_winner": json.dumps(north_winner_obj)
        }

        # Check if a record for this month already exists
        check_success, existing_records, check_error = safe_db_query(
            supabase.table("monthly_staff_recognition")
            .select("id")
            .eq("recognition_month", recognition_month),
            "Checking for existing monthly winner record"
        )

        if check_success and existing_records and len(existing_records) > 0:
            # Record exists, update it
            success, _, error = safe_db_query(
                supabase.table("monthly_staff_recognition")
                .update(save_data)
                .eq("recognition_month", recognition_month),
                "Updating monthly winners"
            )
        else:
            # Record doesn't exist, insert it
            success, _, error = safe_db_query(
                supabase.table("monthly_staff_recognition").insert(save_data),
                "Saving monthly winners"
            )

        if not success:
            return {"success": False, "message": error}

        return {"success": True, "status": "success", "ascend_winner": ascend_winner, "north_winner": north_winner}

    except Exception as e:
        return {"success": False, "message": f"An error occurred: {str(e)}"}

def get_all_staff_names():
    """Fetches all unique staff member names from the database."""
    try:
        # Fetch all staff members from the database
        success, data, error = safe_db_query(
            supabase.table("saved_staff_recognition").select("ascend_recognition, north_recognition"),
            "Fetching all staff names"
        )

        if not success:
            return {"success": False, "message": error}

        staff_names = set()
        for record in data:
            # Process ASCEND recognition
            if record.get('ascend_recognition'):
                try:
                    ascend_rec = json.loads(record['ascend_recognition'].strip('\"'))
                    staff_member = ascend_rec.get('staff_member')
                    if staff_member:
                        staff_names.add(staff_member)
                except (json.JSONDecodeError, TypeError):
                    pass  # Ignore malformed JSON

            # Process NORTH recognition
            if record.get('north_recognition'):
                try:
                    north_rec = json.loads(record['north_recognition'].strip('\"'))
                    staff_member = north_rec.get('staff_member')
                    if staff_member:
                        staff_names.add(staff_member)
                except (json.JSONDecodeError, TypeError):
                    pass  # Ignore malformed JSON

        return {"success": True, "data": list(staff_names), "message": "All staff names fetched successfully"}

    except Exception as e:
        return {"success": False, "message": f"Error fetching all staff names: {str(e)}"}
