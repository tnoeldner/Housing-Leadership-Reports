import os
import streamlit as st

# --- CONSTANTS ---
ASCEND_VALUES = ["Accountability", "Service", "Community", "Excellence", "Nurture", "Development", "N/A"]
NORTH_VALUES = ["Nurturing", "Operational", "Resource", "Transformative", "Holistic", "N/A"]
CORE_SECTIONS = {
    "students": "Students/Stakeholders",
    "projects": "Projects",
    "collaborations": "Collaborations",
    "responsibilities": "General Job Responsibilities",
    "staffing": "Staffing/Personnel",
    "kpis": "KPIs",
    "events": "Campus Events/Committees",
}

def get_secret(key, default=None):
    """
    Get a secret from environment variables or Streamlit secrets.
    Prioritizes environment variables.
    """
    # Try environment variable first
    value = os.getenv(key)
    if value:
        return value

    # Try Streamlit secrets (case-sensitive)
    try:
        return st.secrets.get(key, default)
    except FileNotFoundError:
        return default
    except Exception:
        return default
