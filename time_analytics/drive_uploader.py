import logging
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
    """Upload report files to Google Drive.

    Creates or finds a target folder, uploads each file, and returns
    a list of dicts with file name and web link.
    """
    service = build("drive", "v3", credentials=creds)
    folder_id = _get_or_create_folder(service)

    uploaded = []
    for file_path in files:
        if not file_path.exists():
            logger.warning("File not found, skipping: %s", file_path)
            continue

        mime = MIME_TYPES.get(file_path.suffix, "application/octet-stream")
        file_metadata = {
            "name": file_path.name,
            "parents": [folder_id],
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

    logger.info("Uploaded %d files to Drive folder '%s'", len(uploaded), config.DRIVE_FOLDER_NAME)
    return uploaded


def _get_or_create_folder(service) -> str:
    """Find existing folder by name or create a new one. Returns folder ID."""
    query = (
        f"name = '{config.DRIVE_FOLDER_NAME}' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    results = service.files().list(q=query, spaces="drive", fields="files(id)").execute()
    folders = results.get("files", [])

    if folders:
        folder_id = folders[0]["id"]
        logger.info("Found existing Drive folder: %s", folder_id)
        return folder_id

    folder_metadata = {
        "name": config.DRIVE_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = service.files().create(body=folder_metadata, fields="id").execute()
    folder_id = folder["id"]
    logger.info("Created Drive folder: %s", folder_id)
    return folder_id
