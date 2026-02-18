import logging
from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from . import config

logger = logging.getLogger(__name__)

MIME_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".pdf": "application/pdf",
}


def upload_reports(creds: Credentials, files: list[Path]) -> list[dict]:
    """Upload report files to Google Drive, organized by Year-Month.

    Structure: Time Analytics Reports / 2026-02 / files...
    """
    service = build("drive", "v3", credentials=creds)
    root_id = _get_or_create_folder(service, config.DRIVE_FOLDER_NAME)

    # Create Year-Month subfolder (e.g. "2026-02")
    month_label = datetime.now().strftime("%Y-%m")
    month_folder_id = _get_or_create_folder(service, month_label, parent_id=root_id)

    uploaded = []
    for file_path in files:
        if not file_path.exists():
            logger.warning("File not found, skipping: %s", file_path)
            continue

        mime = MIME_TYPES.get(file_path.suffix, "application/octet-stream")
        file_metadata = {
            "name": file_path.name,
            "parents": [month_folder_id],
        }
        media = MediaFileUpload(str(file_path), mimetype=mime)

        result = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )

        link = result.get("webViewLink", "")
        uploaded.append({"name": file_path.name, "link": link})
        logger.info("Uploaded %s -> %s", file_path.name, link)

    logger.info(
        "Uploaded %d files to Drive: %s/%s",
        len(uploaded), config.DRIVE_FOLDER_NAME, month_label,
    )
    return uploaded


def _get_or_create_folder(
    service, folder_name: str, parent_id: str = None
) -> str:
    """Find existing folder by name (under parent) or create one. Returns folder ID."""
    query = (
        f"name = '{folder_name}' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, spaces="drive", fields="files(id)").execute()
    folders = results.get("files", [])

    if folders:
        folder_id = folders[0]["id"]
        logger.info("Found existing Drive folder '%s': %s", folder_name, folder_id)
        return folder_id

    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        folder_metadata["parents"] = [parent_id]

    folder = service.files().create(body=folder_metadata, fields="id").execute()
    folder_id = folder["id"]
    logger.info("Created Drive folder '%s': %s", folder_name, folder_id)
    return folder_id
