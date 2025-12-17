from collections import defaultdict
import google.generativeai as genai
import streamlit as st
from datetime import datetime

def create_weekly_duty_report_summary(selected_forms, start_date, end_date):
    st.info(f"[DEBUG] Entered create_weekly_duty_report_summary with {len(selected_forms)} forms, start_date={start_date}, end_date={end_date}")
    """Create a weekly quantitative duty report with hall breakdowns for admin summaries"""
        # Prepare comprehensive report data for AI analysis
        reports_text = f"\n=== WEEKLY DUTY REPORTS ANALYSIS ===\n"
        reports_text += f"Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n"
        reports_text += f"Total Reports: {len(selected_forms)}\n\n"
        # ...existing code for building reports_text...
        st.info(f"[DEBUG] Prepared reports_text for AI:")
        st.code(reports_text)
    

    if not selected_forms:
        return {"summary": "No duty reports selected for analysis."}
    try:
        halls_data = defaultdict(lambda: {
            'total_reports': 0,
            'lockouts': 0,
            'maintenance': 0,
            'policy_violations': 0,
            'safety_concerns': 0,
            'staff_responses': 0
        })
        weekly_data = defaultdict(lambda: {
            'total_reports': 0,
            'incident_count': 0,
            'halls_active': set()
        })

        # Process each form to extract quantitative data
        for form in selected_forms:
            current_revision = form.get('current_revision', {})
            author = current_revision.get('author', 'Unknown')
            date_str = current_revision.get('date', '')
            hall_name = "Unknown Hall"
            responses = current_revision.get('responses', [])
            for response in responses:
                field_label = response.get('field_label', '').lower()
                field_response = str(response.get('response', '')).strip()
                if any(word in field_label for word in ['building', 'hall', 'location', 'area']):
                    if field_response and field_response != 'None':
                        hall_name = field_response
                        break
            # Extract week from date
            if date_str:
                try:
                    form_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    week_key = form_date.strftime('Week of %Y-%m-%d')
                    weekly_data[week_key]['total_reports'] += 1
                    weekly_data[week_key]['halls_active'].add(hall_name)
                except:
                    week_key = "Unknown Week"
            else:
                week_key = "Unknown Week"
            # Count incidents by type in this report
            report_text = ""
            for response in responses:
                field_response = str(response.get('response', '')).strip().lower()
                report_text += field_response + " "
            halls_data[hall_name]['total_reports'] += 1
            if any(word in report_text for word in ['lockout', 'locked out', 'key']):
                halls_data[hall_name]['lockouts'] += 1
            if any(word in report_text for word in ['maintenance', 'repair', 'broken', 'leak', 'ac', 'heat']):
                halls_data[hall_name]['maintenance'] += 1
            if any(word in report_text for word in ['alcohol', 'intoxicated', 'violation', 'policy', 'noise']):
                halls_data[hall_name]['policy_violations'] += 1
                weekly_data[week_key]['incident_count'] += 1
            if any(word in report_text for word in ['safety', 'emergency', 'security', 'fire', 'medical']):
                halls_data[hall_name]['safety_concerns'] += 1
                weekly_data[week_key]['incident_count'] += 1
            if any(word in report_text for word in ['responded', 'contacted', 'called', 'notified']):
                halls_data[hall_name]['staff_responses'] += 1

        # Prepare comprehensive report data for AI analysis
        reports_text = f"\n=== WEEKLY DUTY REPORTS ANALYSIS ===\n"
        reports_text += f"Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n"
        reports_text += f"Total Reports: {len(selected_forms)}\n\n"

        # Add quantitative breakdown by hall (formatted for table creation)
        reports_text += "=== HALL-BY-HALL INCIDENT BREAKDOWN (FOR TABLE) ===\n"

        # Calculate totals for summary
        total_lockouts = sum(int(data['lockouts']) for data in halls_data.values())
        total_maintenance = sum(int(data['maintenance']) for data in halls_data.values())
        total_violations = sum(int(data['policy_violations']) for data in halls_data.values())
        total_safety = sum(int(data['safety_concerns']) for data in halls_data.values())
        total_reports = sum(int(data['total_reports']) for data in halls_data.values())
        total_responses = sum(int(data['staff_responses']) for data in halls_data.values())

        reports_text += "DATA FOR QUANTITATIVE METRICS TABLE:\n"
        reports_text += f"TOTALS: Reports={total_reports}, Lockouts={total_lockouts}, Maintenance={total_maintenance}, Violations={total_violations}, Safety={total_safety}, Responses={total_responses}\n\n"

        reports_text += "HALL-BY-HALL DATA:\n"
        for hall, data in sorted(halls_data.items()):
            reports_text += f"{hall}: Reports={data['total_reports']}, Lockouts={data['lockouts']}, Maintenance={data['maintenance']}, Violations={data['policy_violations']}, Safety={data['safety_concerns']}, Responses={data['staff_responses']}\n"

        reports_text += "\nDETAILED BREAKDOWN BY HALL:\n"
        for hall, data in sorted(halls_data.items()):
            total_incidents = int(data['lockouts']) + int(data['maintenance']) + int(data['policy_violations']) + int(data['safety_concerns'])
            reports_text += f"**{hall}** ({data['total_reports']} reports, {total_incidents} total incidents):\n"
            reports_text += f"  • Lockouts: {data['lockouts']}\n"
            # Removed undefined 'week' reference. If weekly breakdown is needed, restructure using weekly_data.

        reports_text += f"\n=== DETAILED REPORTS ===\n"

        for i, form in enumerate(selected_forms, 1):
            current_revision = form.get('current_revision', {})
            form_name = form.get('form_template_name', 'Unknown Form')
            author = current_revision.get('author', 'Unknown')
            date = current_revision.get('date', 'Unknown date')

            reports_text += f"\n--- REPORT {i}: {form_name} ---\n"
            reports_text += f"Staff: {author}\n"
            reports_text += f"Date: {date}\n\n"

            # Process responses
            responses = current_revision.get('responses', [])
            for response in responses:
                field_label = response.get('field_label', 'Unknown Field')
                field_response = response.get('response', '')

                if field_response and str(field_response).strip():
                    reports_text += f"**{field_label}:** {field_response}\n"

            reports_text += "\n" + "="*50 + "\n"

        # Updated AI prompt for improved, actionable, bullet-pointed summary
        prompt = f"""
You are analyzing residence life duty reports for a weekly administrative summary. Your goal is to produce a concise, actionable, and easy-to-read report for leadership. Please:

- Summarize the week's overall activity and key trends in 3-5 bullet points.
- Highlight the most important incidents, challenges, or successes that require attention. Use bullet points for each item.
- Provide a quantitative breakdown (number of reports, incidents by type, hall-by-hall summary) in a clear, readable format.
- For each hall, create a dedicated section with the hall name as the header. The individual halls are: Swanson, West, McVey, Brannon, Noren, Selke, Johnstone, Smith, University Place. Under each hall, list the key items, incidents, challenges, successes, and any notable staff actions for that hall as bullet points. Do not group halls together; each hall should have its own section, even if some halls have no incidents or items to report.
- List specific action items or recommendations for staff or administration. Make these actionable and direct.
- Note any staff performance highlights or concerns.
- If relevant, mention any policy, facility, or safety issues that need follow-up.

Do NOT include a separate "Recurring Issues" section. Instead, ensure hall-specific issues are included under each hall's section.

Format your response in markdown with clear headers and bullet points. Focus on actionable insights and brevity. Do not include unnecessary narrative or filler text.

DUTY REPORTS DATA:
{reports_text}

Generate the weekly duty analysis summary below:
"""

        api_key = None
        try:
            from src.config import get_secret
            api_key = get_secret("GOOGLE_API_KEY")
        except Exception:
            api_key = None
        if not api_key:
            st.error("❌ Missing Google AI API key. Please check your secrets or environment variables.")
            return {"summary": "Error: Missing Google AI API key."}
        st.info(f"[DEBUG] Using Google API key: {api_key[:6]}... (truncated)")
        model = genai.GenerativeModel("models/gemini-2.5-pro")
        with st.spinner(f"AI is generating weekly duty report from {len(selected_forms)} reports..."):
            try:
                st.info("[DEBUG] Sending prompt to Gemini AI model...")
                result = model.generate_content(prompt)
                st.info(f"[DEBUG] Gemini AI model returned: {getattr(result, 'text', None)[:500]}... (truncated)")
                summary_text = result.text if result and hasattr(result, 'text') else None
                if not summary_text or not summary_text.strip():
                    st.info("Prompt sent to AI:")
                    st.code(prompt)
                    st.info("Input data summary:")
                    st.code(reports_text)
                    return {"summary": "Error: AI did not return a summary. Please check your API quota, prompt, or try again later."}
                return {"summary": summary_text}
            except Exception as e:
                st.error(f"[DEBUG] Exception during Gemini AI call: {e}")
                return {"summary": f"Error generating weekly duty report summary: {str(e)}"}
    except Exception as e:
        st.error(f"[DEBUG] Exception in create_weekly_duty_report_summary: {e}")
        return {"summary": f"Error generating weekly duty report summary: {str(e)}"}
