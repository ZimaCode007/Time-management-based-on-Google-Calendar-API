"""Personal Time Analytics — Pipeline Orchestrator.

Usage:
    python -m time_analytics.main [--days N] [--start YYYY-MM-DD --end YYYY-MM-DD] [--last-week] [--skip-upload] [--incremental] [--force]
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

from . import config
from .analytics import compute_analytics
from .data_ingestion import authenticate, fetch_events, load_state, save_state
from .drive_uploader import upload_reports
from .feature_engineering import engineer_features
from .notion_uploader import upload_to_notion
from .processing import process_events
from .reporting import generate_reports

logger = logging.getLogger("time_analytics")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Personal Time Analytics Pipeline")
    parser.add_argument(
        "--days",
        type=int,
        default=config.DEFAULT_LOOKBACK_DAYS,
        help=f"Number of days to look back (default: {config.DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD). Use with --end for a specific range.",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD). Use with --start for a specific range.",
    )
    parser.add_argument(
        "--last-week",
        action="store_true",
        help="Generate report for last Mon-Sun week, with cumulative monthly data.",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip uploading reports to Google Drive",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only fetch events updated since last run",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run even if reports already exist for this period",
    )
    parser.add_argument(
        "--skip-notion",
        action="store_true",
        help="Skip uploading data to Notion databases",
    )
    return parser.parse_args()


def _get_last_week_range() -> tuple[str, str]:
    """Return (start, end) date strings for last Monday–Sunday."""
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday.isoformat(), last_sunday.isoformat()


def _get_month_to_date_start() -> str:
    """Return the 1st of the current month as YYYY-MM-DD."""
    today = date.today()
    return today.replace(day=1).isoformat()


def _check_idempotency(force: bool, week_label: str = None) -> bool:
    """Check if reports for the period already exist."""
    if force:
        return True

    if not week_label:
        now = datetime.now()
        iso = now.isocalendar()
        week_label = f"{iso[0]}_W{iso[1]:02d}"

    expected_excel = config.REPORT_DIR / f"weekly_report_{week_label}.xlsx"

    if expected_excel.exists():
        logger.info(
            "Report for %s already exists: %s. Use --force to regenerate.",
            week_label,
            expected_excel,
        )
        return False

    return True


def run(
    days: int,
    skip_upload: bool,
    incremental: bool,
    force: bool,
    start_date: str = None,
    end_date: str = None,
    last_week: bool = False,
    skip_notion: bool = False,
) -> None:
    """Execute the full analytics pipeline."""
    logger.info("=== Starting Time Analytics Pipeline ===")

    # Resolve --last-week mode
    month_df = None
    if last_week:
        week_start, week_end = _get_last_week_range()
        month_start = _get_month_to_date_start()
        logger.info(
            "Last-week mode: week %s to %s | month from %s | Upload: %s",
            week_start, week_end, month_start,
            "skip" if skip_upload else "enabled",
        )
    elif start_date and end_date:
        logger.info(
            "Range: %s to %s | Upload: %s",
            start_date, end_date,
            "skip" if skip_upload else "enabled",
        )
    else:
        logger.info(
            "Lookback: %d days | Upload: %s | Incremental: %s",
            days, "skip" if skip_upload else "enabled", incremental,
        )

    # Idempotency check
    if not _check_idempotency(force):
        return

    # Step 1: Authenticate
    logger.info("Step 1/7: Authenticating with Google APIs")
    creds = authenticate()

    # Step 2: Fetch events
    logger.info("Step 2/7: Fetching calendar events")
    if last_week:
        # Fetch full month-to-date (covers both weekly and monthly needs)
        raw_df = fetch_events(
            creds, start_date=month_start, end_date=week_end,
        )
    else:
        raw_df = fetch_events(
            creds, days_back=days, incremental=incremental,
            start_date=start_date, end_date=end_date,
        )
    if raw_df.empty:
        logger.warning("No events found. Exiting.")
        return

    # Step 3: Process data
    logger.info("Step 3/7: Processing events")
    processed_df = process_events(raw_df)
    if processed_df.empty:
        logger.warning("No events after processing. Exiting.")
        return

    # Step 4: Feature engineering
    logger.info("Step 4/7: Engineering features")
    featured_df = engineer_features(processed_df)

    # Step 5: Split weekly and monthly data for --last-week mode
    if last_week:
        logger.info("Step 5/7: Splitting weekly and monthly data")
        week_start_date = date.fromisoformat(week_start)
        week_end_date = date.fromisoformat(week_end)
        weekly_df = featured_df[
            (featured_df["date"] >= week_start_date)
            & (featured_df["date"] <= week_end_date)
        ].copy()
        month_df = featured_df  # full month-to-date
        if weekly_df.empty:
            logger.warning("No events in last week. Exiting.")
            return
        logger.info(
            "Weekly: %d events (%.1fh) | Month-to-date: %d events (%.1fh)",
            len(weekly_df), weekly_df["duration_hours"].sum(),
            len(month_df), month_df["duration_hours"].sum(),
        )
    else:
        logger.info("Step 5/7: No split needed (single range)")
        weekly_df = featured_df

    # Step 6: Compute analytics (on weekly data)
    logger.info("Step 6/7: Computing analytics")
    analytics = compute_analytics(weekly_df)

    # Step 7: Generate reports
    logger.info("Step 7/7: Generating reports")
    report_files = generate_reports(weekly_df, analytics, month_df=month_df)

    # Optional: Upload to Drive
    if not skip_upload:
        logger.info("Uploading reports to Google Drive")
        links = upload_reports(creds, report_files)
        for item in links:
            logger.info("  %s: %s", item["name"], item["link"])
    else:
        logger.info("Upload skipped (--skip-upload)")

    # Optional: Upload to Notion
    if config.NOTION_TOKEN and not skip_notion:
        logger.info("Uploading data to Notion")
        now = datetime.now()
        iso = now.isocalendar()
        week_label = f"{iso[0]}_W{iso[1]:02d}"
        try:
            notion_results = upload_to_notion(
                notion_token=config.NOTION_TOKEN,
                df=weekly_df,
                result=analytics,
                week_label=week_label,
                force=force,
                parent_page_id=config.NOTION_PARENT_PAGE_ID,
            )
            for item in notion_results:
                logger.info(
                    "  Notion %s: %s (%d rows)",
                    item["database"], item["action"], item["count"],
                )
        except Exception:
            logger.exception("Notion upload failed (non-fatal)")
    elif skip_notion:
        logger.info("Notion upload skipped (--skip-notion)")
    else:
        logger.info("Notion upload skipped (NOTION_TOKEN not set)")

    # Save pipeline state
    save_state({
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "days_back": days,
        "events_fetched": len(raw_df),
        "events_processed": len(processed_df),
        "reports_generated": [str(f) for f in report_files],
    })

    logger.info("=== Pipeline complete ===")
    logger.info(
        "Summary: %.1f hours across %d events",
        analytics.total_hours,
        analytics.total_events,
    )


def main() -> None:
    setup_logging()
    args = parse_args()

    try:
        run(
            days=args.days,
            skip_upload=args.skip_upload,
            incremental=args.incremental,
            force=args.force,
            start_date=args.start,
            end_date=args.end,
            last_week=args.last_week,
            skip_notion=args.skip_notion,
        )
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception:
        logger.exception("Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
