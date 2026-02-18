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


def generate_reports(df: pd.DataFrame, result: AnalyticsResult) -> list[Path]:
    """Generate Excel and PNG reports. Returns list of created file paths."""
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Build period label from data (e.g. "2025_W03" or "2025-01")
    now = datetime.now()
    iso = now.isocalendar()
    week_label = f"{iso[0]}_W{iso[1]:02d}"
    month_label = now.strftime("%Y_%m")

    files = []
    files.append(_generate_excel(df, result, week_label))
    files.extend(_generate_charts(result, week_label, month_label))

    logger.info("Generated %d report files in %s", len(files), config.REPORT_DIR)
    return files


def _generate_excel(df: pd.DataFrame, result: AnalyticsResult, week_label: str) -> Path:
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

        # Monthly sheet
        if not result.monthly_hours.empty:
            result.monthly_hours.to_excel(writer, sheet_name="Monthly", index=False)

        # Categories sheet
        if not result.category_ratios.empty:
            result.category_ratios.to_excel(writer, sheet_name="Categories", index=False)

        # Work Log sheet — every event grouped by category with subtotals
        if "category" in df.columns and "duration_hours" in df.columns:
            _write_work_log(df, writer)

        # Raw data sheet
        export_cols = [
            c for c in ["date", "summary", "calendar_name", "category", "duration_hours", "day_of_week", "iso_week"]
            if c in df.columns
        ]
        if export_cols:
            df[export_cols].to_excel(writer, sheet_name="Raw Data", index=False)

    logger.info("Excel report: %s", path)
    return path


def _write_work_log(df: pd.DataFrame, writer: pd.ExcelWriter) -> None:
    """Write a Work Log sheet grouped by category → job name with subtotals."""
    rows = []
    sorted_df = df.sort_values(["category", "summary", "date"])

    for category, cat_group in sorted_df.groupby("category", sort=True):
        # Category header
        rows.append({"Date": "", "Job": f"=== {category} ===", "Hours": ""})

        # Group by job name (event summary) within each category
        for job_name, job_group in cat_group.groupby("summary", sort=True):
            # Job header
            rows.append({"Date": "", "Job": f"  {job_name}", "Hours": ""})

            # Individual sessions
            for _, event in job_group.iterrows():
                rows.append({
                    "Date": str(event["date"]),
                    "Job": "",
                    "Hours": round(event["duration_hours"], 2),
                })

            # Job subtotal
            rows.append({
                "Date": "",
                "Job": f"  Subtotal: {job_name}",
                "Hours": round(job_group["duration_hours"].sum(), 2),
            })

        # Category total
        rows.append({
            "Date": "",
            "Job": f"TOTAL ({category})",
            "Hours": round(cat_group["duration_hours"].sum(), 2),
        })
        # Blank separator
        rows.append({"Date": "", "Job": "", "Hours": ""})

    # Grand total
    rows.append({
        "Date": "",
        "Job": "GRAND TOTAL",
        "Hours": round(df["duration_hours"].sum(), 2),
    })

    pd.DataFrame(rows).to_excel(writer, sheet_name="Work Log", index=False)


def _generate_charts(
    result: AnalyticsResult, week_label: str, month_label: str
) -> list[Path]:
    """Generate PNG charts and return list of file paths."""
    files = []

    # Monthly bar chart
    if not result.monthly_hours.empty:
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
