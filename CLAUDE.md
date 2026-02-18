# CLAUDE.md — Project Instructions for Claude Code

## Project
Personal Time Analytics System — automated pipeline that fetches Google Calendar events, analyzes time usage, generates reports (Excel + PNG), and uploads to Google Drive.

## Architecture
```
time_analytics/
├── config.py                # Constants: SCOPES, TIMEZONE, paths, regex
├── data_ingestion.py        # OAuth2 auth, Calendar API fetch, raw data saving, state I/O
├── processing.py            # Clean events: remove all-day/zero-duration, tz convert, duration
├── feature_engineering.py   # Extract [Tag] categories, streaks, daily ratios
├── analytics.py             # Metrics: totals, consistency, focus (HHI), trend analysis
├── reporting.py             # Excel (5 sheets) + 3 PNG charts → reports/
├── drive_uploader.py        # Upload to Google Drive folder
├── main.py                  # CLI orchestrator with idempotency + incremental support
└── __main__.py              # Entry: python -m time_analytics
```

Pipeline order: **ingest → process → engineer → analyze → report → upload**

## CLI Usage
```bash
python -m time_analytics.main --days 30 --skip-upload    # local test
python -m time_analytics.main --incremental              # only new events
python -m time_analytics.main --force                    # regenerate existing reports
```

## Conventions
- **Timezone:** Always use `Europe/Berlin` (configured in `config.py`)
- **Categories:** Extracted from `[Tag]` prefix in event titles (regex in `config.py`)
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

## Key Design Decisions
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
