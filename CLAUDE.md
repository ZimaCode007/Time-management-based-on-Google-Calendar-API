# CLAUDE.md — Project Instructions for Claude Code

## Project
Personal Time Analytics System — automated pipeline that fetches Google Calendar events, analyzes time usage, generates reports (Excel + PNG), and uploads to Google Drive.

## Architecture
```
time_analytics/
├── config.py                # Constants: SCOPES, TIMEZONE, paths, regex
├── data_ingestion.py        # OAuth2 auth, multi-calendar fetch, raw data saving, state I/O
├── processing.py            # Clean events: remove all-day/zero-duration, tz convert, duration
├── feature_engineering.py   # Category from calendar name/[Tag], streaks, daily ratios
├── analytics.py             # Metrics: totals, consistency, focus (HHI), trend analysis
├── reporting.py             # Excel (7 sheets) + 3 PNG charts → reports/
├── drive_uploader.py        # Upload to Google Drive (Year-Month subfolders)
├── main.py                  # CLI orchestrator with idempotency + incremental support
└── __main__.py              # Entry: python -m time_analytics
```

Pipeline order: **ingest → process → engineer → analyze → report → upload**

## CLI Usage
```bash
python -m time_analytics.main --days 30 --skip-upload                     # rolling lookback, no upload
python -m time_analytics.main --start 2026-02-15 --end 2026-02-21        # specific date range
python -m time_analytics.main --incremental                               # only events updated since last run
python -m time_analytics.main --force                                     # regenerate even if report exists
```

## Conventions
- **Timezone:** Always use `Europe/Berlin` (configured in `config.py`)
- **Categories:** Primary source is **calendar name** (fetches all user calendars). `[Tag]` prefix in event title overrides calendar name. Fallback: "Uncategorized".
- **Report naming:** `weekly_report_YYYY_WNN.xlsx`, `monthly_report_YYYY_MM.png`
- **Logging:** Every module uses `logging.getLogger(__name__)`. Log at INFO level for pipeline steps, WARNING for skipped data, ERROR for failures.
- **No hardcoded credentials.** Credentials come from `credentials.json` / `token.json` (gitignored) or GitHub Secrets in CI.

## Rules
- Always run `python -m py_compile <file>` on changed files before committing
- Never commit `credentials.json`, `token.json`, or anything in `data/` or `reports/`
- Keep modules focused — each file has a single responsibility
- Use `pandas` for all data manipulation, `matplotlib` with `Agg` backend for charts
- Prefer editing existing files over creating new ones
- All new analytics metrics should be added to the `AnalyticsResult` dataclass and surfaced in the Excel Summary sheet

## Excel Report Sheets
1. **Summary** — Total hours, events, avg daily, consistency/focus scores, trend
2. **Weekly** — Hours per ISO week
3. **Monthly** — Hours per month
4. **Categories** — Hours and ratio per category
5. **Details** — Two sections:
   - **Job Summary** (top): Category → Job → Sessions + Total Hours with subtotals
   - **Event Log** (bottom): Flat table (Date, Category, Job, Hours) for filtering
6. **Raw Data** — All events with date, summary, calendar, category, hours

## Drive Upload Structure
```
Time Analytics Reports/
└── YYYY-MM/              (auto-created per month)
    ├── weekly_report_YYYY_WNN.xlsx
    ├── monthly_report_YYYY_MM.png
    ├── weekly_trend_YYYY_WNN.png
    └── category_distribution_YYYY_WNN.png
```

## Key Design Decisions
- **Multi-calendar:** Fetches from all user calendars via `calendarList().list()`. Calendar name becomes the event category.
- **Category priority:** `[Tag]` in title > calendar name > "Uncategorized"
- **Date range:** Supports both `--days N` (rolling) and `--start/--end` (explicit range)
- **Idempotency:** `main.py` checks if `weekly_report_{week}.xlsx` exists before running. Use `--force` to override.
- **Incremental fetch:** Uses `updatedMin` parameter from saved state in `data/pipeline_state.json`
- **Raw data traceability:** Every fetch saves raw API response to `data/raw_events_{timestamp}.json`
- **State persistence:** Pipeline state (last run time, counts) saved to `data/pipeline_state.json`

## Dependencies
numpy, pandas, openpyxl, matplotlib, google-api-python-client, google-auth-httplib2, google-auth-oauthlib

## CI/CD
- `.github/workflows/scheduled_run.yml` — runs every Monday 08:00 Berlin time
- Secrets needed: `GOOGLE_CREDENTIALS_JSON`, `GOOGLE_TOKEN_JSON`
- Reports uploaded as GitHub Actions artifacts (30-day retention)
