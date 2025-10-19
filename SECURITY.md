# Security Guidelines for Housing Leadership Reports

## 🔐 API Key Management

### ✅ DO:
- Store API keys in Streamlit secrets (`secrets.toml`)
- Use environment variables for local development (`.env`)
- Keep secrets files in `.gitignore`
- Rotate keys immediately if exposed
- Use separate keys for dev/staging/production

### ❌ DON'T:
- Hardcode API keys in source code
- Commit secrets files to Git
- Share keys in chat/email
- Use production keys in development
- Store keys in public repositories

## 🗂️ File Structure

```
project/
├── .streamlit/
│   └── secrets.toml           # ← NEVER COMMIT
├── .env                       # ← NEVER COMMIT  
├── .env.example              # ← Safe to commit (template only)
├── .gitignore                # ← Must include secrets files
└── app.py                    # ← Use st.secrets["key_name"]
```

## 🔧 Setup Instructions

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Fill in your actual keys in `.env`:**
   ```env
   GOOGLE_API_KEY=AIzaSy...
   SUPABASE_KEY=eyJhbG...
   ```

3. **For Streamlit Cloud, use secrets.toml:**
   ```toml
   google_api_key = "AIzaSy..."
   supabase_key = "eyJhbG..."
   ```

4. **In your code, use:**
   ```python
   import streamlit as st
   api_key = st.secrets["google_api_key"]
   ```

## 🚨 If Keys Are Exposed

1. **Immediately rotate all exposed keys**
2. **Remove from Git history:**
   ```bash
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch path/to/secrets" \
     --prune-empty -- --all
   git push origin main --force
   ```
3. **Update all environments with new keys**
4. **Review access logs for unauthorized usage**

## 📋 Security Checklist

- [ ] All secrets in `.gitignore`
- [ ] No hardcoded keys in source code
- [ ] Separate keys for different environments
- [ ] Regular key rotation schedule
- [ ] Monitor API usage for anomalies
- [ ] Team members know security practices

## 🔍 Regular Security Audit

Run these commands periodically:
```bash
# Search for potential exposed keys
git log --all -p -S "AIzaSy"
grep -r "AIzaSy" . --exclude-dir=.git

# Check what's tracked by Git
git ls-files | grep -E "(secret|key|env)"
```

Remember: **Security is everyone's responsibility!**