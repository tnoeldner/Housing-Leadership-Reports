from supabase import create_client
from datetime import datetime

SUPABASE_URL = "https://qcktthcerwjzticcjizk.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFja3R0aGNlcndqenRpY2NqaXprIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1OTI2NzEzNCwiZXhwIjoyMDc0ODQzMTM0fQ.2T-9kEYa_KV_WXtt-g8uiUxJqcHL4Ulg9o2PjyyCFus"

# Replace with your actual values
payload = {
    "week_ending_date": "2025-11-30",
    "report_type": "weekly_summary",
    "date_range_start": "2025-11-24",
    "date_range_end": "2025-11-30",
    "reports_analyzed": 46,
    "total_selected": 46,
    "analysis_text": "Test insert from service role script.",
    "created_by": "36164f8f-ac80-4c63-907c-e56aa9f2637a",
    "created_at": datetime.now().isoformat(),
    "updated_at": datetime.now().isoformat()
}

client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

try:
    response = client.table("saved_duty_analyses").insert(payload).execute()
    print("Insert response:", response)
except Exception as e:
    print("Error during insert:", e)