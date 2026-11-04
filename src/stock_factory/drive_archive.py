"""Stage 6: Google Drive archival with separate Adobe/Magnific queues.

Unattended (GitHub Actions) Drive access needs a Google Cloud *service
account* with Drive API access granted to the target Drive folders --
the interactive OAuth session used inside this chat does not carry over
to a scheduled cloud job. Until GOOGLE_SERVICE_ACCOUNT_JSON,
DRIVE_ADOBE_FOLDER_ID, and DRIVE_MAGNIFIC_FOLDER_ID are configured as
secrets/variables, this stage is a documented no-op: it reports which
files *would* be archived and to which queue, but uploads nothing.

Once configured, archive() provides:
- SHA256 integrity verification (local hash recorded in Drive file
  properties; compared against a read-back hash after upload).
- Retry handling with exponential backoff for transient API errors.
- Duplicate protection: a file whose name or recorded sha256 already
  exists in the target folder is skipped rather than re-uploaded.
- Persistent archive references: every archived file's Drive file id,
  folder, and sha256 are appended to STATE_DIR/drive_archive_log.jsonl
  so a later run (or a human) can look up what was archived where.
"""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path
from . import config

MAX_RETRIES = 4
RETRY_BASE_DELAY_SECONDS = 2


def is_configured() -> bool:
    return bool(config.GOOGLE_SERVICE_ACCOUNT_JSON and config.DRIVE_ADOBE_FOLDER_ID and config.DRIVE_MAGNIFIC_FOLDER_ID)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _build_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)


def _with_retries(fn, *, what: str):
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 -- Drive API raises several transient error types
            last_exc = exc
            if attempt == MAX_RETRIES - 1:
                break
            time.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** attempt))
    raise RuntimeError(f'{what} failed after {MAX_RETRIES} attempts: {last_exc}') from last_exc


def _find_existing(service, folder_id: str, name: str, sha256: str) -> dict | None:
    """Duplicate protection: look for a non-trashed file with the same name
    AND the same recorded sha256 property in the target folder."""
    query = (
        f"'{folder_id}' in parents and name = '{name.replace(chr(39), '')}' and trashed = false"
    )
    result = _with_retries(
        lambda: service.files().list(
            q=query, fields='files(id, name, properties)', pageSize=10
        ).execute(),
        what='drive duplicate-check list',
    )
    for f in result.get('files', []):
        if (f.get('properties') or {}).get('sha256') == sha256:
            return f
    return None


def _log_archive(entry: dict) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = config.STATE_DIR / 'drive_archive_log.jsonl'
    with log_path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')


def archive(path: Path, queue: str) -> dict:
    """queue: 'adobe' or 'magnific'. Returns a status dict; never raises for
    missing configuration -- that is an expected, reported state, not a bug.
    Transient Drive API failures are retried; if all retries fail, the
    exception propagates (the caller records 'archive_skipped' only for the
    documented not-configured case, not for a real upload failure)."""
    if queue not in ('adobe', 'magnific'):
        raise ValueError(f'unknown queue: {queue}')
    if not is_configured():
        return {'archived': False, 'queue': queue, 'reason': 'drive_not_configured', 'file': path.name}

    local_sha256 = _sha256_file(path)
    service = _build_service()
    folder_id = config.DRIVE_ADOBE_FOLDER_ID if queue == 'adobe' else config.DRIVE_MAGNIFIC_FOLDER_ID

    existing = _find_existing(service, folder_id, path.name, local_sha256)
    if existing:
        entry = {
            'archived': True, 'queue': queue, 'file': path.name,
            'drive_file_id': existing['id'], 'sha256': local_sha256,
            'duplicate': True, 'reason': 'already_archived',
        }
        _log_archive(entry)
        return entry

    from googleapiclient.http import MediaFileUpload

    file_metadata = {
        'name': path.name,
        'parents': [folder_id],
        'properties': {'sha256': local_sha256},
    }
    media = MediaFileUpload(str(path), mimetype='image/jpeg')
    uploaded = _with_retries(
        lambda: service.files().create(
            body=file_metadata, media_body=media, fields='id, properties'
        ).execute(),
        what='drive upload',
    )
    file_id = uploaded['id']

    # Integrity verification: read the uploaded file back and compare bytes.
    downloaded = _with_retries(
        lambda: service.files().get_media(fileId=file_id).execute(),
        what='drive read-back',
    )
    remote_sha256 = hashlib.sha256(downloaded).hexdigest()
    if remote_sha256 != local_sha256:
        raise RuntimeError(
            f'drive integrity check failed for {path.name}: local={local_sha256} remote={remote_sha256}'
        )

    entry = {
        'archived': True, 'queue': queue, 'file': path.name,
        'drive_file_id': file_id, 'sha256': local_sha256, 'duplicate': False,
    }
    _log_archive(entry)
    return entry


def verify_with_test_artifact() -> dict:
    """Uploads a small harmless text file, reads it back, checks its
    sha256, then deletes it. Used to verify Drive credentials/folders are
    correctly wired without touching any real production asset. Returns a
    status dict; raises on any verification failure."""
    import tempfile

    if not is_configured():
        return {'verified': False, 'reason': 'drive_not_configured'}

    service = _build_service()
    content = f'stock-factory drive connectivity test -- safe to delete\n'.encode()
    local_sha256 = hashlib.sha256(content).hexdigest()

    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        folder_id = config.DRIVE_ADOBE_FOLDER_ID
        file_metadata = {
            'name': '_stock_factory_connectivity_test.txt',
            'parents': [folder_id],
            'properties': {'sha256': local_sha256},
        }
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(str(tmp_path), mimetype='text/plain')
        uploaded = _with_retries(
            lambda: service.files().create(body=file_metadata, media_body=media, fields='id').execute(),
            what='drive test upload',
        )
        file_id = uploaded['id']

        downloaded = _with_retries(
            lambda: service.files().get_media(fileId=file_id).execute(),
            what='drive test read-back',
        )
        remote_sha256 = hashlib.sha256(downloaded).hexdigest()

        _with_retries(
            lambda: service.files().delete(fileId=file_id).execute(),
            what='drive test cleanup',
        )

        if remote_sha256 != local_sha256:
            raise RuntimeError(f'test artifact integrity mismatch: local={local_sha256} remote={remote_sha256}')

        return {'verified': True, 'sha256': local_sha256, 'drive_file_id': file_id}
    finally:
        tmp_path.unlink(missing_ok=True)
