import streamlit as st
from src.database import select_monthly_winners, supabase
import datetime
import json

def monthly_recognition_page():
    """Render the monthly staff recognition winners selection page"""
    st.title("🏆 Monthly Staff Recognition Winners")
    
    # Check if the monthly_staff_recognition table exists
    try:
        supabase.table("monthly_staff_recognition").select("id", count="exact").limit(1).execute()
    except Exception as e:
        error_msg = str(e).lower()
        if "not found" in error_msg or "does not exist" in error_msg or "pgrst205" in error_msg:
            st.warning("""
            **⚠️ Database Setup Required**
            
            The `monthly_staff_recognition` table has not been created yet.
            
            Please copy and paste the SQL below into your Supabase SQL Editor:
            
            ```sql
            CREATE TABLE IF NOT EXISTS monthly_staff_recognition (
                id BIGSERIAL PRIMARY KEY,
                recognition_month DATE NOT NULL UNIQUE,
                ascend_winner JSONB,
                north_winner JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            
            ALTER TABLE monthly_staff_recognition ENABLE ROW LEVEL SECURITY;
            
            CREATE POLICY IF NOT EXISTS "Allow all to view monthly recognition"
            ON monthly_staff_recognition
            FOR SELECT
            USING (true);
            
            CREATE POLICY IF NOT EXISTS "Allow service role to manage monthly recognition"
            ON monthly_staff_recognition
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

    # --- Month and Year Selection ---
    current_year = datetime.date.today().year
    years = list(range(current_year - 5, current_year + 5))
    months = list(range(1, 13))
    month_names = [datetime.date(2024, i, 1).strftime('%B') for i in months]

    col1, col2 = st.columns(2)
    with col1:
        selected_year = st.selectbox("Select Year", options=years, index=years.index(current_year))
    with col2:
        selected_month_name = st.selectbox("Select Month", options=month_names, index=datetime.date.today().month - 1)

    selected_month = month_names.index(selected_month_name) + 1

    # --- Winner Selection Logic ---
    if st.button("Select Monthly Winners"):
        with st.spinner("Determining winners..."):
            result = select_monthly_winners(selected_month, selected_year)

            if not result.get("success"):
                st.error(f"An error occurred: {result.get('message')}")
            elif result.get("status") == "tie":
                st.warning(f"A tie was found for the {result['category']} category.")
                st.write("Please select the winner from the following staff members:")
                
                # Store tied winners in session state
                st.session_state.tied_winners = result['winners']
                st.session_state.tie_category = result['category']
                st.session_state.recognition_month = f"{selected_year}-{selected_month:02d}-01"

                for winner in result['winners']:
                    if st.button(f"Select {winner} as the winner"):
                        st.session_state.manual_winner = winner
                        # Rerun to process manual selection
                        st.rerun()

            else:
                ascend_winner = result.get('ascend_winner')
                north_winner = result.get('north_winner')
                
                if not ascend_winner and not north_winner:
                    st.warning(f"""
                    ⚠️ No staff recognitions found for {selected_month_name} {selected_year}.
                    
                    Please ensure that:
                    1. Weekly staff recognitions have been created for this month
                    2. The recognitions have been saved (visible in "Saved Reports")
                    
                    Once you create weekly recognitions for {selected_month_name}, come back and try again.
                    """)
                else:
                    st.success("Monthly winners selected and saved successfully!")
                    st.balloons()
                    st.subheader("This Month's Winners")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("🌟 ASCEND Winner", ascend_winner or "Not awarded")
                    with col2:
                        st.metric("🧭 NORTH Winner", north_winner or "Not awarded")

    # --- Manual Tie-Breaking Logic ---
    if 'manual_winner' in st.session_state:
        winner = st.session_state.manual_winner
        category = st.session_state.tie_category
        recognition_month = st.session_state.recognition_month
        
        st.write(f"You have selected **{winner}** as the winner for the **{category}** category.")

        # Fetch the full recognition object for the winner
        start_date = recognition_month
        end_date = f"{recognition_month[:7]}-31"
        
        query_col = "ascend_recognition" if category == "ASCEND" else "north_recognition"

        success, data, error = supabase.table("saved_staff_recognition").select(query_col).gte("week_ending_date", start_date).lte("week_ending_date", end_date).execute()
        
        winner_obj = {}
        if success:
            for record in data:
                if record.get(query_col):
                    try:
                        rec = json.loads(record[query_col].strip('\"'))
                        if rec.get('staff_member') == winner:
                            winner_obj = rec
                            break
                    except (json.JSONDecodeError, TypeError):
                        continue

        # Save the manually selected winner
        if category == "ASCEND":
            save_data = {"recognition_month": recognition_month, "ascend_winner": json.dumps(winner_obj)}
        else: # NORTH
            save_data = {"recognition_month": recognition_month, "north_winner": json.dumps(winner_obj)}

        # Check if a record for this month already exists to decide on insert vs update
        try:
            existing_response = supabase.table("monthly_staff_recognition").select("id").eq("recognition_month", recognition_month).execute()
            existing_record = existing_response.data if hasattr(existing_response, 'data') else existing_response
            
            if existing_record and len(existing_record) > 0:
                update_query = supabase.table("monthly_staff_recognition").update(save_data).eq("recognition_month", recognition_month)
            else:
                update_query = supabase.table("monthly_staff_recognition").insert(save_data)

            result = update_query.execute()
            success = result.data is not None if hasattr(result, 'data') else True
            error = None
        except Exception as e:
            success = False
            error = str(e)

        if success:
            st.success(f"Winner for {category} saved successfully!")
            # Clear session state
            del st.session_state.manual_winner
            del st.session_state.tied_winners
            del st.session_state.tie_category
            del st.session_state.recognition_month
            st.rerun()
        else:
            st.error(f"Failed to save the winner: {error}")

    # --- Display Past Winners ---
    st.subheader("Past Monthly Winners")
    try:
        response = supabase.table("monthly_staff_recognition").select("*").order("recognition_month", desc=True).execute()
        if response.data:
            for record in response.data:
                st.markdown(f"#### {datetime.datetime.strptime(record['recognition_month'], '%Y-%m-%d').strftime('%B %Y')}")
                
                ascend_winner_data = json.loads(record.get('ascend_winner', '{}')) if isinstance(record.get('ascend_winner'), str) else record.get('ascend_winner', {})
                north_winner_data = json.loads(record.get('north_winner', '{}')) if isinstance(record.get('north_winner'), str) else record.get('north_winner', {})

                col1, col2 = st.columns(2)
                with col1:
                    if ascend_winner_data and ascend_winner_data.get('staff_member'):
                        with st.expander(f"🌟 ASCEND: {ascend_winner_data['staff_member']}"):
                            st.write(f"**Category:** {ascend_winner_data.get('category', 'N/A')}")
                            st.write(f"**Reasoning:** {ascend_winner_data.get('reasoning', 'N/A')}")
                    else:
                        st.info("No ASCEND winner for this month.")
                
                with col2:
                    if north_winner_data and north_winner_data.get('staff_member'):
                        with st.expander(f"🧭 NORTH: {north_winner_data['staff_member']}"):
                            st.write(f"**Category:** {north_winner_data.get('category', 'N/A')}")
                            st.write(f"**Reasoning:** {north_winner_data.get('reasoning', 'N/A')}")
                    else:
                        st.info("No NORTH winner for this month.")
                st.divider()
        else:
            st.info("No past monthly winners found.")
    except Exception as e:
        st.error(f"Could not load past winners: {e}")
