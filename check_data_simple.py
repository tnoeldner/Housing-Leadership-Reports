"""
Simple script to check Supabase engagement data without Streamlit
"""
import os
import json
from supabase import create_client, Client

def main():
    # Load Streamlit secrets manually
    secrets_path = r"c:\Users\troy.noeldner\OneDrive - North Dakota University System\Documents\und-reporting-tool\.streamlit\secrets.toml"
    
    if not os.path.exists(secrets_path):
        print("❌ Secrets file not found. Please check Streamlit setup.")
        return
        
    # Read secrets file
    import toml
    try:
        secrets = toml.load(secrets_path)
        supabase_url = secrets["supabase_url"]
        supabase_key = secrets["supabase_key"]
    except Exception as e:
        print(f"❌ Error reading secrets: {e}")
        return
    
    # Initialize Supabase client
    supabase = create_client(supabase_url, supabase_key)
    
    print("🔍 Checking Engagement Table Data")
    print("=" * 50)
    
    try:
        # Query current data focusing on event_approval
        response = supabase.table("engagement_report_data").select(
            "form_submission_id, event_name, event_approval, event_status, hall, purchasing_items, anticipated_attendance"
        ).limit(5).execute()
        
        if response.data:
            print(f"✅ Found {len(response.data)} records")
            print()
            
            for i, record in enumerate(response.data, 1):
                print(f"Record {i}:")
                print(f"  - Form ID: {record.get('form_submission_id', 'N/A')}")
                print(f"  - Event Name: {record.get('event_name', 'N/A')}")
                print(f"  - Event Approval: '{record.get('event_approval', 'N/A')}'")
                print(f"  - Event Status: {record.get('event_status', 'N/A')}")
                print(f"  - Hall: {record.get('hall', 'N/A')}")
                print(f"  - Purchasing Items: {record.get('purchasing_items', 'N/A')}")
                print(f"  - Anticipated Attendance: {record.get('anticipated_attendance', 'N/A')}")
                print()
            
            # Check event_approval values
            print("📊 Event Approval Summary:")
            approval_values = {}
            for record in response.data:
                approval = record.get('event_approval', 'NULL')
                if approval == '':
                    approval = 'EMPTY_STRING'
                elif approval is None:
                    approval = 'NULL'
                approval_values[approval] = approval_values.get(approval, 0) + 1
            
            for value, count in approval_values.items():
                print(f"  - '{value}': {count} records")
                
            # Check one raw form response to see what fields are available
            print("\n🔍 Raw Form Data Sample:")
            raw_response = supabase.table("engagement_report_data").select(
                "form_submission_id, event_name, form_responses"
            ).limit(1).execute()
            
            if raw_response.data:
                record = raw_response.data[0]
                print(f"Event: {record['event_name']}")
                
                try:
                    form_data = json.loads(record['form_responses'])
                    responses = form_data.get('current_revision', {}).get('responses', [])
                    
                    print("Available form fields:")
                    for response in responses:
                        field_label = response.get('field_label', 'Unknown')
                        field_value = response.get('response', 'No response')
                        if 'approval' in field_label.lower() or 'supervisor' in field_label.lower():
                            print(f"  ✅ {field_label}: '{field_value}'")
                        else:
                            print(f"     {field_label}: {type(field_value).__name__}")
                            
                except Exception as e:
                    print(f"  ❌ Could not parse form responses: {e}")
                    
        else:
            print("⚠️  No data found in engagement_report_data table")
            
    except Exception as e:
        print(f"❌ Error checking engagement data: {e}")

if __name__ == "__main__":
    main()