# CLAUDE.md — Project Instructions for Claude Code

## Project
Personal Time Analytics System — automated pipeline that fetches Google Calendar events, analyzes time usage, generates reports (Excel + HTML/PNG), and uploads to Google Drive and Notion.

## Architecture
```
time_analytics/
├── config.py                # Constants: SCOPES, TIMEZONE, paths, regex, Notion env vars
├── data_ingestion.py        # OAuth2 auth, multi-calendar fetch, raw data saving, state I/O
├── processing.py            # Clean events: remove all-day/zero-duration, tz convert, duration
├── feature_engineering.py   # Category from calendar name/[Tag], streaks, daily ratios
├── analytics.py             # Metrics: totals, consistency, focus (HHI), trend analysis
├── reporting.py             # Excel (3 sheets) + 3 Plotly charts (HTML+PNG) → reports/
├── drive_uploader.py        # Upload to Google Drive (Year-Month subfolders)
├── notion_uploader.py       # Upload structured data to Notion (Weekly Summary + Event Log DBs)
├── main.py                  # CLI orchestrator with idempotency + incremental support
└── __main__.py              # Entry: python -m time_analytics
```

Pipeline order: **ingest → process → engineer → analyze → report → upload (Drive + Notion)**

## CLI Usage
```bash
python -m time_analytics.main --last-week                                 # last Mon-Sun + cumulative monthly (CI default)
python -m time_analytics.main --days 30 --skip-upload                     # rolling lookback, no upload
python -m time_analytics.main --start 2026-02-15 --end 2026-02-21        # specific date range
python -m time_analytics.main --incremental                               # only events updated since last run
python -m time_analytics.main --force                                     # regenerate even if report exists
python -m time_analytics.main --last-week --skip-notion                   # skip Notion upload
```

## Conventions
- **Timezone:** Always use `Europe/Berlin` (configured in `config.py`)
- **Categories:** Primary source is **calendar name** (fetches all user calendars). `[Tag]` prefix in event title overrides calendar name. Fallback: "Uncategorized".
- **Report naming:** `weekly_report_YYYY_WNN.xlsx`, `monthly_report_YYYY_MM.{html,png}`
- **Logging:** Every module uses `logging.getLogger(__name__)`. Log at INFO level for pipeline steps, WARNING for skipped data, ERROR for failures.
- **No hardcoded credentials.** Credentials come from `credentials.json` / `token.json` (gitignored) or GitHub Secrets in CI.

## Rules
- Always run `python -m py_compile <file>` on changed files before committing
- Never commit `credentials.json`, `token.json`, or anything in `data/` or `reports/`
- Keep modules focused — each file has a single responsibility
- Use `pandas` for all data manipulation, `plotly` for charts (HTML+PNG via kaleido), keep `matplotlib.use("Agg")` for kaleido compatibility
- Prefer editing existing files over creating new ones
- All new analytics metrics should be added to the `AnalyticsResult` dataclass and surfaced in the Excel Summary sheet

## Excel Report Sheets (3 sheets)
1. **Summary** — Total hours, events, avg daily, consistency/focus scores, trend
2. **Weekly** — Details-style: Job Summary (top) + Event Log (bottom) for the week
3. **Monthly** — Same structure using cumulative month-to-date data

Each Details-style sheet has:
- **Job Summary** (top): Category → Job → Sessions + Total Hours with category subtotals and grand total
- **Event Log** (bottom): Flat table (Date, Category, Job, Hours) for filtering

## Charts (3 charts × 2 formats = 6 files)
- `monthly_report_YYYY_MM.{html,png}` — bar chart: hours by category (month-to-date)
- `weekly_trend_YYYY_WNN.{html,png}` — line chart: weekly hours trend
- `category_distribution_YYYY_WNN.{html,png}` — horizontal bar: hours by category (week)

## Notion Databases (auto-created under NOTION_PARENT_PAGE_ID)
- **Weekly Summary** — one row per week (Week, Total Hours, Events, Avg Daily, Consistency, Focus, Streak, Trend Direction, Slope)
- **Event Log** — one row per event (Job, Date, Category, Hours, Week, Month)
- Upsert strategy: skip if exists (unless `--force`), bulk-replace Event Log rows by week
- Rate-limited: 0.35s sleep between Event Log inserts

## Drive Upload Structure
```
Time Analytics Reports/
└── YYYY-MM/              (auto-created per month)
    ├── weekly_report_YYYY_WNN.xlsx
    ├── monthly_report_YYYY_MM.html
    ├── monthly_report_YYYY_MM.png
    ├── weekly_trend_YYYY_WNN.html
    ├── weekly_trend_YYYY_WNN.png
    ├── category_distribution_YYYY_WNN.html
    └── category_distribution_YYYY_WNN.png
```

## Key Design Decisions
- **Multi-calendar:** Fetches from all user calendars via `calendarList().list()`. Calendar name becomes the event category.
- **Category priority:** `[Tag]` in title > calendar name > "Uncategorized"
- **Last-week mode:** `--last-week` fetches full month-to-date, splits into weekly (last Mon-Sun) and monthly (cumulative) data. Used by CI.
- **Date range:** Also supports `--days N` (rolling) and `--start/--end` (explicit range)
- **Idempotency:** `main.py` checks if `weekly_report_{week}.xlsx` exists before running. Use `--force` to override.
- **Incremental fetch:** Uses `updatedMin` parameter from saved state in `data/pipeline_state.json`
- **Raw data traceability:** Every fetch saves raw API response to `data/raw_events_{timestamp}.json`
- **State persistence:** Pipeline state (last run time, counts) saved to `data/pipeline_state.json`
- **Notion non-fatal:** Notion upload failures are caught and logged; they do not abort the pipeline.

## Dependencies
numpy, pandas, openpyxl, matplotlib, plotly, kaleido==0.2.1, google-api-python-client, google-auth-httplib2, google-auth-oauthlib, notion-client

## CI/CD
- `.github/workflows/scheduled_run.yml` — runs every Monday 08:00 Berlin time with `--last-week`
- Secrets needed: `GOOGLE_CREDENTIALS_JSON`, `GOOGLE_TOKEN_JSON`, `NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID`
- Reports uploaded as GitHub Actions artifacts (30-day retention)
