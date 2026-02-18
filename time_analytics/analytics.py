import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsResult:
    """Container for all computed analytics metrics."""

    total_hours: float = 0.0
    total_events: int = 0
    avg_daily_hours: float = 0.0

    weekly_hours: pd.DataFrame = field(default_factory=pd.DataFrame)
    monthly_hours: pd.DataFrame = field(default_factory=pd.DataFrame)

    category_hours: pd.DataFrame = field(default_factory=pd.DataFrame)
    category_ratios: pd.DataFrame = field(default_factory=pd.DataFrame)

    consistency_score: float = 0.0
    focus_score: float = 0.0
    max_streak: int = 0

    # Trend analysis
    weekly_trend_slope: float = 0.0
    weekly_trend_direction: str = "stable"  # "increasing", "decreasing", "stable"


def compute_analytics(df: pd.DataFrame) -> AnalyticsResult:
    """Compute all analytics metrics from featured event data."""
    if df.empty:
        logger.warning("No data for analytics")
        return AnalyticsResult()

    result = AnalyticsResult()

    # Totals
    result.total_hours = df["duration_hours"].sum()
    result.total_events = len(df)
    unique_days = df["date"].nunique()
    result.avg_daily_hours = result.total_hours / unique_days if unique_days else 0

    # Weekly hours
    result.weekly_hours = (
        df.groupby("iso_week")["duration_hours"]
        .sum()
        .reset_index()
        .rename(columns={"duration_hours": "hours"})
        .sort_values("iso_week")
    )

    # Monthly hours
    result.monthly_hours = (
        df.groupby("month")["duration_hours"]
        .sum()
        .reset_index()
        .rename(columns={"duration_hours": "hours"})
        .sort_values("month")
    )

    # Category distribution
    result.category_hours = (
        df.groupby("category")["duration_hours"]
        .sum()
        .reset_index()
        .rename(columns={"duration_hours": "hours"})
        .sort_values("hours", ascending=False)
    )

    total = result.category_hours["hours"].sum()
    result.category_ratios = result.category_hours.copy()
    result.category_ratios["ratio"] = result.category_ratios["hours"] / total if total else 0

    # Consistency score: 1 / (1 + std of daily hours)
    daily_hours = df.groupby("date")["duration_hours"].sum()
    std = daily_hours.std()
    result.consistency_score = 1.0 / (1.0 + std) if pd.notna(std) else 1.0

    # Focus score: Herfindahl index on category shares
    # Higher = more concentrated (fewer categories dominate)
    if total > 0:
        shares = result.category_hours["hours"] / total
        result.focus_score = (shares**2).sum()
    else:
        result.focus_score = 0.0

    # Max streak
    result.max_streak = int(df["streak"].max()) if "streak" in df.columns else 0

    # Trend analysis: linear regression on weekly hours
    if len(result.weekly_hours) >= 2:
        y = result.weekly_hours["hours"].values
        x = np.arange(len(y), dtype=float)
        slope, _ = np.polyfit(x, y, 1)
        result.weekly_trend_slope = round(float(slope), 2)
        if slope > 0.5:
            result.weekly_trend_direction = "increasing"
        elif slope < -0.5:
            result.weekly_trend_direction = "decreasing"
        else:
            result.weekly_trend_direction = "stable"

    logger.info(
        "Analytics: %.1f total hours, %d events, consistency=%.2f, focus=%.2f, trend=%s (%.2f h/wk)",
        result.total_hours,
        result.total_events,
        result.consistency_score,
        result.focus_score,
        result.weekly_trend_direction,
        result.weekly_trend_slope,
    )

    return result
