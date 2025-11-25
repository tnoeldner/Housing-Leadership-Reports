import streamlit as st
import time
from src.database import supabase

def profile_page():
    if "user" not in st.session_state:
        st.warning("You must be logged in to view this page.")
        st.stop()
    st.header("My Profile")
    st.markdown(f"**Email:** {st.session_state['user'].email}")
    st.markdown(f"**Role:** {st.session_state.get('role', 'N/A')}")
    st.markdown(f"**Full Name:** {st.session_state.get('full_name', '')}")
    st.markdown(f"**Title:** {st.session_state.get('title', '')}")
    # Debug: Show session UID, email, and access token
    st.write("Session user id:", getattr(st.session_state["user"], "id", None))
    st.write("Session user email:", getattr(st.session_state["user"], "email", None))
    st.write("Session user access_token:", getattr(st.session_state["user"], "access_token", None))

    user_id = getattr(st.session_state["user"], "id", None)
    form_key = f"update_profile_{user_id}" if user_id else f"update_profile_{st.session_state['user'].email}"
    with st.form(form_key):
        new_name = st.text_input("Full Name", value=st.session_state.get("full_name", ""))
        new_title = st.text_input("Position Title", value=st.session_state.get("title", ""))
        submitted = st.form_submit_button("Update Profile")
        if submitted:
            try:
                user_id = st.session_state["user"].id
                update_data = {"full_name": new_name, "title": new_title}
                supabase.table("profiles").update(update_data).eq("id", user_id).execute()
                st.session_state["full_name"] = new_name
                st.session_state["title"] = new_title
                st.success("Profile updated successfully!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"An error occurred: {e}")
