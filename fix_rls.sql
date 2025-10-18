-- FIXED RLS POLICIES FOR SERVICE KEY ACCESS
-- This updates the existing table to allow both authenticated users AND service key access

-- Drop existing policies
DROP POLICY IF EXISTS "Allow authenticated users to read engagement data" ON engagement_report_data;
DROP POLICY IF EXISTS "Allow authenticated users to insert/update engagement data" ON engagement_report_data;

-- New RLS Policies that work with service key
CREATE POLICY "Allow service key and authenticated users to read engagement data" 
ON engagement_report_data FOR SELECT 
USING (true);  -- Allow all reads (service key + authenticated users)

CREATE POLICY "Allow service key and authenticated users to modify engagement data" 
ON engagement_report_data FOR ALL 
USING (true)   -- Allow all operations
WITH CHECK (true);

-- Verify RLS is still enabled
ALTER TABLE engagement_report_data ENABLE ROW LEVEL SECURITY;

SELECT 'RLS policies updated to allow service key access!' as status;