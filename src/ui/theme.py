"""Global visual theme for the Streamlit app (fonts, cards, sidebar, buttons, tables)."""
import streamlit as st
from src.utils import get_logo_base64

PRIMARY = "#009A44"
PRIMARY_DARK = "#006633"
PRIMARY_LIGHT = "#E8F5E8"


def apply_custom_theme():
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', 'Segoe UI', sans-serif;
        }}

        /* Tighten default page padding for a more app-like feel */
        .block-container {{
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1200px;
        }}

        /* Headings */
        h1 {{
            color: {PRIMARY_DARK};
            font-weight: 800;
            letter-spacing: -0.5px;
        }}
        h2 {{
            color: {PRIMARY_DARK};
            font-weight: 700;
            border-left: 5px solid {PRIMARY};
            padding-left: 12px;
            margin-top: 1.5rem;
        }}
        h3 {{
            color: #2c3e50;
            font-weight: 600;
        }}

        /* Sidebar */
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {PRIMARY_DARK} 0%, {PRIMARY} 100%);
            color: #ffffff;
        }}
        /* Only force white on text elements, not on inputs/controls with light backgrounds */
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] h4,
        [data-testid="stSidebar"] .stMarkdown {{
            color: #ffffff !important;
        }}
        /* Text/password inputs keep a white field with dark, readable text */
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {{
            color: #1a1a1a !important;
            background-color: #ffffff !important;
        }}
        [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div {{
            background-color: rgba(255,255,255,0.12);
            border-radius: 8px;
            color: #ffffff !important;
        }}
        [data-testid="stSidebar"] hr {{
            border-color: rgba(255,255,255,0.25);
        }}
        /* Tabs in the sidebar (Login / Sign Up): keep selected tab text dark since its background is light */
        [data-testid="stSidebar"] .stTabs [aria-selected="true"] {{
            color: {PRIMARY_DARK} !important;
        }}
        [data-testid="stSidebar"] .stTabs [aria-selected="false"] {{
            color: #ffffff !important;
        }}

        /* Buttons (including form submit buttons) */
        .stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
            border-radius: 8px;
            border: none;
            font-weight: 600;
            padding: 0.5rem 1.25rem;
            transition: all 0.15s ease-in-out;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        }}
        .stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 10px rgba(0,154,68,0.25);
        }}
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button {{
            background-color: rgba(255,255,255,0.18);
            color: #ffffff !important;
            width: 100%;
        }}
        [data-testid="stSidebar"] .stButton > button:hover,
        [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button:hover {{
            background-color: rgba(255,255,255,0.32);
        }}
        /* The login/signup form renders as a light card inside the sidebar,
           so its text and button need dark-on-white styling instead of the
           white-on-green styling used elsewhere in the sidebar. */
        [data-testid="stSidebar"] div[data-testid="stForm"] label,
        [data-testid="stSidebar"] div[data-testid="stForm"] p,
        [data-testid="stSidebar"] div[data-testid="stForm"] span {{
            color: #1a1a1a !important;
        }}
        [data-testid="stSidebar"] div[data-testid="stForm"] [data-testid="stFormSubmitButton"] > button {{
            background-color: {PRIMARY} !important;
            color: #ffffff !important;
        }}
        [data-testid="stSidebar"] div[data-testid="stForm"] [data-testid="stFormSubmitButton"] > button:hover {{
            background-color: {PRIMARY_DARK} !important;
        }}

        /* Metrics as cards */
        [data-testid="stMetric"] {{
            background-color: #ffffff;
            border: 1px solid #e9ecef;
            border-radius: 10px;
            padding: 1rem 1.1rem;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }}

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 4px;
        }}
        .stTabs [data-baseweb="tab"] {{
            border-radius: 8px 8px 0 0;
            font-weight: 600;
            padding: 8px 16px;
        }}
        .stTabs [aria-selected="true"] {{
            background-color: {PRIMARY_LIGHT};
            color: {PRIMARY_DARK};
        }}

        /* Expanders */
        [data-testid="stExpander"] {{
            border: 1px solid #e9ecef;
            border-radius: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}

        /* DataFrames / tables */
        [data-testid="stDataFrame"], [data-testid="stTable"] {{
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }}

        /* Alerts */
        div[data-testid="stAlert"] {{
            border-radius: 8px;
        }}

        /* Form containers */
        div[data-testid="stForm"] {{
            border: 1px solid #e9ecef;
            border-radius: 12px;
            padding: 1.25rem;
            background-color: #fafafa;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand():
    """Small branded logo + title block shown at the top of the sidebar."""
    logo_data = get_logo_base64()
    st.sidebar.markdown(
        f"""
        <div style="text-align:center; padding: 0.5rem 0 1rem 0;">
            <img src="{logo_data}" style="max-width: 140px; height: auto; margin-bottom: 0.5rem;" />
            <div style="font-weight:700; font-size:1.05rem; letter-spacing:0.5px;">Weekly Impact Report</div>
        </div>
        <hr/>
        """,
        unsafe_allow_html=True,
    )
