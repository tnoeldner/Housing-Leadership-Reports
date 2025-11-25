import streamlit as st
from datetime import datetime
import json
import pandas as pd
import io
from google import genai
from src.database import save_staff_recognition, save_staff_performance_scores, supabase
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from datetime import timezone as ZoneInfo

def load_rubrics():
    """Load ASCEND and NORTH rubrics from markdown files"""
    rubrics = {}
    try:
        with open('tests/ASCEND_context.md', 'r', encoding='utf-8') as f:
            rubrics['ascend'] = f.read()
        with open('tests/NORTH_contexts.md', 'r', encoding='utf-8') as f:
            rubrics['north'] = f.read()
        
        # Create a custom evaluation prompt for 1-4 scale
        rubrics['evaluation_prompt'] = """You are evaluating staff performance for UND Housing & Residence Life.
        
Review the staff performance data and the ASCEND and NORTH rubrics provided below.
Select ONE staff member who best exemplifies an ASCEND pillar and ONE who best exemplifies a NORTH pillar.

IMPORTANT: Use the 1-4 rating scale defined in the rubrics:
- 1 = Needs Improvement
- 2 = Meets Expectations  
- 3 = Exceeds Expectations
- 4 = Outstanding

Provide specific reasoning based on their activities and alignment with the criteria."""
        return rubrics
    except FileNotFoundError as e:
        st.error(f"Context file not found: {e}")
        return None

def evaluate_staff_performance(weekly_reports, rubrics):
    """Use AI to evaluate staff performance against ASCEND and NORTH criteria"""
    if not weekly_reports or not rubrics:
        return None
    
        from src.config import get_secret
        api_key = get_secret("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
    
    # Build staff performance data
    staff_data = []
    for report in weekly_reports:
        staff_info = {
            "name": report.get('team_member', 'Unknown'),
            "user_id": report.get('user_id'),  # Include user_id for database linking
            "well_being_score": report.get('well_being_rating', 0),
            "activities": []
        }
        
        report_body = report.get("report_body", {})
        for section_key, section_data in report_body.items():
            if section_data:
                for success in section_data.get("successes", []):
                    staff_info["activities"].append({
                        "type": "success",
                        "text": success.get("text", ""),
                        "ascend_category": success.get("ascend_category", "N/A"),
                        "north_category": success.get("north_category", "N/A")
                    })
        staff_data.append(staff_info)
    
    staff_json = json.dumps(staff_data, indent=2)
    
    prompt = f"""
{rubrics['evaluation_prompt']}

ASCEND Rubric:
{rubrics['ascend']}

NORTH Rubric:
{rubrics['north']}

Staff Performance Data:
{staff_json}

CRITICAL INSTRUCTIONS FOR SCORING:

IMPORTANT: You must provide TWO outputs:
1. Top performers (one for ASCEND, one for NORTH)
2. ALL staff scores across ALL categories where they have activities

For each staff member, evaluate them ONLY in the ASCEND and NORTH categories where they have logged activities.
If a staff member has NO activities in a category, do NOT include that category in their scores (leave it out entirely).

Return JSON in this EXACT format with scores between 1-4 ONLY:
{{
  "top_performers": {{
    "ascend_recognition": {{
      "staff_member": "Full Name",
      "category": "ASCEND Category Letter - Full Name", 
      "reasoning": "Specific reasoning based on their activities",
      "score": <NUMBER BETWEEN 1 AND 4>
    }},
    "north_recognition": {{
      "staff_member": "Full Name", 
      "category": "NORTH Pillar Letter - Full Name",
      "reasoning": "Specific reasoning based on their activities",
      "score": <NUMBER BETWEEN 1 AND 4>
    }}
  }},
  "all_staff_scores": [
    {{
      "staff_member": "Full Name",
      "ascend_scores": [
        {{"category": "A - Accountability", "score": 3, "reasoning": "Brief reasoning"}},
        {{"category": "S - Service Excellence", "score": 4, "reasoning": "Brief reasoning"}}
      ],
      "north_scores": [
        {{"category": "N - Navigate Change", "score": 2, "reasoning": "Brief reasoning"}},
        {{"category": "O - Own Your Growth", "score": 3, "reasoning": "Brief reasoning"}}
      ]
    }}
  ]
}}

REMINDER: 
"""

    try:
        from src.config import get_secret
        api_key = get_secret("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
        
        # Debug: Show prompt and raw response
        with st.expander("🕵️ Debug: AI Input & Output"):
            st.subheader("Prompt Sent to AI")
            st.code(prompt, language="text")
            st.subheader("Raw AI Response")
            st.code(response.text, language="json")
            
        clean_response = response.text.strip().replace("```json", "").replace("```", "")
        result = json.loads(clean_response)
        
        # Clamp scores to 1-4 range for top performers
        top_performers = result.get("top_performers", {})
        for rec_key in ["ascend_recognition", "north_recognition"]:
            rec = top_performers.get(rec_key, {})
            if isinstance(rec, dict) and "score" in rec:
                try:
                    score_val = int(rec["score"])
                except Exception:
                    score_val = 0
                rec["score"] = max(1, min(4, score_val))
        
        # Clamp scores for all staff scores
        all_staff_scores = result.get("all_staff_scores", [])
        for staff_score in all_staff_scores:
            # Add user_id from original staff_data
            staff_name = staff_score.get("staff_member", "")
            matching_staff = next((s for s in staff_data if s["name"] == staff_name), None)
            if matching_staff:
                staff_score["staff_member_id"] = matching_staff.get("user_id")
            
            # Clamp ASCEND scores
            for ascend_score in staff_score.get("ascend_scores", []):
                if "score" in ascend_score and ascend_score["score"] is not None:
                    try:
                        score_val = int(ascend_score["score"])
                    except Exception:
                        score_val = None
                    if score_val is not None:
                        ascend_score["score"] = max(1, min(4, score_val))
            
            # Clamp NORTH scores
            for north_score in staff_score.get("north_scores", []):
                if "score" in north_score and north_score["score"] is not None:
                    try:
                        score_val = int(north_score["score"])
                    except Exception:
                        score_val = None
                    if score_val is not None:
                        north_score["score"] = max(1, min(4, score_val))
        
        # Return both top performers and all scores
        return {
            "ascend_recognition": top_performers.get("ascend_recognition", {}),
            "north_recognition": top_performers.get("north_recognition", {}),
            "all_staff_scores": all_staff_scores
        }
    except Exception as e:
        st.error(f"AI evaluation error: {e}")
        return None


def staff_recognition_page():
    """Standalone page for weekly staff recognition.
    Handles generation, cache clearing, and display of recognition results.
    """
    st.title("🏆 Weekly Staff Recognition")
    st.write("Generate AI-powered recognition for staff based on the ASCEND and NORTH frameworks.")
    
    # Fetch all finalized reports
    try:
        current_user_id = st.session_state['user'].id
        is_supervisor = st.session_state.get('is_supervisor', False)
        user_role = st.session_state.get('role', 'staff')
        
        all_reports = []



        if is_supervisor:
            # Use RPC to fetch finalized reports for this supervisor (works with RLS)
            rpc_resp = supabase.rpc('get_finalized_reports_for_supervisor', {'sup_id': current_user_id}).execute()
            all_reports = rpc_resp.data or []
        elif user_role in ['admin', 'director']:
            # Admin/Director sees all finalized reports using admin client to bypass RLS
            from src.database import get_admin_client
            admin_supabase = get_admin_client()
            response = admin_supabase.table("reports").select("week_ending_date, team_member, user_id, report_body, well_being_rating").eq("status", "finalized").execute()
            all_reports = response.data or []
        else:
            # Regular staff - might only see their own, or maybe this page isn't for them?
            # Assuming they can see their own finalized reports
            response = supabase.table("reports").select("week_ending_date, team_member, user_id, report_body, well_being_rating").eq("status", "finalized").eq("user_id", current_user_id).execute()
            all_reports = response.data or []
        
        # ...existing code...
        if not all_reports:
            st.info("No finalized reports found to analyze.")
            return

        # Get unique dates
        all_report_dates = [r.get("week_ending_date") for r in all_reports if r.get("week_ending_date")]
        # ...existing code...
        unique_dates = sorted(list(set(all_report_dates)), reverse=True)

        if not unique_dates:
            st.info("No report dates found.")
            return

        selected_date_for_summary = st.selectbox("Select week to analyze:", options=unique_dates)
        
    except Exception as e:
        st.error(f"Error fetching reports: {e}")
        return

    # Generate button
    if st.button("Generate Staff Recognition"):
        with st.spinner("🤖 Evaluating staff performance against ASCEND and NORTH criteria..."):
            weekly_reports = [r for r in all_reports if r.get("week_ending_date") == selected_date_for_summary]
            
            # Load rubrics
            rubrics = load_rubrics()
            if not rubrics:
                st.error("Failed to load rubrics.")
                return
                
            # Evaluate performance
            recognition_results = evaluate_staff_performance(weekly_reports, rubrics)
            
            if recognition_results:
                # Display top performers
                st.success("Recognition generated successfully!")
                
                st.subheader("🏆 Top Performers")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### 🌟 ASCEND Recognition")
                    ascend = recognition_results.get("ascend_recognition", {})
                    st.write(f"**Recipient:** {ascend.get('staff_member', 'Unknown')}")
                    st.write(f"**Category:** {ascend.get('category', 'Unknown')}")
                    st.write(f"**Score:** {ascend.get('score', 0)}/4")
                    st.write(f"**Reasoning:** {ascend.get('reasoning', 'N/A')}")
                    
                with col2:
                    st.markdown("### 🧭 NORTH Recognition")
                    north = recognition_results.get("north_recognition", {})
                    st.write(f"**Recipient:** {north.get('staff_member', 'Unknown')}")
                    st.write(f"**Category:** {north.get('category', 'Unknown')}")
                    st.write(f"**Score:** {north.get('score', 0)}/4")
                    st.write(f"**Reasoning:** {north.get('reasoning', 'N/A')}")
                
                # Display full score matrix
                st.markdown("---")
                st.subheader("📊 All Staff Performance Scores")
                
                all_staff_scores = recognition_results.get("all_staff_scores", [])
                if all_staff_scores:
                    # Create expandable sections for each staff member
                    for staff_score in all_staff_scores:
                        staff_name = staff_score.get("staff_member", "Unknown")
                        
                        with st.expander(f"📋 {staff_name}"):
                            # ASCEND scores
                            ascend_scores = staff_score.get("ascend_scores", [])
                            if ascend_scores:
                                st.markdown("**ASCEND Scores:**")
                                for score_item in ascend_scores:
                                    st.write(f"- **{score_item.get('category', 'Unknown')}**: {score_item.get('score', 'N/A')}/4")
                                    st.write(f"  _{score_item.get('reasoning', 'No reasoning provided')}_")
                            else:
                                st.write("_No ASCEND activities this week_")
                            
                            st.write("")  # Spacing
                            
                            # NORTH scores
                            north_scores = staff_score.get("north_scores", [])
                            if north_scores:
                                st.markdown("**NORTH Scores:**")
                                for score_item in north_scores:
                                    st.write(f"- **{score_item.get('category', 'Unknown')}**: {score_item.get('score', 'N/A')}/4")
                                    st.write(f"  _{score_item.get('reasoning', 'No reasoning provided')}_")
                            else:
                                st.write("_No NORTH activities this week_")
                    
                    # Add CSV download button
                    # Flatten data for CSV
                    csv_data = []
                    for staff_score in all_staff_scores:
                        staff_name = staff_score.get("staff_member", "Unknown")
                        
                        for ascend_score in staff_score.get("ascend_scores", []):
                            csv_data.append({
                                "Staff Member": staff_name,
                                "Category Type": "ASCEND",
                                "Category": ascend_score.get("category", "Unknown"),
                                "Score": ascend_score.get("score", ""),
                                "Reasoning": ascend_score.get("reasoning", "")
                            })
                        
                        for north_score in staff_score.get("north_scores", []):
                            csv_data.append({
                                "Staff Member": staff_name,
                                "Category Type": "NORTH",
                                "Category": north_score.get("category", "Unknown"),
                                "Score": north_score.get("score", ""),
                                "Reasoning": north_score.get("reasoning", "")
                            })
                    
                    if csv_data:
                        df = pd.DataFrame(csv_data)
                        csv_buffer = io.StringIO()
                        df.to_csv(csv_buffer, index=False)
                        
                        st.download_button(
                            label="📥 Download Scores as CSV",
                            data=csv_buffer.getvalue(),
                            file_name=f"staff_scores_{selected_date_for_summary}.csv",
                            mime="text/csv"
                        )
                else:
                    st.info("No detailed scores generated.")
                
                # Save results
                st.markdown("---")
                with st.spinner("Saving recognition report and individual scores..."):
                    # Save top performers
                    save_result = save_staff_recognition(
                        recognition_results, 
                        selected_date_for_summary, 
                        current_user_id
                    )
                    
                    if save_result.get("success"):
                        st.success(save_result.get("message"))
                    else:
                        st.error(f"Failed to save recognition: {save_result.get('message')}")
                    
                    # Save all individual scores
                    scores_save_result = save_staff_performance_scores(
                        all_staff_scores,
                        selected_date_for_summary,
                        current_user_id
                    )
                    
                    if scores_save_result.get("success"):
                        st.success(f"✅ {scores_save_result.get('message')}")
                    else:
                        st.error(f"Failed to save individual scores: {scores_save_result.get('message')}")
