import logging

import pandas as pd

from . import config

logger = logging.getLogger(__name__)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract features from processed event data.

    - Extract category from [Tag] prefix in summary
    - Add ISO week number and year-week key
    - Compute active-day streaks
    - Compute time distribution ratios per category
    """
    if df.empty:
        logger.warning("No events for feature engineering")
        return df

    df = df.copy()

    # Extract category: [Tag] in title overrides calendar name
    df["category"] = df.apply(_extract_category, axis=1)
    logger.info(
        "Categories found: %s",
        df["category"].value_counts().to_dict(),
    )

    # ISO week key (e.g. "2025-W03")
    iso = df["start"].dt.isocalendar()
    df["iso_week"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)

    # Active-day streak
    df["streak"] = _compute_streaks(df)

    # Category time distribution ratio (per-event share of its day's total)
    daily_total = df.groupby("date")["duration_hours"].transform("sum")
    df["daily_ratio"] = df["duration_hours"] / daily_total

    return df


def _extract_category(row: pd.Series) -> str:
    """Determine event category.

    Priority:
    1. [Tag] in event title (explicit override)
    2. Calendar name (from Google Calendar)
    3. DEFAULT_CATEGORY fallback
    """
    match = config.CATEGORY_PATTERN.search(row["summary"])
    if match:
        return match.group(1).strip()

    calendar_name = row.get("calendar_name", "")
    if calendar_name:
        return calendar_name

    return config.DEFAULT_CATEGORY


def _compute_streaks(df: pd.DataFrame) -> pd.Series:
    """Compute consecutive active-day streak for each event's date.

    An active day is any date with at least one event. The streak value
    for each event is the number of consecutive days ending on that
    event's date.
    """
    unique_dates = sorted(df["date"].unique())

    if not unique_dates:
        return pd.Series(0, index=df.index)

    # Build a mapping: date -> streak length
    streak_map = {}
    current_streak = 1
    streak_map[unique_dates[0]] = 1

    for i in range(1, len(unique_dates)):
        prev = unique_dates[i - 1]
        curr = unique_dates[i]
        delta = (pd.Timestamp(curr) - pd.Timestamp(prev)).days

        if delta == 1:
            current_streak += 1
        else:
            current_streak = 1

        streak_map[curr] = current_streak

    return df["date"].map(streak_map).fillna(0).astype(int)
