# Roompact API Configuration Issue

## Current Problem

The API is returning HTML instead of JSON, which means the endpoint URL is incorrect.

**Error:** `Invalid JSON response from API. Status: 200, Content preview: <!DOCTYPE html...`

## Possible Solutions

### Option 1: Check Your Institution's Roompact URL

Your institution might have a custom Roompact subdomain. Common formats:
- `https://yourschool.roompact.com/api/v1`
- `https://und.roompact.com/api/v1` (if UND is your school code)

### Option 2: Try Different API Versions

The API path might be different:
- `https://roompact.com/api/v2`
- `https://roompact.com/api`
- `https://app.roompact.com/api/v1`

### Option 3: Configure Custom Base URL

Add this to your `.streamlit/secrets.toml` file:

```toml
roompact_api_token = "your-token-here"
roompact_base_url = "https://YOUR_CORRECT_URL_HERE/api/v1"
```

## How to Find the Correct URL

1. **Check Roompact Documentation** - Look for API documentation from your Roompact admin
2. **Contact Roompact Support** - Ask for the correct API endpoint URL for your institution
3. **Check Your Institution's IT** - They may have documentation on the Roompact API setup

## Next Steps

Once you have the correct base URL:
1. Add `roompact_base_url = "correct-url-here"` to your secrets.toml
2. Restart the Streamlit app
3. Try fetching duty reports again
