import logging

import pandas as pd

from . import config

logger = logging.getLogger(__name__)


def process_events(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and enrich raw event data.

    - Removes all-day events
    - Removes zero-duration events
    - Converts timestamps to Europe/Berlin
    - Computes duration_hours
    - Adds date, week, month, day_of_week columns
    """
    if df.empty:
        logger.warning("No events to process")
        return df

    initial_count = len(df)

    # Remove all-day events
    df = df[~df["is_all_day"]].copy()
    logger.info("Removed %d all-day events", initial_count - len(df))

    # Parse datetimes
    df["start"] = pd.to_datetime(df["start_raw"], utc=True)
    df["end"] = pd.to_datetime(df["end_raw"], utc=True)

    # Validate: end must be after start
    invalid = df["end"] <= df["start"]
    if invalid.any():
        logger.warning("Removing %d events with invalid time ranges", invalid.sum())
        df = df[~invalid].copy()

    # Remove zero-duration events
    zero_dur = df["start"] == df["end"]
    if zero_dur.any():
        logger.info("Removing %d zero-duration events", zero_dur.sum())
        df = df[~zero_dur].copy()

    # Convert to configured timezone
    df["start"] = df["start"].dt.tz_convert(config.TIMEZONE)
    df["end"] = df["end"].dt.tz_convert(config.TIMEZONE)

    # Compute duration in hours
    df["duration_hours"] = (df["end"] - df["start"]).dt.total_seconds() / 3600

    # Add date-based columns
    df["date"] = df["start"].dt.date
    df["week"] = df["start"].dt.isocalendar().week.astype(int)
    df["year"] = df["start"].dt.year
    df["month"] = df["start"].dt.strftime("%Y-%m")
    df["day_of_week"] = df["start"].dt.day_name()

    # Drop intermediate columns
    df = df.drop(columns=["start_raw", "end_raw", "is_all_day"])

    logger.info("Processing complete: %d events retained from %d", len(df), initial_count)
    return df.reset_index(drop=True)
