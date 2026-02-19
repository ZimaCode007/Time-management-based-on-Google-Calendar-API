import logging
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from . import config
from .analytics import AnalyticsResult

logger = logging.getLogger(__name__)


def generate_reports(
    df: pd.DataFrame,
    result: AnalyticsResult,
    month_df: pd.DataFrame = None,
) -> list[Path]:
    """Generate Excel and chart reports.

    Args:
        df: Weekly event data.
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
    """Create Excel workbook with 3 sheets: Summary, Weekly, Monthly."""
    path = config.REPORT_DIR / f"weekly_report_{week_label}.xlsx"

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Sheet 1: Summary — metrics table
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

        # Sheet 2: Weekly — job-level breakdown for the week
        if "category" in df.columns and "duration_hours" in df.columns:
            _write_details_sheet(df, writer, "Weekly")

        # Sheet 3: Monthly — job-level breakdown for the month
        target_df = month_df if (month_df is not None and not month_df.empty) else df
        if "category" in target_df.columns and "duration_hours" in target_df.columns:
            _write_details_sheet(target_df, writer, "Monthly")

    logger.info("Excel report: %s", path)
    return path


def _write_details_sheet(df: pd.DataFrame, writer: pd.ExcelWriter, sheet_name: str) -> None:
    """Write a sheet with Job Summary table on top and Event Log below.

    Args:
        df: Event DataFrame with at least category, summary, duration_hours, date columns.
        writer: Active ExcelWriter instance.
        sheet_name: Name of the sheet to write to.
    """
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

    # Write job summary at top
    start_row = 0
    summary_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=start_row)

    # Gap of 2 rows, then event log
    detail_start = start_row + len(summary_df) + 3
    header_df = pd.DataFrame([{"Date": "--- Event Log ---", "Category": "", "Job": "", "Hours": ""}])
    header_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=detail_start - 1, header=False)
    detail_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=detail_start)


def _save_plotly_fig(fig: go.Figure, base_path: Path) -> list[Path]:
    """Export a Plotly figure as both HTML and PNG.

    Args:
        fig: Plotly figure to export.
        base_path: Path without extension (e.g. reports/weekly_trend_2026_W07).

    Returns:
        [html_path, png_path]
    """
    html_path = base_path.with_suffix(".html")
    png_path = base_path.with_suffix(".png")

    fig.write_html(str(html_path), include_plotlyjs="cdn")
    fig.write_image(str(png_path), width=1000, height=500, scale=1.5)

    return [html_path, png_path]


def _generate_charts(
    result: AnalyticsResult, week_label: str, month_label: str,
    month_df: pd.DataFrame = None,
) -> list[Path]:
    """Generate Plotly charts (HTML + PNG) and return list of file paths."""
    files = []

    # Chart 1: Monthly bar — hours by category (cumulative month-to-date)
    if month_df is not None and not month_df.empty:
        cat_hours = (
            month_df.groupby("category")["duration_hours"]
            .sum()
            .reset_index()
            .rename(columns={"duration_hours": "hours"})
            .sort_values("hours", ascending=False)
        )
        cat_hours["hours"] = cat_hours["hours"].round(2)
        fig = px.bar(
            cat_hours,
            x="category",
            y="hours",
            color="category",
            text="hours",
            title=f"Month-to-Date Hours by Category ({month_label.replace('_', '-')})",
            labels={"category": "Category", "hours": "Hours"},
            template="plotly_white",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        base = config.REPORT_DIR / f"monthly_report_{month_label}"
        files.extend(_save_plotly_fig(fig, base))
        logger.info("Chart: %s (.html + .png)", base)
    elif not result.monthly_hours.empty:
        fig = px.bar(
            result.monthly_hours,
            x="month",
            y="hours",
            text="hours",
            title="Hours per Month",
            labels={"month": "Month", "hours": "Hours"},
            template="plotly_white",
        )
        fig.update_traces(textposition="outside")
        base = config.REPORT_DIR / f"monthly_report_{month_label}"
        files.extend(_save_plotly_fig(fig, base))
        logger.info("Chart: %s (.html + .png)", base)

    # Chart 2: Weekly trend line
    if not result.weekly_hours.empty:
        weekly = result.weekly_hours.copy()
        weekly["hours"] = weekly["hours"].round(2)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=weekly["iso_week"].astype(str),
            y=weekly["hours"],
            mode="lines+markers+text",
            text=weekly["hours"],
            textposition="top center",
            line=dict(color="#0f9d58", width=2),
            marker=dict(size=8),
            name="Hours",
        ))
        fig.update_layout(
            title="Weekly Hours Trend",
            xaxis_title="Week",
            yaxis_title="Hours",
            template="plotly_white",
        )
        base = config.REPORT_DIR / f"weekly_trend_{week_label}"
        files.extend(_save_plotly_fig(fig, base))
        logger.info("Chart: %s (.html + .png)", base)

    # Chart 3: Category horizontal bar
    if not result.category_hours.empty:
        cat = result.category_hours.copy()
        cat["hours"] = cat["hours"].round(2)
        # Reverse order so highest is at top
        cat = cat.sort_values("hours", ascending=True)
        fig = px.bar(
            cat,
            x="hours",
            y="category",
            orientation="h",
            color="category",
            text="hours",
            title="Hours by Category (This Week)",
            labels={"category": "Category", "hours": "Hours"},
            template="plotly_white",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False, yaxis=dict(autorange="reversed"))
        base = config.REPORT_DIR / f"category_distribution_{week_label}"
        files.extend(_save_plotly_fig(fig, base))
        logger.info("Chart: %s (.html + .png)", base)

    return files
