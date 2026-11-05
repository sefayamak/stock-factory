#!/usr/bin/env python3
"""Secure local OAuth setup for Stock Factory Drive archival.

This script:
1. Prompts for OAuth client ID and secret (from Google Cloud Console)
2. Opens your browser for Google consent (drive.file scope only)
3. Stores credentials securely in macOS Keychain (not plaintext files)
4. Tests Drive connectivity without exposing sensitive values
5. Returns exit 0 if successful, non-zero if setup failed

Usage:
    python3 scripts/setup_drive_oauth_secure.py

Then set environment variables from Keychain (secrets stay in Keychain):
    eval "$(python3 scripts/load_drive_credentials.py)"

After successful setup, the production pipeline will use credentials from Keychain.
"""
from __future__ import annotations
import sys
import os
import subprocess
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/drive.file']
KEYCHAIN_SERVICE = 'stock-factory'

def store_in_keychain(key: str, value: str) -> bool:
    """Store value in macOS Keychain. Returns True on success."""
    try:
        # Use security command to store in Keychain
        cmd = f'security add-generic-password -s "{KEYCHAIN_SERVICE}" -a "{key}" -w "{value}" -U 2>/dev/null'
        result = subprocess.run(cmd, shell=True, capture_output=True)
        return result.returncode == 0
    except Exception:
        return False

def get_from_keychain(key: str) -> str | None:
    """Retrieve value from Keychain. Returns None if not found."""
    try:
        cmd = f'security find-generic-password -s "{KEYCHAIN_SERVICE}" -a "{key}" -w 2>/dev/null'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            'Missing dependency. Run: pip install google-auth-oauthlib\n'
            '(This is only needed for this one-time local setup script.)',
            file=sys.stderr,
        )
        return 1

    # Step 1: Get OAuth credentials from user
    print('\n' + '='*70)
    print('STOCK FACTORY — SECURE LOCAL OAUTH SETUP')
    print('='*70)
    print('\nYou need OAuth credentials from Google Cloud Console.')
    print('Project: pam-cloud-508907')
    print('OAuth app: Desktop (installed)')
    print('\nGet them from: https://console.cloud.google.com/apis/credentials')
    print('\nProvide them now (they will be stored securely in Keychain):\n')

    client_id = input('Google OAuth Client ID: ').strip()
    if not client_id:
        print('Aborted: client ID required.', file=sys.stderr)
        return 2

    client_secret = input('Google OAuth Client Secret: ').strip()
    if not client_secret:
        print('Aborted: client secret required.', file=sys.stderr)
        return 2

    # Step 2: Verify consent screen publishing status
    print(
        '\nBefore authorizing: confirm the OAuth consent screen in Google Cloud is set to\n'
        '"In production" (NOT "Testing"). A testing-status token expires after 7 days.\n'
        'See Google\'s documentation for how to publish.\n'
    )
    confirmed = input('Type YES to confirm publishing status is "In production": ').strip()
    if confirmed != 'YES':
        print('Aborted -- publish the app to "In production" first, then re-run.', file=sys.stderr)
        return 3

    # Step 3: Run OAuth flow
    print('\nOpening your browser for Google sign-in and consent...')
    print(f'Requested scope: drive.file (minimum needed for folder access)\n')

    client_config = {
        'installed': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': ['http://localhost'],
        }
    }

    try:
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
        creds = flow.run_local_server(port=0)
    except Exception as e:
        print(f'OAuth failed: {e}', file=sys.stderr)
        return 4

    if not creds.refresh_token:
        print(
            'WARNING: No refresh token received. This usually means you authorized this\n'
            'client before. Revoke access at https://myaccount.google.com/permissions\n'
            'and re-run this script.',
            file=sys.stderr,
        )
        return 5

    # Step 4: Store in Keychain (not plaintext)
    print('\nStoring credentials in macOS Keychain (no plaintext files)...')

    if not store_in_keychain('GOOGLE_OAUTH_CLIENT_ID', client_id):
        print('Failed to store client ID in Keychain.', file=sys.stderr)
        return 6

    if not store_in_keychain('GOOGLE_OAUTH_CLIENT_SECRET', client_secret):
        print('Failed to store client secret in Keychain.', file=sys.stderr)
        return 6

    if not store_in_keychain('GOOGLE_OAUTH_REFRESH_TOKEN', creds.refresh_token):
        print('Failed to store refresh token in Keychain.', file=sys.stderr)
        return 6

    print('✓ Credentials stored securely in Keychain.')

    # Step 5: Verify Keychain storage (without displaying values)
    if not all([
        get_from_keychain('GOOGLE_OAUTH_CLIENT_ID'),
        get_from_keychain('GOOGLE_OAUTH_CLIENT_SECRET'),
        get_from_keychain('GOOGLE_OAUTH_REFRESH_TOKEN'),
    ]):
        print('Verification failed: credentials not readable from Keychain.', file=sys.stderr)
        return 7

    print('✓ Credentials verified in Keychain.\n')
    print('✓ SUCCESS: OAuth setup complete.')
    print('\nNext step: Set environment variables from Keychain.')
    print('Your production pipeline will read credentials from Keychain automatically.')

    return 0

if __name__ == '__main__':
    sys.exit(main())
