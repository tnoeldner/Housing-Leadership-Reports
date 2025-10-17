# Engagement Database Debug Guide

## Issue: Save shows success but no data in table

The save function is returning "✅ Data already exists in database (no duplicates created)" but the `engagement_report_data` table in Supabase is empty.

## Likely Causes

1. **Constraint Issue**: The unique constraint is preventing insert due to NULL values or mismatched field names
2. **Silent Failure**: The duplicate key error is being triggered incorrectly
3. **Data Issues**: Some required fields might be NULL when they should have values

## Enhanced Debugging

I've updated the `save_engagement_data()` function to:

✅ **Better Error Messages**: More specific success/failure indicators  
✅ **Existence Check**: When duplicate error occurs, verify if data actually exists  
✅ **Detailed Logging**: Show exactly what constraint is failing  

## Quick Debug Steps

### 1. Check Table Structure in Supabase
```sql
-- Run in Supabase SQL Editor to see table structure
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'engagement_report_data';
```

### 2. Check Constraints
```sql
-- See what constraints exist
SELECT constraint_name, constraint_type 
FROM information_schema.table_constraints 
WHERE table_name = 'engagement_report_data';
```

### 3. Check for Existing Data
```sql
-- See if there's any data at all
SELECT COUNT(*) as total_records FROM engagement_report_data;
SELECT * FROM engagement_report_data LIMIT 5;
```

### 4. Test Manual Insert
```sql
-- Try inserting a simple test record
INSERT INTO engagement_report_data (
    event_title, 
    form_submission_id, 
    date_range_start, 
    date_range_end
) VALUES (
    'Test Event', 
    'TEST-001', 
    '2024-01-01', 
    '2024-01-07'
);
```

## Expected Behavior After Fix

When you try to save engagement data now, you should see one of these messages:

✅ **"✅ Successfully saved X engagement records to database"** - Data was actually saved  
⚠️ **"✅ Data already exists in database - found X existing records"** - Data already there (verified)  
❌ **"⚠️ Duplicate key error but no existing data found"** - Constraint issue (needs fixing)  
❌ **"❌ Database error: [details]"** - Other database problem  

## Next Steps

1. **Try saving again** - You should now get a more specific error message
2. **Run the debug SQL queries** above to understand the table state
3. **Check the constraint fields** to see if they're causing the issue

The enhanced error handling will tell us exactly what's happening! 🔍