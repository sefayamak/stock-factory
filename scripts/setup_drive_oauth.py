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

*** PUBLISHING STATUS -- DO THIS OR THE SETUP WILL SILENTLY BREAK IN A WEEK ***
If your OAuth consent screen's publishing status is "Testing" when you
run this script, the refresh token Google issues for a sensitive scope
(drive.file is sensitive) EXPIRES AFTER 7 DAYS. The pipeline will work
for a week and then every unattended run will start failing with an
invalid_grant error -- with no code change, nothing looks "broken" until
it silently stops archiving. "Testing" is NOT suitable for unattended
production use, however briefly convenient it looks.

Before running this script, set the consent screen's publishing status to
"In production" (OAuth consent screen -> click "PUBLISH APP"). This is
the supported configuration for a single-user production app and removes
the 7-day cap. You do NOT need to submit the app for Google's formal
verification review to do this -- verification is required before "In
production" only for apps expected to serve many/unknown users or that
request "restricted" scopes (drive.file is "sensitive", not
"restricted" -- see https://developers.google.com/identity/protocols/oauth2/scopes).
With only you as the consenting user, publishing without verification is
the normal path; the one consequence is that during the one-time consent
below, Google shows an "unverified app" interstitial that you click
through once ("Advanced" -> "Go to <app name> (unsafe)") -- expected and
fine for a tool only you authorize. (This reflects Google's documented
policy as of this writing; if Google changes that policy, re-check before
relying on it.)

What this script does:
  1. Opens your browser to Google's consent screen, scoped to the single
     minimum permission needed: https://www.googleapis.com/auth/drive.file
     (the app can only see/manage files *it* creates -- not your whole
     Drive, not files other apps created; see docs/ADAPTERS.md for why
     this is still sufficient to write into our pre-existing folders, and
     why that claim must be verified for real before relying on it).
  2. Exchanges your consent for a refresh token.
  3. Prints the three values for YOU to set as GitHub Actions secrets, to
     your own terminal only. It does NOT write them to any file in this
     repository, to Drive, or anywhere else, and this script is never run
     in CI.

Prerequisites (you do this once, in Google Cloud Console, in the existing
pam-cloud-508907 project -- no new project needed):
  1. APIs & Services -> OAuth consent screen -> configure it. User type
     must be "External" (personal Google accounts cannot use "Internal",
     which is Workspace-only). Add your own email as a test user, finish
     the required fields, THEN CLICK "PUBLISH APP" to move publishing
     status from "Testing" to "In production" (see warning above).
  2. APIs & Services -> Credentials -> Create Credentials -> OAuth client
     ID -> Application type: "Desktop app". Download the client secret.
  3. Run: pip install google-auth-oauthlib (not needed in CI, only here).
  4. Run this script with that client ID/secret:
       python3 scripts/setup_drive_oauth.py \
         --client-id YOUR_CLIENT_ID.apps.googleusercontent.com \
         --client-secret YOUR_CLIENT_SECRET
     or point it at the downloaded JSON:
       python3 scripts/setup_drive_oauth.py --client-secrets-file client_secret.json
     You will see the "unverified app" warning during consent -- click
     Advanced -> Go to <app name> (unsafe) to proceed; this is expected.

After this script prints the refresh token to YOUR OWN TERMINAL, set
these as GitHub secrets yourself (never commit them, never paste them
into a chat/issue/PR, never let an assistant run these commands for you
with the real values filled in):
  gh secret set GOOGLE_OAUTH_CLIENT_ID --body "<client id>"
  gh secret set GOOGLE_OAUTH_CLIENT_SECRET --body "<client secret>"
  gh secret set GOOGLE_OAUTH_REFRESH_TOKEN --body "<refresh token>"

Then run the GitHub Actions workflow "Stock Factory - verify Drive
connectivity" (workflow_dispatch, .github/workflows/verify-drive.yml) to
run the REAL (non-mocked) write/readback/sha256/cleanup and token-refresh
checks before considering Drive archival production-ready -- see
scripts/verify_drive_connectivity.py and docs/ADAPTERS.md.
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

    print(
        '\nBefore continuing: has the OAuth consent screen\'s publishing status been set to\n'
        '"In production" (NOT "Testing")? A refresh token issued while still in "Testing"\n'
        'status expires after 7 days for this scope, and the pipeline will silently stop\n'
        'archiving a week from now with no code change. See the warning at the top of this\n'
        'script\'s docstring.\n'
    )
    confirmed = input('Type YES to confirm publishing status is "In production": ').strip()
    if confirmed != 'YES':
        print('Aborted -- publish the app to "In production" first, then re-run this script.', file=sys.stderr)
        raise SystemExit(3)

    print('\nOpening your browser for Google sign-in and consent...')
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
