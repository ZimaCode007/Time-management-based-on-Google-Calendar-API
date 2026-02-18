import os
import re
from pathlib import Path

# Base directory (project root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Google API scopes
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

# Timezone
TIMEZONE = "Europe/Berlin"

# Lookback period
DEFAULT_LOOKBACK_DAYS = 30

# Report output directory
REPORT_DIR = BASE_DIR / "reports"

# Credential paths
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

# Category extraction pattern: matches [Tag] prefix in event titles
CATEGORY_PATTERN = re.compile(r"\[([^\]]+)\]")
DEFAULT_CATEGORY = "Uncategorized"

# Raw data directory (for traceability)
RAW_DATA_DIR = BASE_DIR / "data"

# State file for incremental updates and idempotency
STATE_FILE = BASE_DIR / "data" / "pipeline_state.json"

# Google Drive upload folder name
DRIVE_FOLDER_NAME = "Time Analytics Reports"
