"""Debug script to check what recognitions exist for January 2026"""
import sys
sys.path.insert(0, 'c:\\weeklyleadershipreports')

from src.database import supabase
import json

# Query all recognitions for January 2026
try:
    response = supabase.table("saved_staff_recognition").select("*").order("week_ending_date").execute()
    
    print(f"Total records in database: {len(response.data) if response.data else 0}\n")
    
    if response.data:
        # Find records that might be for January 2026
        january_records = []
        for record in response.data:
            date_str = record.get('week_ending_date', '')
            print(f"Date: {date_str}, ASCEND: {bool(record.get('ascend_recognition'))}, NORTH: {bool(record.get('north_recognition'))}")
            
            # Check if this is January 2026
            if date_str.startswith('2026-01'):
                january_records.append(record)
        
        print(f"\n\n=== January 2026 Records ===")
        print(f"Found {len(january_records)} records for January 2026\n")
        
        for i, record in enumerate(january_records):
            print(f"\nRecord {i+1}:")
            print(f"  Week Ending: {record.get('week_ending_date')}")
            
            if record.get('ascend_recognition'):
                try:
                    ascend_data = record['ascend_recognition']
                    if isinstance(ascend_data, str):
                        # Try to parse it
                        cleaned = ascend_data.strip()
                        while cleaned.startswith('"') and cleaned.endswith('"'):
                            cleaned = cleaned[1:-1]
                        cleaned = cleaned.replace('\\"', '"').replace('\\\\', '\\')
                        ascend_obj = json.loads(cleaned)
                    else:
                        ascend_obj = ascend_data
                    print(f"  ASCEND: {ascend_obj.get('staff_member')} - {ascend_obj.get('category')}")
                except Exception as e:
                    print(f"  ASCEND: Error parsing - {e}")
            
            if record.get('north_recognition'):
                try:
                    north_data = record['north_recognition']
                    if isinstance(north_data, str):
                        # Try to parse it
                        cleaned = north_data.strip()
                        while cleaned.startswith('"') and cleaned.endswith('"'):
                            cleaned = cleaned[1:-1]
                        cleaned = cleaned.replace('\\"', '"').replace('\\\\', '\\')
                        north_obj = json.loads(cleaned)
                    else:
                        north_obj = north_data
                    print(f"  NORTH: {north_obj.get('staff_member')} - {north_obj.get('category')}")
                except Exception as e:
                    print(f"  NORTH: Error parsing - {e}")

except Exception as e:
    print(f"Error querying database: {e}")
    import traceback
    traceback.print_exc()
