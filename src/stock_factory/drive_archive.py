"""Stage 6: Google Drive archival with separate Adobe/Magnific queues.

Unattended (GitHub Actions) Drive access needs a Google Cloud *service
account* with Drive API access granted to the target Drive folders --
the interactive OAuth session used inside this chat does not carry over
to a scheduled cloud job. Until GOOGLE_SERVICE_ACCOUNT_JSON,
DRIVE_ADOBE_FOLDER_ID, and DRIVE_MAGNIFIC_FOLDER_ID are configured as
secrets/variables, this stage is a documented no-op: it reports which
files *would* be archived and to which queue, but uploads nothing.
"""
from __future__ import annotations
from pathlib import Path
from . import config


def is_configured() -> bool:
    return bool(config.GOOGLE_SERVICE_ACCOUNT_JSON and config.DRIVE_ADOBE_FOLDER_ID and config.DRIVE_MAGNIFIC_FOLDER_ID)


def archive(path: Path, queue: str) -> dict:
    """queue: 'adobe' or 'magnific'. Returns a status dict; never raises for
    missing configuration -- that is an expected, reported state, not a bug."""
    if queue not in ('adobe', 'magnific'):
        raise ValueError(f'unknown queue: {queue}')
    if not is_configured():
        return {'archived': False, 'queue': queue, 'reason': 'drive_not_configured', 'file': path.name}

    # Real upload path -- exercised only once service-account credentials exist.
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import json

    creds_info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=['https://www.googleapis.com/auth/drive.file']
    )
    service = build('drive', 'v3', credentials=creds)
    folder_id = config.DRIVE_ADOBE_FOLDER_ID if queue == 'adobe' else config.DRIVE_MAGNIFIC_FOLDER_ID
    file_metadata = {'name': path.name, 'parents': [folder_id]}
    media = MediaFileUpload(str(path), mimetype='image/jpeg')
    uploaded = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return {'archived': True, 'queue': queue, 'file': path.name, 'drive_file_id': uploaded.get('id')}
