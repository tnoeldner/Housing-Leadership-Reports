#!/usr/bin/env python3
"""
Quick script to check Google AI API quota and usage
"""
import google.generativeai as genai
from datetime import datetime

def check_quota():
    """Check Google AI API quota and model information"""
    try:
        # Use API key from environment or secrets
        import os
        import streamlit as st
        
        try:
            # Try to use Streamlit secrets first (if running in Streamlit context)
            api_key = st.secrets["google_api_key"]
        except:
            # Fall back to environment variable
            api_key = os.getenv("GOOGLE_API_KEY")
            
        if not api_key:
            raise ValueError("Google API key not found. Please set GOOGLE_API_KEY environment variable or configure Streamlit secrets.")
            
        genai.configure(api_key=api_key)
        
        print("🔍 Google AI API Quota Check")
        print("=" * 50)
        print(f"⏰ Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # List available models
        print("📋 Available Models:")
        models = genai.list_models()
        for model in models:
            if "gemini" in model.name.lower():
                print(f"  - {model.name}")
                print(f"    Display Name: {model.display_name}")
                if hasattr(model, 'input_token_limit'):
                    print(f"    Input Token Limit: {model.input_token_limit:,}")
                if hasattr(model, 'output_token_limit'):
                    print(f"    Output Token Limit: {model.output_token_limit:,}")
                print()
        
        # Test a small request to check if API is working
        print("🧪 Testing API Connection:")
        try:
            test_model = genai.GenerativeModel("models/gemini-2.5-pro")
            response = test_model.generate_content("Hello, this is a quota test. Please respond with just 'API Working'.")
            print(f"  ✅ API Response: {response.text}")
            print("  ✅ API is functioning normally")
        except Exception as e:
            print(f"  ❌ API Error: {e}")
            if "quota" in str(e).lower():
                print("  🚨 QUOTA EXCEEDED - This is likely your issue!")
            elif "rate" in str(e).lower():
                print("  ⏳ RATE LIMIT - Try again in a few minutes")
        
        print()
        print("📊 Quota Recommendations:")
        print("  1. Visit https://aistudio.google.com/app/apikey to check usage")
        print("  2. Check if you're on Free ($0) or Paid tier")
        print("  3. Free tier: 15 req/min, 1,500 req/day")
        print("  4. Consider upgrading for heavy usage (500+ reports)")
        
    except Exception as e:
        print(f"❌ Error checking quota: {e}")

if __name__ == "__main__":
    check_quota()