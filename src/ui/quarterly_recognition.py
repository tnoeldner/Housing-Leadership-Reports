import streamlit as st
from src.database import select_quarterly_winners, supabase
import datetime
import json
import time

def get_fiscal_year_for_quarter(month):
    """
    Determine the fiscal year for a given month.
    Fiscal year runs July 1 through June 30.
    Q1 (Jul-Sep): Fiscal Year is the year that started in July
    Q2 (Oct-Dec): Same fiscal year
    Q3 (Jan-Mar): Same fiscal year
    Q4 (Apr-Jun): Same fiscal year (June is last month)
    
    Example: July 2025 = FY2026 (fiscal year that started in July 2025)
    """
    current_year = datetime.date.today().year
    if month >= 7:  # July or later
        return current_year + 1
    else:  # January through June
        return current_year

def get_quarter_from_month(month):
    """
    Determine which quarter a month belongs to.
    Q1: July (7), August (8), September (9)
    Q2: October (10), November (11), December (12)
    Q3: January (1), February (2), March (3)
    Q4: April (4), May (5), June (6)
    """
    if month in [7, 8, 9]:
        return 1
    elif month in [10, 11, 12]:
        return 2
    elif month in [1, 2, 3]:
        return 3
    elif month in [4, 5, 6]:
        return 4
    else:
        return None

def get_quarter_months(quarter):
    """Return the month names for a given quarter."""
    quarters = {
        1: ["July", "August", "September"],
        2: ["October", "November", "December"],
        3: ["January", "February", "March"],
        4: ["April", "May", "June"]
    }
    return quarters.get(quarter, [])

def quarterly_recognition_page():
    """Render the quarterly staff recognition winners selection page"""
    st.title("🏆 Quarterly Staff Recognition Winners")
    
    st.info("""
    **Quarterly Recognition System**
    - **Fiscal Year:** July 1 - June 30
    - **Q1:** July, August, September
    - **Q2:** October, November, December
    - **Q3:** January, February, March
    - **Q4:** April, May, June
    """)
    
    # Check if the quarterly_staff_recognition table exists
    try:
        supabase.table("quarterly_staff_recognition").select("id", count="exact").limit(1).execute()
    except Exception as e:
        error_msg = str(e).lower()
        if "not found" in error_msg or "does not exist" in error_msg or "pgrst205" in error_msg:
            st.warning("""
            **⚠️ Database Setup Required**
            
            The `quarterly_staff_recognition` table has not been created yet.
            
            Please copy and paste the SQL below into your Supabase SQL Editor:
            
            ```sql
            CREATE TABLE IF NOT EXISTS quarterly_staff_recognition (
                id BIGSERIAL PRIMARY KEY,
                fiscal_year INT NOT NULL,
                quarter INT NOT NULL CHECK (quarter >= 1 AND quarter <= 4),
                ascend_winner JSONB,
                north_winner JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(fiscal_year, quarter)
            );
            
            ALTER TABLE quarterly_staff_recognition ENABLE ROW LEVEL SECURITY;
            
            CREATE POLICY IF NOT EXISTS "Allow all to view quarterly recognition"
            ON quarterly_staff_recognition
            FOR SELECT
            USING (true);
            
            CREATE POLICY IF NOT EXISTS "Allow service role to manage quarterly recognition"
            ON quarterly_staff_recognition
            FOR ALL
            USING (true)
            WITH CHECK (true);
            ```
            
            **Steps:**
            1. Log in to your Supabase project
            2. Go to SQL Editor
            3. Paste the SQL above
            4. Click "Run"
            5. Refresh this page
            """)
            st.stop()
        else:
            st.error(f"Database error: {str(e)}")
            st.stop()

    # --- Fiscal Year and Quarter Selection ---
    current_year = datetime.date.today().year
    current_month = datetime.date.today().month
    current_fy = get_fiscal_year_for_quarter(current_month)
    
    years = list(range(current_year - 5, current_year + 5))
    quarters = [1, 2, 3, 4]
    quarter_labels = ["Q1 (Jul-Sep)", "Q2 (Oct-Dec)", "Q3 (Jan-Mar)", "Q4 (Apr-Jun)"]

    col1, col2 = st.columns(2)
    with col1:
        selected_fy = st.selectbox("Select Fiscal Year", options=years, 
                                   index=years.index(current_fy) if current_fy in years else 0,
                                   help="Fiscal Year runs July 1 - June 30")
    with col2:
        selected_quarter = st.selectbox("Select Quarter", options=quarters, 
                                       format_func=lambda q: quarter_labels[q-1],
                                       index=get_quarter_from_month(current_month) - 1 if get_quarter_from_month(current_month) else 0)

    # Display the months included
    quarter_months = get_quarter_months(selected_quarter)
    st.subheader(f"FY{selected_fy} - {', '.join(quarter_months)}")

    # --- Check if we need to display tie-breaking options ---
    if 'tied_winners' in st.session_state and st.session_state.get('tied_winners'):
        st.warning(f"🤝 A tie was found for the {st.session_state.get('tie_category')} category.")
        st.write("Please review the AI-generated summaries below and select the winner:")
        
        # Display AI summaries for each tied candidate
        ai_summaries = st.session_state.get('ai_summaries', {})
        for winner in st.session_state.get('tied_winners', []):
            col1, col2 = st.columns([3, 1])
            with col1:
                with st.expander(f"📊 {winner} - AI Analysis"):
                    summary = ai_summaries.get(winner, "No summary available")
                    st.write(summary)
            with col2:
                st.write("")  # Spacing
                st.write("")  # Spacing
                if st.button(f"Select {winner}", key=f"tie_winner_{winner}"):
                    st.session_state['manual_winner'] = winner
                    st.rerun()

    # --- Winner Selection Logic ---
    if st.button("Select Quarterly Winners") and 'tied_winners' not in st.session_state:
        # Set session state IMMEDIATELY before any complex operations
        st.session_state['button_clicked'] = True
        
        with st.spinner("Determining winners..."):
            st.info(f"Querying for winners in FY{selected_fy} Quarter {selected_quarter} ({', '.join(quarter_months)})")
            
            result = select_quarterly_winners(selected_quarter, selected_fy)

            if not result.get("success"):
                st.error(f"An error occurred: {result.get('message')}")
            elif result.get("status") == "tie":
                st.warning(f"🤝 A tie was found for the {result['category']} category.")
                st.write("AI is analyzing each candidate's performance...")
                
                # Store tied winners AND AI summaries in session state
                st.session_state['tied_winners'] = result['winners']
                st.session_state['tie_category'] = result['category']
                st.session_state['fiscal_year'] = selected_fy
                st.session_state['quarter'] = selected_quarter
                st.session_state['ai_summaries'] = result.get('ai_summaries', {})
                
                print(f"[DEBUG] Winners list: {result['winners']}")
                print(f"[DEBUG] AI Summaries: {result.get('ai_summaries', {})}")
                
                # Rerun to show tie-breaking buttons with AI summaries
                st.rerun()

            else:
                ascend_winner = result.get('ascend_winner')
                north_winner = result.get('north_winner')
                
                if not ascend_winner and not north_winner:
                    debug_info = result.get('debug', {})
                    st.warning(f"""
                    ⚠️ No staff recognitions found for FY{selected_fy} Quarter {selected_quarter} ({', '.join(quarter_months)}).
                    
                    Please ensure that:
                    1. Weekly staff recognitions have been created for these months
                    2. The recognitions have been saved (visible in "Saved Reports")
                    
                    Once you create weekly recognitions for {', '.join(quarter_months)}, come back and try again.
                    """)
                    
                    # Show debug info
                    if debug_info:
                        with st.expander("Debug Information"):
                            st.write(f"**Records found:** {debug_info.get('records_found', 0)}")
                            st.write(f"**ASCEND recognitions:** {debug_info.get('ascend_count', 0)}")
                            st.write(f"**NORTH recognitions:** {debug_info.get('north_count', 0)}")
                            if debug_info.get('records'):
                                st.write("**Record Details:**")
                                for rec in debug_info['records']:
                                    st.write(f"- Week ending {rec['week_ending_date']}: ASCEND={rec['has_ascend']}, NORTH={rec['has_north']}")
                            st.write("**Note:** Check the terminal/console for complete debug output including recent dates in database")
                else:
                    st.success("✅ Quarterly winners selected and saved successfully!")
                    st.balloons()
                    st.subheader(f"FY{selected_fy} Q{selected_quarter} Winners")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if ascend_winner:
                            st.markdown(f"### 🌟 ASCEND Winner: {ascend_winner}")
                            if result.get('ascend_summary'):
                                with st.expander("📊 Why this winner?"):
                                    st.write(result.get('ascend_summary'))
                        else:
                            st.metric("🌟 ASCEND Winner", "Not awarded")
                    
                    with col2:
                        if north_winner:
                            st.markdown(f"### 🧭 NORTH Winner: {north_winner}")
                            if result.get('north_summary'):
                                with st.expander("📊 Why this winner?"):
                                    st.write(result.get('north_summary'))
                        else:
                            st.metric("🧭 NORTH Winner", "Not awarded")

    # --- Manual Tie-Breaking Logic ---
    print(f"[DEBUG] Checking for manual_winner in session_state: {list(st.session_state.keys())}")
    
    if 'manual_winner' in st.session_state and st.session_state.get('manual_winner'):
        print(f"[DEBUG] FOUND manual_winner! Processing tie-breaking save...")
        
        with st.container(border=True):
            st.write("🔍 **TIE-BREAKING LOGIC RUNNING**")
            
            winner = st.session_state.get('manual_winner')
            category = st.session_state.get('tie_category')
            fiscal_year = st.session_state.get('fiscal_year')
            quarter = st.session_state.get('quarter')
            
            st.write(f"You have selected **{winner}** as the winner for the **{category}** category.")
            st.write(f"Saving to FY{fiscal_year} Q{quarter}")

            # Determine the date range for the quarter
            quarter_months_list = get_quarter_months(quarter)
            month_map = {
                'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
                'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
            }
            
            # For Q1 (Jul-Sep), the year is one less than fiscal year
            # For Q2-Q4, the year is fiscal year minus 1 (since FY2026 runs until June 2026)
            if quarter == 1:
                # Q1: July-September, year is FY - 1
                year = fiscal_year - 1
            else:
                # Q2-Q4: October-June, year is FY - 1 (for months before current year)
                # Actually, let me reconsider: if FY2026 is July 2025 - June 2026
                # Q1 is Jul-Sep 2025 (year 2025)
                # Q2 is Oct-Dec 2025 (year 2025)
                # Q3 is Jan-Mar 2026 (year 2026)
                # Q4 is Apr-Jun 2026 (year 2026)
                if quarter in [1, 2]:  # Q1, Q2 are in fiscal year start year
                    year = fiscal_year - 1
                else:  # Q3, Q4 are in fiscal year end year
                    year = fiscal_year
            
            start_month = month_map[quarter_months_list[0]]
            end_month = month_map[quarter_months_list[-1]]
            start_date = f"{year}-{start_month:02d}-01"
            end_date = f"{year}-{end_month:02d}-31"
            
            query_col = "ascend_recognition" if category == "ASCEND" else "north_recognition"

            try:
                # Use admin client to bypass RLS
                from src.database import get_admin_client
                admin = get_admin_client()
                st.write(f"Debug: Admin client created, fetching records...")
                
                response = admin.table("saved_staff_recognition").select(query_col, "week_ending_date").order("week_ending_date").execute()
                data = response.data if response else []
                
                st.write(f"Debug: Got {len(data)} total records, filtering for {query_col}...")
                print(f"[DEBUG] Got {len(data)} total records for {query_col}")
                
                winner_obj = {}
                if data:
                    for record in data:
                        week_date = record.get('week_ending_date', '')
                        # Filter to records in the quarter
                        if week_date and start_date <= week_date <= end_date:
                            rec_data = record.get(query_col)
                            if rec_data:
                                try:
                                    # Handle multiple levels of string escaping
                                    if isinstance(rec_data, str):
                                        cleaned = rec_data.strip()
                                        while cleaned.startswith('"') and cleaned.endswith('"'):
                                            cleaned = cleaned[1:-1]
                                        cleaned = cleaned.replace('\\"', '"').replace('\\\\', '\\')
                                        rec = json.loads(cleaned)
                                    else:
                                        rec = rec_data
                                        
                                    if rec.get('staff_member') == winner:
                                        winner_obj = rec
                                        st.write(f"✅ Found winner object for {winner}")
                                        print(f"[DEBUG] Found winner object: {winner_obj}")
                                        break
                                except (json.JSONDecodeError, TypeError) as e:
                                    print(f"[DEBUG] Error parsing recognition data for {winner}: {e}")
                                    continue
                
                if not winner_obj:
                    st.warning(f"⚠️ No recognition object found for {winner} in quarter - saving empty object")
                    print(f"[DEBUG] No winner_obj found! winner={winner}, category={category}")
                    
            except Exception as e:
                st.error(f"❌ Failed to load winner data: {e}")
                st.error(f"Full error details: {str(e)}")
                print(f"[ERROR] Tie-breaking fetch failed: {e}")
                import traceback
                traceback.print_exc()
                # Continue with empty object so save can be attempted
                winner_obj = {}

            # Save the manually selected winner
            st.write(f"Preparing to save...")
            if category == "ASCEND":
                save_data = {"fiscal_year": fiscal_year, "quarter": quarter, "ascend_winner": json.dumps(winner_obj)}
            else: # NORTH
                save_data = {"fiscal_year": fiscal_year, "quarter": quarter, "north_winner": json.dumps(winner_obj)}
            
            st.write(f"Save data: {save_data}")
            print(f"[DEBUG] Save data prepared: {save_data}")

            # Check if a record for this quarter already exists to decide on insert vs update
            try:
                from src.database import get_admin_client
                admin = get_admin_client()
                
                # Check for existing record
                check_response = admin.table("quarterly_staff_recognition").select("id").eq("fiscal_year", fiscal_year).eq("quarter", quarter).execute()
                existing_record = check_response.data if check_response else []
                
                st.write(f"Checking for existing record for FY{fiscal_year} Q{quarter}: found {len(existing_record) if existing_record else 0}")
                print(f"[DEBUG] Checking for existing record for FY{fiscal_year} Q{quarter}: found {len(existing_record) if existing_record else 0}")
                print(f"[DEBUG] Save data: {save_data}")
                print(f"[DEBUG] Winner object: {winner_obj}")
                
                if existing_record and len(existing_record) > 0:
                    print(f"[DEBUG] Updating existing record for FY{fiscal_year} Q{quarter}")
                    st.write(f"Updating existing record...")
                    result = admin.table("quarterly_staff_recognition").update(save_data).eq("fiscal_year", fiscal_year).eq("quarter", quarter).execute()
                    operation = "UPDATE"
                else:
                    print(f"[DEBUG] Inserting new record for FY{fiscal_year} Q{quarter}")
                    st.write(f"Inserting new record...")
                    result = admin.table("quarterly_staff_recognition").insert(save_data).execute()
                    operation = "INSERT"
                
                print(f"[DEBUG] {operation} result type: {type(result)}")
                print(f"[DEBUG] {operation} result: {result}")
                if hasattr(result, 'data'):
                    print(f"[DEBUG] {operation} result.data: {result.data}")
                if hasattr(result, 'error'):
                    print(f"[DEBUG] {operation} result.error: {result.error}")
                
                st.write(f"Save result type: {type(result)}")
                
                # Check success - be more lenient about what counts as success
                success = result is not None
                if success:
                    st.success(f"✅ Winner for {category} saved successfully!")
                    st.write(f"Category={category}, Winner={winner}, FY={fiscal_year}, Q={quarter}")
                    # Clear session state
                    if 'manual_winner' in st.session_state:
                        del st.session_state.manual_winner
                    if 'tied_winners' in st.session_state:
                        del st.session_state.tied_winners
                    if 'tie_category' in st.session_state:
                        del st.session_state.tie_category
                    if 'fiscal_year' in st.session_state:
                        del st.session_state.fiscal_year
                    if 'quarter' in st.session_state:
                        del st.session_state.quarter
                    time.sleep(1)  # Give user time to see success message
                    st.rerun()
                else:
                    st.error(f"❌ Failed to save the winner. Result was None/empty.")
                    print(f"[ERROR] Save returned None/empty")
            except Exception as e:
                st.error(f"❌ Failed to save the winner: {e}")
                print(f"[ERROR] Tie-breaking save failed: {e}")
                import traceback
                traceback.print_exc()

    # --- Display Past Winners ---
    st.subheader("Past Quarterly Winners")
    try:
        response = supabase.table("quarterly_staff_recognition").select("*").order("fiscal_year", desc=True).order("quarter", desc=True).execute()
        if response.data:
            for record in response.data:
                st.markdown(f"#### FY{record['fiscal_year']} - Q{record['quarter']}")
                
                ascend_winner_data = json.loads(record.get('ascend_winner', '{}')) if isinstance(record.get('ascend_winner'), str) else record.get('ascend_winner', {})
                north_winner_data = json.loads(record.get('north_winner', '{}')) if isinstance(record.get('north_winner'), str) else record.get('north_winner', {})

                col1, col2 = st.columns(2)
                with col1:
                    if ascend_winner_data and ascend_winner_data.get('staff_member'):
                        with st.expander(f"🌟 ASCEND: {ascend_winner_data['staff_member']}"):
                            st.write(f"**Category:** {ascend_winner_data.get('category', 'N/A')}")
                            st.write(f"**Reasoning:** {ascend_winner_data.get('reasoning', 'N/A')}")
                    else:
                        st.info("No ASCEND winner for this quarter.")
                
                with col2:
                    if north_winner_data and north_winner_data.get('staff_member'):
                        with st.expander(f"🧭 NORTH: {north_winner_data['staff_member']}"):
                            st.write(f"**Category:** {north_winner_data.get('category', 'N/A')}")
                            st.write(f"**Reasoning:** {north_winner_data.get('reasoning', 'N/A')}")
                    else:
                        st.info("No NORTH winner for this quarter.")
                st.divider()
        else:
            st.info("No past quarterly winners found.")
    except Exception as e:
        st.error(f"Could not load past winners: {e}")
