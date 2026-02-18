# Google Cloud Setup Guide

## 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** > **New Project**
3. Name it (e.g. "Time Analytics") and click **Create**

## 2. Enable APIs

In the Cloud Console, go to **APIs & Services > Library** and enable:
- **Google Calendar API**
- **Google Drive API**

## 3. Create OAuth 2.0 Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. If prompted, configure the **OAuth consent screen** first:
   - User type: **External** (or Internal if using Workspace)
   - App name: "Time Analytics"
   - Add your email as a test user
4. Back in Credentials, create an **OAuth client ID**:
   - Application type: **Desktop app**
   - Name: "Time Analytics Desktop"
5. Download the JSON file and save it as `credentials.json` in the project root

## 4. First-Time Authentication

Run the pipeline locally once to generate `token.json`:

```bash
pip install -r requirements.txt
python -m time_analytics.main --days 7 --skip-upload
```

A browser window will open asking you to authorize the app. After granting access, `token.json` will be created automatically.

## 5. GitHub Actions Setup

To automate via GitHub Actions, store credentials as repository secrets:

1. Go to your repo **Settings > Secrets and variables > Actions**
2. Add two secrets:
   - `GOOGLE_CREDENTIALS_JSON` — paste the full contents of `credentials.json`
   - `GOOGLE_TOKEN_JSON` — paste the full contents of `token.json`

> **Note:** OAuth tokens expire. If the refresh token stops working, you'll need to re-authenticate locally and update the `GOOGLE_TOKEN_JSON` secret.

## 6. Verify

```bash
# Local test (no upload)
python -m time_analytics.main --days 7 --skip-upload

# Full run (with Drive upload)
python -m time_analytics.main --days 30

# Check reports/ directory for output
ls reports/
```

## Event Tagging Convention

To categorize your events, prefix the event title with a tag in square brackets:

| Event Title | Category |
|---|---|
| `[Work] Team standup` | Work |
| `[Study] Python course` | Study |
| `[Exercise] Morning run` | Exercise |
| `Weekly grocery shopping` | Uncategorized |

You can use any tag — the system extracts whatever is inside the first `[...]` in the title.
