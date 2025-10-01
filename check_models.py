# check_models.py

import google.generativeai as genai
import streamlit as st # We use streamlit here just to easily read the secrets file

try:
    # Read the API key from your secrets file
    api_key = st.secrets["google_api_key"]
    genai.configure(api_key=api_key)

    print("Finding available models...\n")

    # List the models and check which ones support the 'generateContent' method
    for m in genai.list_models():
      if 'generateContent' in m.supported_generation_methods:
        print(m.name)

except Exception as e:
    print(f"An error occurred: {e}")
    print("\nPlease ensure your '.streamlit/secrets.toml' file exists and contains your 'google_api_key'.")