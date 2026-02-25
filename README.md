# Time Analytics — Google Calendar + Drive + Notion

A personal time tracking pipeline that automatically fetches events from Google Calendar, analyzes your time usage, and generates Excel + chart reports — uploaded to Google Drive and optionally Notion. Runs weekly via GitHub Actions.

---

## What It Does

- Fetches events from **all your Google Calendars** (calendar name = category)
- Generates an **Excel report** with 3 sheets: Summary, Weekly breakdown, Monthly breakdown
- Generates **3 Plotly charts** (HTML + PNG): monthly hours by category, weekly trend, category distribution
- Uploads everything to **Google Drive** in a `YYYY-MM/YYYY-WNN/` folder structure
- Optionally syncs a **Weekly Summary** and **Event Log** to Notion databases
- Runs **automatically every Monday** via GitHub Actions

---

## Output Structure

```
reports/
└── 2026-02/
    └── W08/
        ├── weekly_report_2026_W08.xlsx
        ├── monthly_report_2026_02.html
        ├── monthly_report_2026_02.png
        ├── weekly_trend_2026_W08.html
        ├── weekly_trend_2026_W08.png
        ├── category_distribution_2026_W08.html
        └── category_distribution_2026_W08.png
```

Google Drive mirrors the same structure under `Time Analytics Reports/`.

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/ZimaCode007/Time-management-based-on-Google-Calendar-API.git
cd Time-management-based-on-Google-Calendar-API
```

### 2. Install dependencies

Python 3.12+ recommended.

```bash
pip install -r requirements.txt
```

### 3. Set up Google Cloud credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the **Google Calendar API** and **Google Drive API**
3. Create **OAuth 2.0 credentials** (Desktop app type)
4. Download the credentials file and save it as `credentials.json` in the project root

### 4. Authenticate (first run only)

```bash
python -m time_analytics.main --days 7 --skip-upload
```

A browser window will open asking you to authorize access. After approval, a `token.json` file is saved locally — you won't need to authenticate again.

### 5. (Optional) Set up Notion

1. Create a Notion integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Copy the **Internal Integration Token**
3. Create a Notion page and share it with your integration
4. Copy the page ID from the URL (the 32-character hex string)
5. Set environment variables:

```bash
export NOTION_TOKEN=secret_xxx
export NOTION_PARENT_PAGE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## Usage

```bash
# Last Mon–Sun week + cumulative month-to-date (recommended, same as CI)
python -m time_analytics.main --last-week

# Rolling lookback, no upload
python -m time_analytics.main --days 30 --skip-upload

# Specific date range
python -m time_analytics.main --start 2026-02-01 --end 2026-02-07

# Force regenerate even if report already exists
python -m time_analytics.main --last-week --force

# Skip Notion upload
python -m time_analytics.main --last-week --skip-notion

# Backfill all weeks from a start date
python -m time_analytics.main --all-weeks --start 2026-01-01

# Only fetch events updated since last run
python -m time_analytics.main --incremental
```

---

## Categories

Events are categorized in this priority order:

1. **`[Tag]` prefix in event title** — e.g. an event titled `[Study] Linear Algebra` → category `Study`
2. **Calendar name** — events in a calendar called `Work` → category `Work`
3. **Fallback** — `Uncategorized`

---

## Automated Weekly Run (GitHub Actions)

The pipeline runs every **Monday at 08:00 Berlin time** via `.github/workflows/scheduled_run.yml`.

### Required GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** and add:

| Secret | Description |
|---|---|
| `GOOGLE_CREDENTIALS_JSON` | Full contents of your `credentials.json` |
| `GOOGLE_TOKEN_JSON` | Full contents of your `token.json` (after first local auth) |
| `NOTION_TOKEN` | Notion integration token (optional) |
| `NOTION_PARENT_PAGE_ID` | Notion parent page ID (optional) |

Reports are uploaded to Google Drive automatically and also saved as GitHub Actions artifacts for 30 days.

### Manual trigger

Go to **Actions** → **Weekly Time Analytics** → **Run workflow**.

---

## Project Structure

```
time_analytics/
├── config.py              # Constants: timezone, paths, API scopes, Notion env vars
├── data_ingestion.py      # OAuth2 auth, multi-calendar fetch, raw data saving, state I/O
├── processing.py          # Clean events: remove all-day/zero-duration, timezone convert
├── feature_engineering.py # Category assignment, streaks, daily ratios
├── analytics.py           # Metrics: totals, consistency, focus (HHI), trend slope
├── reporting.py           # Excel (3 sheets) + 3 Plotly charts → reports/YYYY-MM/WNN/
├── drive_uploader.py      # Upload to Google Drive with year/month/week folder structure
├── notion_uploader.py     # Sync to Notion: Weekly Summary + Event Log databases
├── main.py                # CLI orchestrator
└── __main__.py            # Entry point: python -m time_analytics
```

---

## Notes

- `credentials.json` and `token.json` are gitignored — never commit them
- `data/` (raw API responses) and `reports/` are gitignored
- Notion upload failures are non-fatal — the pipeline continues if Notion is unreachable
- GitHub automatically disables scheduled workflows after 60 days of repo inactivity — re-enable from the Actions tab if needed
