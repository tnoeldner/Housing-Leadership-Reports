import streamlit as st
from src.database import supabase

def get_admin_prompt(setting_name: str, default: str) -> str:
    """
    Fetch the prompt template from the admin_settings table, or return the default if not set.
    """
    try:
        row = supabase.table("admin_settings").select("setting_value").eq("setting_name", setting_name).single().execute()
        if row.data and row.data.get("setting_value"):
            return row.data["setting_value"]
    except Exception:
        pass
    return default
