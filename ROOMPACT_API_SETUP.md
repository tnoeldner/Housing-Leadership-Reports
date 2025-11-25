# Roompact API Setup Instructions

## Missing API Key Error

Your app is showing: `Error fetching page 0: Missing Roompact API key`

This means the Roompact API key is not configured in your Streamlit secrets.

## How to Fix

### Step 1: Create/Edit secrets.toml

Create or edit the file: `.streamlit/secrets.toml`

### Step 2: Add Your API Keys

Add the following to the file (replace with your actual keys):

```toml
# Roompact API Configuration
roompact_api_key = "YOUR_ACTUAL_ROOMPACT_API_KEY"

# Supabase Configuration (if not already present)
supabase_url = "YOUR_SUPABASE_URL"
supabase_key = "YOUR_SUPABASE_KEY"

# Google AI Configuration (if not already present)
google_api_key = "YOUR_GOOGLE_API_KEY"

# Email Configuration (optional)
EMAIL_ADDRESS = "your-email@example.com"
EMAIL_PASSWORD = "your-app-password"
SMTP_SERVER = "smtp.gmail.com"
```

### Step 3: Restart the App

1. Stop the Streamlit app (Ctrl+C in terminal)
2. Run it again: `python -m streamlit run app.py`
3. Try fetching duty reports again

## Where to Get Your Roompact API Key

Contact your Roompact administrator or check your Roompact account settings for API access.

## Security Note

The `.streamlit/secrets.toml` file is automatically gitignored - never commit it to version control!
