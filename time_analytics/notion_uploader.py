"""Notion uploader — pushes weekly summary and event log to two Notion databases.

Public API:
    upload_to_notion(notion_token, df, result, week_label, force=False) -> list[dict]
"""

import logging
import time

import pandas as pd

from .analytics import AnalyticsResult

logger = logging.getLogger(__name__)

# Schema definitions for the two databases
_WEEKLY_SUMMARY_SCHEMA = {
    "Week": {"title": {}},
    "Total Hours": {"number": {"format": "number"}},
    "Events": {"number": {"format": "number"}},
    "Avg Daily": {"number": {"format": "number"}},
    "Consistency": {"number": {"format": "number"}},
    "Focus": {"number": {"format": "number"}},
    "Streak": {"number": {"format": "number"}},
    "Trend Direction": {"rich_text": {}},
    "Slope": {"number": {"format": "number"}},
}

_EVENT_LOG_SCHEMA = {
    "Job": {"title": {}},
    "Date": {"date": {}},
    "Category": {"select": {}},
    "Hours": {"number": {"format": "number"}},
    "Week": {"rich_text": {}},
    "Month": {"rich_text": {}},
}


def upload_to_notion(
    notion_token: str,
    df: pd.DataFrame,
    result: AnalyticsResult,
    week_label: str,
    force: bool = False,
    parent_page_id: str = "",
) -> list[dict]:
    """Push weekly summary and event log rows to Notion databases.

    Args:
        notion_token: Notion integration token (secret_...).
        df: Weekly event DataFrame (processed + featured).
        result: Analytics result for the week.
        week_label: e.g. "2026_W07" — used as unique key.
        force: If True, archive existing data and re-insert.
        parent_page_id: Notion page ID under which databases are created.

    Returns:
        List of dicts with {"database": str, "action": str, "count": int}.
    """
    client = _get_notion_client(notion_token)

    # Get or create both databases
    summary_db_id = _get_or_create_database(
        client, parent_page_id, "Weekly Summary", _WEEKLY_SUMMARY_SCHEMA
    )
    event_log_db_id = _get_or_create_database(
        client, parent_page_id, "Event Log", _EVENT_LOG_SCHEMA
    )

    results = []

    # Upsert Weekly Summary
    action = _upsert_weekly_summary(client, summary_db_id, result, week_label, force)
    results.append({"database": "Weekly Summary", "action": action, "count": 1})
    logger.info("Notion Weekly Summary: %s for week %s", action, week_label)

    # Upsert Event Log (bulk replace by week)
    count = _upsert_event_log(client, event_log_db_id, df, week_label, force)
    results.append({"database": "Event Log", "action": "replaced", "count": count})
    logger.info("Notion Event Log: inserted %d rows for week %s", count, week_label)

    return results


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_notion_client(token: str):
    """Initialize and return a Notion client."""
    from notion_client import Client
    return Client(auth=token)


def _get_or_create_database(client, parent_page_id: str, title: str, schema: dict) -> str:
    """Find an existing database by title under parent page, or create it.

    Returns the database ID.
    """
    # Search for existing database with this title
    try:
        response = client.search(query=title, filter={"value": "database", "property": "object"})
        for result in response.get("results", []):
            db_title = ""
            title_parts = result.get("title", [])
            if title_parts:
                db_title = "".join(t.get("plain_text", "") for t in title_parts)
            if db_title == title:
                db_id = result["id"]
                logger.info("Found existing Notion database '%s': %s", title, db_id)
                return db_id
    except Exception as exc:
        logger.warning("Notion search failed: %s", exc)

    # Create new database under parent page
    properties = {}
    for prop_name, prop_config in schema.items():
        properties[prop_name] = prop_config

    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    }
    db = client.databases.create(**payload)
    db_id = db["id"]
    logger.info("Created Notion database '%s': %s", title, db_id)
    return db_id


def _query_pages_by_property(client, db_id: str, prop_name: str, value: str) -> list[str]:
    """Query database for pages where a rich_text or title property equals value.

    Returns list of page IDs.
    """
    filter_payload = {
        "property": prop_name,
        "rich_text": {"equals": value},
    }
    try:
        response = client.databases.query(database_id=db_id, filter=filter_payload)
        return [page["id"] for page in response.get("results", [])]
    except Exception:
        # Fallback: try title filter
        try:
            filter_payload = {
                "property": prop_name,
                "title": {"equals": value},
            }
            response = client.databases.query(database_id=db_id, filter=filter_payload)
            return [page["id"] for page in response.get("results", [])]
        except Exception as exc:
            logger.warning("Notion query failed: %s", exc)
            return []


def _archive_pages(client, page_ids: list[str]) -> None:
    """Soft-delete (archive) Notion pages by ID."""
    for page_id in page_ids:
        try:
            client.pages.update(page_id=page_id, archived=True)
        except Exception as exc:
            logger.warning("Failed to archive Notion page %s: %s", page_id, exc)


def _upsert_weekly_summary(
    client, db_id: str, result: AnalyticsResult, week_label: str, force: bool
) -> str:
    """Insert or update the Weekly Summary page for this week.

    Returns: "skipped", "replaced", or "created".
    """
    existing_ids = _query_pages_by_property(client, db_id, "Week", week_label)

    if existing_ids and not force:
        logger.info("Notion Weekly Summary already exists for %s, skipping", week_label)
        return "skipped"

    if existing_ids and force:
        _archive_pages(client, existing_ids)

    properties = {
        "Week": {"title": [{"text": {"content": week_label}}]},
        "Total Hours": {"number": round(result.total_hours, 2)},
        "Events": {"number": result.total_events},
        "Avg Daily": {"number": round(result.avg_daily_hours, 2)},
        "Consistency": {"number": round(result.consistency_score, 3)},
        "Focus": {"number": round(result.focus_score, 3)},
        "Streak": {"number": result.max_streak},
        "Trend Direction": {"rich_text": [{"text": {"content": result.weekly_trend_direction}}]},
        "Slope": {"number": float(result.weekly_trend_slope)},
    }

    client.pages.create(parent={"database_id": db_id}, properties=properties)
    return "replaced" if existing_ids else "created"


def _upsert_event_log(
    client, db_id: str, df: pd.DataFrame, week_label: str, force: bool
) -> int:
    """Archive existing event log rows for this week and insert fresh rows.

    Returns: number of rows inserted.
    """
    existing_ids = _query_pages_by_property(client, db_id, "Week", week_label)

    if existing_ids and not force:
        logger.info(
            "Notion Event Log already has %d rows for %s, skipping",
            len(existing_ids), week_label,
        )
        return 0

    if existing_ids:
        _archive_pages(client, existing_ids)

    if df.empty or "summary" not in df.columns:
        return 0

    # Determine month label from date column
    inserted = 0
    for _, row in df.iterrows():
        try:
            date_val = row.get("date")
            date_str = str(date_val) if date_val is not None else ""
            month_str = date_str[:7] if len(date_str) >= 7 else ""

            job_name = str(row.get("summary", ""))[:2000]  # Notion title limit
            category = str(row.get("category", "Uncategorized"))
            hours = round(float(row.get("duration_hours", 0)), 2)

            properties = {
                "Job": {"title": [{"text": {"content": job_name}}]},
                "Date": {"date": {"start": date_str}} if date_str else {"date": None},
                "Category": {"select": {"name": category}},
                "Hours": {"number": hours},
                "Week": {"rich_text": [{"text": {"content": week_label}}]},
                "Month": {"rich_text": [{"text": {"content": month_str}}]},
            }
            client.pages.create(parent={"database_id": db_id}, properties=properties)
            inserted += 1

            # Respect Notion rate limit (~3 req/s)
            time.sleep(0.35)

        except Exception as exc:
            logger.warning("Failed to insert event log row: %s", exc)

    return inserted
