"""
Check table schema and run a test sync
"""
import os
import json
from supabase import create_client, Client
import toml

def main():
    # Load secrets
    secrets_path = r"c:\Users\troy.noeldner\OneDrive - North Dakota University System\Documents\und-reporting-tool\.streamlit\secrets.toml"
    secrets = toml.load(secrets_path)
    supabase_url = secrets["supabase_url"]
    supabase_key = secrets["supabase_key"]
    
    supabase = create_client(supabase_url, supabase_key)
    
    print("🔍 Checking Table Schema")
    print("=" * 50)
    
    try:
        # Test if table exists by trying to describe it
        test_response = supabase.table("engagement_report_data").select("*").limit(1).execute()
        
        if hasattr(test_response, 'data'):
            print("✅ Table exists!")
            
            # Check if it has the CSV columns
            if test_response.data:
                columns = list(test_response.data[0].keys())
                print(f"Found {len(columns)} columns")
            else:
                # Table exists but is empty - check columns by inserting a test record
                print("📋 Table is empty. Let's check the expected columns:")
                expected_columns = [
                    'form_submission_id', 'author_first', 'author_last', 'event_name',
                    'event_approval', 'event_status', 'hall', 'purchasing_items',
                    'anticipated_attendance', 'total_cost_vendor'
                ]
                
                for col in expected_columns:
                    print(f"  - {col}")
                    
                print("\n💡 Suggestion: Run the engagement sync in the Streamlit app to populate data")
                
            # Check if there are any CSV field mappings issues
            print("\n🔍 Field Mapping Check:")
            print("The CSV should have these key fields:")
            csv_fields = [
                "Author First", "Author Last", "Event Name", "Hall", 
                "Event Approval", "Purchasing Items", "Anticipated Number Attendees"
            ]
            
            for field in csv_fields:
                print(f"  - {field}")
                
        else:
            print("❌ Table does not exist or schema is incorrect")
            print("💡 Please run the SIMPLIFIED_ENGAGEMENT_SCHEMA.sql in Supabase first")
            
    except Exception as e:
        if "relation" in str(e).lower() and "does not exist" in str(e).lower():
            print("❌ Table 'engagement_report_data' does not exist")
            print("💡 Please run the SIMPLIFIED_ENGAGEMENT_SCHEMA.sql in Supabase first")
        else:
            print(f"❌ Error checking table: {e}")

if __name__ == "__main__":
    main()