import logging
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from . import config
from .analytics import AnalyticsResult

logger = logging.getLogger(__name__)


def generate_reports(
    df: pd.DataFrame,
    result: AnalyticsResult,
    month_df: pd.DataFrame = None,
) -> list[Path]:
    """Generate Excel and PNG reports.

    Args:
        df: Weekly event data (used for most sheets).
        result: Analytics computed from weekly data.
        month_df: Optional month-to-date data for the Monthly sheet.
                  If None, monthly data is derived from df.
    """
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    iso = now.isocalendar()
    week_label = f"{iso[0]}_W{iso[1]:02d}"
    month_label = now.strftime("%Y_%m")

    files = []
    files.append(_generate_excel(df, result, week_label, month_df=month_df))
    files.extend(_generate_charts(result, week_label, month_label, month_df=month_df))

    logger.info("Generated %d report files in %s", len(files), config.REPORT_DIR)
    return files


def _generate_excel(
    df: pd.DataFrame, result: AnalyticsResult, week_label: str,
    month_df: pd.DataFrame = None,
) -> Path:
    """Create Excel workbook with Summary, Weekly, Monthly, Categories sheets."""
    path = config.REPORT_DIR / f"weekly_report_{week_label}.xlsx"

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Summary sheet
        summary = pd.DataFrame(
            {
                "Metric": [
                    "Total Hours",
                    "Total Events",
                    "Avg Daily Hours",
                    "Consistency Score",
                    "Focus Score (HHI)",
                    "Max Streak (days)",
                    "Weekly Trend",
                    "Trend Slope (h/wk)",
                ],
                "Value": [
                    round(result.total_hours, 2),
                    result.total_events,
                    round(result.avg_daily_hours, 2),
                    round(result.consistency_score, 3),
                    round(result.focus_score, 3),
                    result.max_streak,
                    result.weekly_trend_direction,
                    result.weekly_trend_slope,
                ],
            }
        )
        summary.to_excel(writer, sheet_name="Summary", index=False)

        # Weekly sheet
        if not result.weekly_hours.empty:
            result.weekly_hours.to_excel(writer, sheet_name="Weekly", index=False)

        # Monthly sheet — cumulative month-to-date if available
        _write_monthly_sheet(writer, result, month_df)

        # Categories sheet
        if not result.category_ratios.empty:
            result.category_ratios.to_excel(writer, sheet_name="Categories", index=False)

        # Details sheet — per-job hour breakdown
        if "category" in df.columns and "duration_hours" in df.columns:
            _write_details(df, writer)

        # Raw data sheet
        export_cols = [
            c for c in ["date", "summary", "calendar_name", "category", "duration_hours", "day_of_week", "iso_week"]
            if c in df.columns
        ]
        if export_cols:
            df[export_cols].to_excel(writer, sheet_name="Raw Data", index=False)

    logger.info("Excel report: %s", path)
    return path


def _write_monthly_sheet(
    writer: pd.ExcelWriter, result: AnalyticsResult, month_df: pd.DataFrame = None,
) -> None:
    """Write the Monthly sheet with cumulative month-to-date data."""
    if month_df is not None and not month_df.empty:
        # Cumulative monthly breakdown by category and week
        monthly_by_cat = (
            month_df.groupby(["category"])["duration_hours"]
            .sum()
            .reset_index()
            .rename(columns={"duration_hours": "hours"})
            .sort_values("hours", ascending=False)
        )
        monthly_by_cat["hours"] = monthly_by_cat["hours"].round(2)

        # Weekly breakdown within the month
        monthly_by_week = (
            month_df.groupby(["iso_week"])["duration_hours"]
            .sum()
            .reset_index()
            .rename(columns={"duration_hours": "hours"})
            .sort_values("iso_week")
        )
        monthly_by_week["hours"] = monthly_by_week["hours"].round(2)

        # Total row
        total_hours = round(month_df["duration_hours"].sum(), 2)
        total_events = len(month_df)

        # Write month summary at top
        month_summary = pd.DataFrame([
            {"Metric": "Month Total Hours", "Value": total_hours},
            {"Metric": "Month Total Events", "Value": total_events},
        ])
        month_summary.to_excel(writer, sheet_name="Monthly", index=False, startrow=0)

        # Category breakdown
        row = len(month_summary) + 2
        monthly_by_cat.to_excel(writer, sheet_name="Monthly", index=False, startrow=row)

        # Weekly breakdown
        row += len(monthly_by_cat) + 2
        monthly_by_week.to_excel(writer, sheet_name="Monthly", index=False, startrow=row)
    elif not result.monthly_hours.empty:
        # Fallback: use analytics result
        result.monthly_hours.to_excel(writer, sheet_name="Monthly", index=False)


def _write_details(df: pd.DataFrame, writer: pd.ExcelWriter) -> None:
    """Write a Details sheet with job summary + full event log."""
    # --- Part 1: Job Summary table (top) ---
    job_summary = (
        df.groupby(["category", "summary"])
        .agg(sessions=("duration_hours", "count"), total_hours=("duration_hours", "sum"))
        .reset_index()
        .rename(columns={"summary": "job"})
        .sort_values(["category", "total_hours"], ascending=[True, False])
    )
    job_summary["total_hours"] = job_summary["total_hours"].round(2)

    # Add category totals
    cat_totals = (
        job_summary.groupby("category")
        .agg(sessions=("sessions", "sum"), total_hours=("total_hours", "sum"))
        .reset_index()
    )
    cat_totals["job"] = "** TOTAL **"
    cat_totals["total_hours"] = cat_totals["total_hours"].round(2)

    summary_rows = []
    for category, group in job_summary.groupby("category", sort=True):
        for _, row in group.iterrows():
            summary_rows.append(row.to_dict())
        cat_row = cat_totals[cat_totals["category"] == category].iloc[0].to_dict()
        summary_rows.append(cat_row)
        # Blank separator
        summary_rows.append({"category": "", "job": "", "sessions": "", "total_hours": ""})

    # Grand total
    summary_rows.append({
        "category": "",
        "job": "** GRAND TOTAL **",
        "sessions": int(job_summary["sessions"].sum()),
        "total_hours": round(job_summary["total_hours"].sum(), 2),
    })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.columns = ["Category", "Job", "Sessions", "Total Hours"]

    # --- Part 2: Full event log (flat table, filterable) ---
    detail_df = (
        df[["date", "category", "summary", "duration_hours"]]
        .copy()
        .sort_values(["category", "summary", "date"])
        .rename(columns={"summary": "Job", "date": "Date", "category": "Category", "duration_hours": "Hours"})
    )
    detail_df["Hours"] = detail_df["Hours"].round(2)
    detail_df["Date"] = detail_df["Date"].astype(str)

    # Write both to the same sheet: summary on top, detail below
    start_row = 0
    summary_df.to_excel(writer, sheet_name="Details", index=False, startrow=start_row)

    # Gap of 2 rows, then detail table
    detail_start = start_row + len(summary_df) + 3
    # Section header
    header_df = pd.DataFrame([{"Date": "--- Event Log ---", "Category": "", "Job": "", "Hours": ""}])
    header_df.to_excel(writer, sheet_name="Details", index=False, startrow=detail_start - 1, header=False)
    detail_df.to_excel(writer, sheet_name="Details", index=False, startrow=detail_start)


def _generate_charts(
    result: AnalyticsResult, week_label: str, month_label: str,
    month_df: pd.DataFrame = None,
) -> list[Path]:
    """Generate PNG charts and return list of file paths."""
    files = []

    # Monthly bar chart — use cumulative month_df if available
    if month_df is not None and not month_df.empty:
        path = config.REPORT_DIR / f"monthly_report_{month_label}.png"
        cat_hours = (
            month_df.groupby("category")["duration_hours"]
            .sum()
            .sort_values(ascending=False)
        )
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(cat_hours.index, cat_hours.values, color="#4285f4")
        ax.set_title(f"Month-to-Date Hours by Category ({month_label.replace('_', '-')})")
        ax.set_xlabel("Category")
        ax.set_ylabel("Hours")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        files.append(path)
        logger.info("Chart: %s", path)
    elif not result.monthly_hours.empty:
        path = config.REPORT_DIR / f"monthly_report_{month_label}.png"
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(result.monthly_hours["month"], result.monthly_hours["hours"], color="#4285f4")
        ax.set_title("Hours per Month")
        ax.set_xlabel("Month")
        ax.set_ylabel("Hours")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        files.append(path)
        logger.info("Chart: %s", path)

    # Weekly trend line
    if not result.weekly_hours.empty:
        path = config.REPORT_DIR / f"weekly_trend_{week_label}.png"
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(
            result.weekly_hours["iso_week"],
            result.weekly_hours["hours"],
            marker="o",
            color="#0f9d58",
            linewidth=2,
        )
        ax.set_title("Weekly Hours Trend")
        ax.set_xlabel("Week")
        ax.set_ylabel("Hours")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        files.append(path)
        logger.info("Chart: %s", path)

    # Category bar chart
    if not result.category_hours.empty:
        path = config.REPORT_DIR / f"category_distribution_{week_label}.png"
        fig, ax = plt.subplots(figsize=(10, 5))
        colors = plt.cm.Set2.colors
        bars = ax.barh(
            result.category_hours["category"],
            result.category_hours["hours"],
            color=[colors[i % len(colors)] for i in range(len(result.category_hours))],
        )
        ax.set_title("Hours by Category")
        ax.set_xlabel("Hours")
        ax.invert_yaxis()
        plt.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        files.append(path)
        logger.info("Chart: %s", path)

    return files
