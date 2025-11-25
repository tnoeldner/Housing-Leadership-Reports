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
        print(f"[DEBUG] get_secret: Found environment variable '{key}' with value: {value}")
        return value

    # Try Streamlit secrets (case-sensitive)
    try:
        secret_value = st.secrets.get(key, default)
        print(f"[DEBUG] get_secret: Found Streamlit secret '{key}' with value: {secret_value}")
        return secret_value
    except FileNotFoundError:
        print(f"[DEBUG] get_secret: FileNotFoundError for key '{key}'")
        return default
    except Exception as e:
        print(f"[DEBUG] get_secret: Exception for key '{key}': {e}")
        return default
