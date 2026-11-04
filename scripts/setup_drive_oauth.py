#!/usr/bin/env python3
"""One-time, interactive OAuth 2.0 authorization for the Stock Factory
Drive archival stage.

RUN THIS LOCALLY ON YOUR OWN MACHINE, AS YOURSELF. It is not meant to run
in CI and must never run anywhere that isn't under your direct control --
it opens a real Google sign-in/consent screen in your browser and the
refresh token it prints is a long-lived credential for your account.

Why this exists: the Stock Factory Drive folders live in a personal
Google My Drive account. A Google Cloud service account cannot own or
write files there even with folder "Editor" access -- Google enforces
this regardless of sharing settings. OAuth 2.0 user credentials (your own
account, consenting once) are the supported alternative.

What this script does:
  1. Opens your browser to Google's consent screen, scoped to the single
     minimum permission needed: https://www.googleapis.com/auth/drive.file
     (the app can only see/manage files *it* creates -- not your whole
     Drive, not files other apps created).
  2. Exchanges your consent for a refresh token.
  3. Prints the three values to set as GitHub Actions secrets. It does
     NOT write them to any file in this repository or anywhere in Drive.

Prerequisites (you do this once, in Google Cloud Console, in the existing
pam-cloud-508907 project -- no new project needed):
  1. APIs & Services -> OAuth consent screen -> configure it (External or
     Internal, your choice; "Testing" publishing status is fine since
     only your own account will ever use this client).
  2. APIs & Services -> Credentials -> Create Credentials -> OAuth client
     ID -> Application type: "Desktop app". Download the client secret.
  3. Run: pip install google-auth-oauthlib (not needed in CI, only here).
  4. Run this script with that client ID/secret:
       python3 scripts/setup_drive_oauth.py \
         --client-id YOUR_CLIENT_ID.apps.googleusercontent.com \
         --client-secret YOUR_CLIENT_SECRET
     or point it at the downloaded JSON:
       python3 scripts/setup_drive_oauth.py --client-secrets-file client_secret.json

After this script prints the refresh token, set these as GitHub secrets
(never commit them, never paste them into a chat/issue/PR):
  gh secret set GOOGLE_OAUTH_CLIENT_ID --body "<client id>"
  gh secret set GOOGLE_OAUTH_CLIENT_SECRET --body "<client secret>"
  gh secret set GOOGLE_OAUTH_REFRESH_TOKEN --body "<refresh token>"
"""
from __future__ import annotations
import argparse
import json
import sys

SCOPES = ['https://www.googleapis.com/auth/drive.file']


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--client-id', help='OAuth client ID (used with --client-secret)')
    ap.add_argument('--client-secret', help='OAuth client secret (used with --client-id)')
    ap.add_argument('--client-secrets-file', help='Path to the client_secret.json downloaded from Cloud Console')
    args = ap.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            'Missing dependency. Run: pip install google-auth-oauthlib\n'
            '(This is only needed for this one-time local setup script, not for the CI pipeline.)',
            file=sys.stderr,
        )
        raise SystemExit(1)

    if args.client_secrets_file:
        flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets_file, scopes=SCOPES)
    elif args.client_id and args.client_secret:
        client_config = {
            'installed': {
                'client_id': args.client_id,
                'client_secret': args.client_secret,
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
                'redirect_uris': ['http://localhost'],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    else:
        print('Provide either --client-secrets-file, or both --client-id and --client-secret.', file=sys.stderr)
        raise SystemExit(2)

    print('Opening your browser for Google sign-in and consent...')
    print(f'Requested scope (minimum needed): {SCOPES[0]}')
    creds = flow.run_local_server(port=0)

    print('\nSuccess. Set these as GitHub Actions secrets (never commit them):\n')
    print(f'  GOOGLE_OAUTH_CLIENT_ID={creds.client_id}')
    print(f'  GOOGLE_OAUTH_CLIENT_SECRET={creds.client_secret}')
    print(f'  GOOGLE_OAUTH_REFRESH_TOKEN={creds.refresh_token}')
    print(
        '\nOr non-interactively:\n'
        f'  gh secret set GOOGLE_OAUTH_CLIENT_ID --body "{creds.client_id}"\n'
        f'  gh secret set GOOGLE_OAUTH_CLIENT_SECRET --body "{creds.client_secret}"\n'
        f'  gh secret set GOOGLE_OAUTH_REFRESH_TOKEN --body "{creds.refresh_token}"\n'
    )
    if not creds.refresh_token:
        print(
            'WARNING: no refresh token was returned. This usually means you have authorized this '
            'client before and Google only issues a refresh token on first consent. Revoke prior '
            'access at https://myaccount.google.com/permissions and re-run this script.',
            file=sys.stderr,
        )


if __name__ == '__main__':
    main()
