"""Personal Time Analytics — Pipeline Orchestrator.

Usage:
    python -m time_analytics.main [--days N] [--start YYYY-MM-DD --end YYYY-MM-DD] [--skip-upload] [--incremental] [--force]
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

from . import config
from .analytics import compute_analytics
from .data_ingestion import authenticate, fetch_events, load_state, save_state
from .drive_uploader import upload_reports
from .feature_engineering import engineer_features
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
    return parser.parse_args()


def _check_idempotency(force: bool) -> bool:
    """Check if reports for the current period already exist.

    Returns True if pipeline should proceed, False to skip.
    """
    if force:
        return True

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
) -> None:
    """Execute the full analytics pipeline."""
    logger.info("=== Starting Time Analytics Pipeline ===")
    if start_date and end_date:
        logger.info(
            "Range: %s to %s | Upload: %s",
            start_date,
            end_date,
            "skip" if skip_upload else "enabled",
        )
    else:
        logger.info(
            "Lookback: %d days | Upload: %s | Incremental: %s",
            days,
            "skip" if skip_upload else "enabled",
            incremental,
        )

    # Idempotency check
    if not _check_idempotency(force):
        return

    # Step 1: Authenticate
    logger.info("Step 1/6: Authenticating with Google APIs")
    creds = authenticate()

    # Step 2: Fetch events
    logger.info("Step 2/6: Fetching calendar events")
    raw_df = fetch_events(
        creds, days_back=days, incremental=incremental,
        start_date=start_date, end_date=end_date,
    )
    if raw_df.empty:
        logger.warning("No events found. Exiting.")
        return

    # Step 3: Process data
    logger.info("Step 3/6: Processing events")
    processed_df = process_events(raw_df)
    if processed_df.empty:
        logger.warning("No events after processing. Exiting.")
        return

    # Step 4: Feature engineering
    logger.info("Step 4/6: Engineering features")
    featured_df = engineer_features(processed_df)

    # Step 5: Compute analytics
    logger.info("Step 5/6: Computing analytics")
    analytics = compute_analytics(featured_df)

    # Step 6: Generate reports
    logger.info("Step 6/6: Generating reports")
    report_files = generate_reports(featured_df, analytics)

    # Optional: Upload to Drive
    if not skip_upload:
        logger.info("Uploading reports to Google Drive")
        links = upload_reports(creds, report_files)
        for item in links:
            logger.info("  %s: %s", item["name"], item["link"])
    else:
        logger.info("Upload skipped (--skip-upload)")

    # Save pipeline state for incremental runs
    save_state({
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "days_back": days,
        "events_fetched": len(raw_df),
        "events_processed": len(processed_df),
        "reports_generated": [str(f) for f in report_files],
    })

    logger.info("=== Pipeline complete ===")
    logger.info(
        "Summary: %.1f hours across %d events over %d days",
        analytics.total_hours,
        analytics.total_events,
        days,
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
        )
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception:
        logger.exception("Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
