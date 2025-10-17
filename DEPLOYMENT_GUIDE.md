# UND Reporting Tool - Deployment Guide

## Prerequisites
- GitHub repository with the latest code
- Streamlit Community Cloud account (https://share.streamlit.io/)
- Supabase account and database setup

## Deployment Steps

### 1. Streamlit Community Cloud Deployment

1. Go to https://share.streamlit.io/
2. Sign in with your GitHub account
3. Click "New app"
4. Select your repository: `tnoeldner/Housing-Leadership-Reports`
5. Set branch: `main`
6. Set main file path: `app.py`
7. Click "Deploy!"

### 2. Environment Variables/Secrets

In Streamlit Cloud, add these secrets in the app settings:

```toml
[supabase]
url = "your-supabase-url"
key = "your-supabase-anon-key"

[google]
api_key = "your-google-gemini-api-key"

[roompact]
url = "your-roompact-api-url"
key = "your-roompact-api-key"

[email]
smtp_server = "your-smtp-server"
smtp_port = 587
from_email = "your-email@domain.com"
password = "your-email-password"
```

### 3. Database Setup

Before first use, run the database setup:

1. Execute `COMPLETE_DATABASE_SETUP.sql` in your Supabase SQL editor
2. If you have existing engagement data, run `UPDATE_ATTENDANCE_COLUMN.sql`

### 4. Alternative Deployment Options

#### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

#### Heroku Deployment
Create these files:
- `Procfile`: `web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
- `setup.sh`: Script to configure Streamlit
- `runtime.txt`: `python-3.9.20`

## Features Included in Latest Deployment

✅ **Enhanced Duty Analysis Save Functionality**
- Pre-insert duplicate detection
- Detailed user feedback and error handling
- Batch processing with individual record validation
- Consistent save patterns across all analysis types

✅ **Complete Engagement Analysis System**
- Full feature parity with duty analysis
- Quantitative data extraction and storage
- Weekly analysis reports with AI summaries
- Upcoming events tracking
- Field mapping for Residence Life Event Submission forms

✅ **Database Schema Updates**
- Comprehensive table structure for all report types
- Proper constraints and indexes
- Row Level Security (RLS) policies
- Migration scripts for existing data

✅ **Enhanced Error Handling**
- Graceful duplicate detection
- User-friendly error messages
- Detailed logging and feedback
- Robust constraint handling

## Monitoring and Maintenance

- Monitor app performance in Streamlit Cloud dashboard
- Check logs for any errors or issues
- Update database schema as needed using provided SQL scripts
- Regular backup of Supabase database

## Support

- Check ENGAGEMENT_DEBUG_GUIDE.md for troubleshooting
- Review DATABASE_SAVE_FIX.md for save functionality issues
- Refer to ENGAGEMENT_SETUP_INSTRUCTIONS.md for initial setup