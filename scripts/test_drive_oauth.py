#!/usr/bin/env python3
"""Test Drive OAuth connectivity and upload/readback/SHA256 verification.

Usage:
    eval "$(python3 scripts/load_drive_credentials.py)"
    python3 scripts/test_drive_oauth.py

This script:
1. Loads OAuth credentials from environment (populated from Keychain)
2. Creates a disposable test file in STOCK_FACTORY_MAGNIFIC_OUTPUT folder
3. Uploads it to Drive
4. Verifies readback and SHA256 hash
5. Cleans up the test file
"""
from __future__ import annotations
import sys
import os
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timezone

def get_cred(name: str) -> str:
    """Get credential from environment. Must be loaded from Keychain first."""
    value = os.getenv(name)
    if not value:
        print(f'ERROR: {name} not in environment.', file=sys.stderr)
        print('Run: eval "$(python3 scripts/load_drive_credentials.py)"', file=sys.stderr)
        sys.exit(1)
    return value

def main() -> int:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        print(
            'Missing Google API dependencies. Run:\n'
            'pip install google-auth-oauthlib google-api-python-client',
            file=sys.stderr,
        )
        return 1

    print('\n' + '='*70)
    print('STOCK FACTORY — DRIVE OAUTH TEST')
    print('='*70)

    # Load credentials from environment (populated from Keychain)
    client_id = get_cred('GOOGLE_OAUTH_CLIENT_ID')
    client_secret = get_cred('GOOGLE_OAUTH_CLIENT_SECRET')
    refresh_token = get_cred('GOOGLE_OAUTH_REFRESH_TOKEN')
    folder_id = get_cred('DRIVE_MAGNIFIC_FOLDER_ID')

    print(f'\nUsing folder: {folder_id}')
    print('Testing: upload → readback → SHA256 → cleanup\n')

    # Reconstruct credentials object
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
    )

    # Refresh to get a valid access token
    try:
        request = Request()
        creds.refresh(request)
    except Exception as e:
        print(f'Failed to refresh token: {e}', file=sys.stderr)
        return 2

    print('✓ Token refreshed successfully.')

    # Build Drive service
    service = build('drive', 'v3', credentials=creds)

    # Create test file
    test_content = b'Stock Factory OAuth test file\n'
    test_content += f'Created: {datetime.now(timezone.utc).isoformat()}\n'.encode()
    test_sha256 = hashlib.sha256(test_content).hexdigest()

    test_filename = 'test-oauth-disposable.txt'
    print(f'\n1. Creating test file: {test_filename}')
    print(f'   Content SHA256: {test_sha256}')

    # Upload test file
    from googleapiclient.http import MediaIoBaseUpload
    import io

    try:
        media = MediaIoBaseUpload(io.BytesIO(test_content), mimetype='text/plain')
        file_metadata = {'name': test_filename, 'parents': [folder_id]}
        result = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
        ).execute()
        test_file_id = result['id']
        print(f'   ✓ Uploaded: {test_file_id}')
    except HttpError as e:
        print(f'Upload failed: {e}', file=sys.stderr)
        return 3

    # Readback and verify SHA256
    print(f'\n2. Reading back test file...')
    try:
        request = service.files().get_media(fileId=test_file_id)
        readback_content = request.execute()
        readback_sha256 = hashlib.sha256(readback_content).hexdigest()
        print(f'   Readback SHA256: {readback_sha256}')

        if readback_sha256 == test_sha256:
            print(f'   ✓ SHA256 matches (integrity verified)')
        else:
            print(f'   ✗ SHA256 mismatch!', file=sys.stderr)
            return 4
    except HttpError as e:
        print(f'Readback failed: {e}', file=sys.stderr)
        return 5

    # Cleanup: delete test file
    print(f'\n3. Cleaning up test file...')
    try:
        service.files().delete(fileId=test_file_id).execute()
        print(f'   ✓ Deleted {test_filename}')
    except HttpError as e:
        print(f'Cleanup failed: {e}', file=sys.stderr)
        return 6

    print('\n' + '='*70)
    print('✓ SUCCESS: Drive OAuth test passed.')
    print('✓ Upload, readback, and SHA256 verification all successful.')
    print('='*70 + '\n')

    return 0

if __name__ == '__main__':
    sys.exit(main())
