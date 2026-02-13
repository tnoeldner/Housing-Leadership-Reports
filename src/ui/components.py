import streamlit as st
from src.database import supabase
from src.utils import clear_form_state

def login_form():
    st.header("Login")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        if submit:
            try:
                print(f"DEBUG: Attempting login for {email}")
                user_session = supabase.auth.sign_in_with_password({"email": email, "password": password})
                print(f"DEBUG: user_session: {user_session}")
                print(f"DEBUG: user_session type: {type(user_session)}")
                print(f"DEBUG: user_session attributes: {dir(user_session)}")
                if getattr(user_session, "user", None):
                    st.session_state["user"] = user_session.user
                    print(f"DEBUG: Login successful for {email}")
                    if hasattr(user_session, 'session'):
                        print(f"DEBUG: Found session attribute")
                        st.session_state["supabase_session"] = user_session.session
                        supabase.auth.set_session(user_session.session.access_token, user_session.session.refresh_token)
                    st.rerun()
                else:
                    print(f"DEBUG: Login failed, no user in session object")
                    st.error("Login failed. Please check your credentials.")
            except Exception as e:
                print(f"DEBUG: Exception during login: {type(e)} - {e}")
                st.error(f"Login failed: {e}")


def signup_form():
    st.header("Create a New Account")
    with st.form("signup"):
        email = st.text_input("Email")
        full_name = st.text_input("Full Name")
        title = st.text_input("Position Title")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Create Account")
        if submit:
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})
                if getattr(res, "user", None):
                    new_user_id = res.user.id
                    supabase.table("profiles").update({"full_name": full_name, "title": title, "email": email}).eq("id", new_user_id).execute()
                    st.success("Signup successful! Please check your email to confirm your account.")
                else:
                    st.error("Signup failed. A user may already exist with this email.")
            except Exception as e:
                if "already registered" in str(e):
                    st.error("This email address is already registered. Please try logging in.")
                else:
                    st.error(f"An error occurred during signup: {e}")


def logout():
    keys_to_delete = ["user", "role", "title", "full_name", "last_summary", "report_to_edit", "draft_report", "is_supervisor", "supabase_session"]
    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key]
    clear_form_state()

def restore_auth_session():
    """Restore the Supabase auth session from session_state if it exists"""
    if "supabase_session" in st.session_state:
        try:
            session = st.session_state["supabase_session"]
            supabase.auth.set_session(session.access_token, session.refresh_token)
        except Exception as e:
            print(f"Failed to restore auth session: {e}")

