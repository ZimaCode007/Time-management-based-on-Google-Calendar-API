import json
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import config

logger = logging.getLogger(__name__)


def authenticate() -> Credentials:
    """Authenticate with Google APIs using OAuth2.

    Uses existing token.json if valid, otherwise runs the OAuth flow
    with credentials.json.
    """
    creds = None

    if config.TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(config.TOKEN_FILE), config.SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired token")
            creds.refresh(Request())
        else:
            if not config.CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {config.CREDENTIALS_FILE}. "
                    "See setup_guide.md for instructions."
                )
            logger.info("Running OAuth flow — browser will open for authorization")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.CREDENTIALS_FILE), config.SCOPES
            )
            creds = flow.run_local_server(port=0)

        config.TOKEN_FILE.write_text(creds.to_json())
        logger.info("Token saved to %s", config.TOKEN_FILE)

    return creds


def fetch_events(
    creds: Credentials,
    days_back: int = None,
    incremental: bool = False,
    start_date: str = None,
    end_date: str = None,
) -> pd.DataFrame:
    """Fetch events from all Google Calendars.

    Args:
        creds: Authenticated Google credentials.
        days_back: Number of days to look back. Defaults to config value.
        incremental: If True, fetch only events updated since last run.
        start_date: Explicit start date (YYYY-MM-DD). Overrides days_back.
        end_date: Explicit end date (YYYY-MM-DD). Overrides days_back.

    Returns:
        DataFrame with columns: event_id, summary, calendar_name, start, end, created, updated.
    """
    service = build("calendar", "v3", credentials=creds)

    if start_date and end_date:
        # Explicit date range
        time_min = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
        time_max = (
            datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        ).isoformat()
        logger.info("Fetching events from %s to %s", start_date, end_date)
    else:
        if days_back is None:
            days_back = config.DEFAULT_LOOKBACK_DAYS
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=days_back)).isoformat()
        time_max = now.isoformat()
        logger.info("Fetching events from %d days back", days_back)

    # For incremental mode, use updatedMin from last run state
    updated_min = None
    if incremental:
        state = load_state()
        if state.get("last_run_utc"):
            updated_min = state["last_run_utc"]
            logger.info("Incremental mode: fetching events updated since %s", updated_min)

    # Fetch all calendars the user has access to
    calendars = _get_calendars(service)
    logger.info("Found %d calendars: %s", len(calendars), list(calendars.values()))

    all_events = []
    for cal_id, cal_name in calendars.items():
        page_token = None
        while True:
            params = dict(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            if updated_min:
                params["orderBy"] = "updated"
                params["updatedMin"] = updated_min

            response = service.events().list(**params).execute()

            for event in response.get("items", []):
                event["_calendar_name"] = cal_name

            all_events.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    logger.info("Fetched %d raw events across all calendars", len(all_events))

    # Save raw data for traceability
    _save_raw_events(all_events)

    return _normalize_events(all_events)


def _get_calendars(service) -> dict[str, str]:
    """Fetch all calendars. Returns {calendar_id: calendar_name}."""
    calendars = {}
    page_token = None

    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        for cal in response.get("items", []):
            calendars[cal["id"]] = cal.get("summary", cal["id"])
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return calendars


def _normalize_events(raw_events: list[dict]) -> pd.DataFrame:
    """Convert raw API response into a structured DataFrame."""
    records = []
    for event in raw_events:
        start = event.get("start", {})
        end = event.get("end", {})

        records.append(
            {
                "event_id": event.get("id"),
                "summary": event.get("summary", ""),
                "calendar_name": event.get("_calendar_name", ""),
                "start_raw": start.get("dateTime") or start.get("date"),
                "end_raw": end.get("dateTime") or end.get("date"),
                "is_all_day": "dateTime" not in start,
                "created": event.get("created"),
                "updated": event.get("updated"),
            }
        )

    return pd.DataFrame(records)


def _save_raw_events(raw_events: list[dict]) -> None:
    """Save raw API response to disk for traceability."""
    config.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = config.RAW_DATA_DIR / f"raw_events_{timestamp}.json"
    path.write_text(json.dumps(raw_events, indent=2, default=str))
    logger.info("Raw events saved to %s", path)


def load_state() -> dict:
    """Load pipeline state from disk."""
    if config.STATE_FILE.exists():
        return json.loads(config.STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    """Persist pipeline state to disk."""
    config.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.STATE_FILE.write_text(json.dumps(state, indent=2))
    logger.info("Pipeline state saved")
