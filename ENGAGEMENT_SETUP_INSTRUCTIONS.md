# Engagement Analysis Database Setup Instructions

## Problem
The engagement analysis feature shows this error when trying to save data:
```
❌ Save failed: Error saving engagement data: {'message': 'there is no unique or exclusion constraint matching the ON CONFLICT specification', 'code': '42P10'}
```

## Solution
The database tables need to be created. Here's how to fix it:

### Step 1: Access Supabase SQL Editor
1. Go to your Supabase project dashboard
2. Navigate to the SQL Editor (left sidebar)
3. Create a new query

### Step 2: Run the Database Schema
1. Open the file `database_schema_engagement_reports.sql` in this project
2. Copy the entire contents of that file
3. Paste it into the Supabase SQL Editor
4. Click "Run" to execute the SQL

### Step 3: Verify Table Creation
After running the schema, you should see two new tables created:
- `engagement_report_data` - stores quantitative data from event forms
- `saved_engagement_analyses` - stores completed analysis reports

### Step 4: Test the Feature
1. Go back to your app
2. Navigate to Supervisors → Engagement Analysis
3. Select some forms and generate an analysis
4. Try saving the quantitative data - it should now work!

## What the Schema Creates
- **Tables**: Two tables with proper indexes and constraints
- **Security**: Row Level Security (RLS) policies for data protection
- **Constraints**: Unique constraints to prevent duplicate data
- **Indexes**: Optimized indexes for fast querying

## Features Now Available
✅ Save quantitative engagement data for historical analysis  
✅ Save weekly engagement analysis reports  
✅ Extract upcoming events from forms  
✅ Integration with admin weekly summaries  
✅ Archive of saved engagement analyses  

## Troubleshooting
If you still get errors after running the schema:
1. Check that you're connected to the correct Supabase project
2. Verify you have admin/owner permissions on the project
3. Refresh your app page after creating the tables
4. Check the Supabase logs for any additional error details

The save functions have been updated with better error handling, so you'll get clearer error messages if anything is still wrong.