#!/usr/bin/env python3
"""Real (non-mocked) Drive connectivity gate -- run this once the owner
has completed the one-time OAuth setup (scripts/setup_drive_oauth.py) and
the 5 GitHub secrets/variables are set, before treating Drive archival as
production-ready.

This performs three checks, each against the REAL Google Drive API (no
mocks, no stubs):

  1. verify_both_queues()          -- uploads a harmless test file into
     EACH of the two real pre-existing target folders (Adobe, Magnific),
     reads it back, verifies its sha256, then deletes it. This is the
     only way to confirm drive.file-scoped user credentials can actually
     write into those specific pre-existing folders -- folder IDs alone
     do not guarantee it.
  2. verify_token_refresh_is_durable() -- builds OAuth credentials from
     the stored refresh token twice, simulating two independent
     unattended runs. Does not wait 7 days; see its docstring for what
     this does and does not prove.
  3. Confirms no original production file was touched: this script never
     reads, lists, or deletes anything except the test file it itself
     created, by construction (it only ever calls service.files().create
     for a name it generates itself, then deletes that same file id).

Exit code 0 only if every check passes. Never prints token/credential
values -- only PASS/FAIL per check and non-secret metadata (file ids,
sha256 of the harmless test content, which is public/constant anyway).

Usage:
  PYTHONPATH=src python3 scripts/verify_drive_connectivity.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from stock_factory import config, drive_archive  # noqa: E402


def main() -> int:
    if not drive_archive.is_configured():
        print('FAIL: Drive is not configured (missing OAuth credentials and/or folder IDs). Nothing was attempted.')
        return 1
    if not drive_archive._oauth_configured():
        print(
            'FAIL: no OAuth credentials configured. This project does not treat a service account as '
            'production-ready for these personal-My-Drive folders -- see docs/ADAPTERS.md.'
        )
        return 1

    all_ok = True

    print('[1/2] Checking OAuth token refresh is durable (two independent builds)...')
    try:
        refresh_result = drive_archive.verify_token_refresh_is_durable()
        if refresh_result.get('verified'):
            print('  PASS: token refreshed successfully twice.')
        else:
            print(f'  FAIL: {refresh_result}')
            all_ok = False
    except Exception as exc:  # noqa: BLE001
        print(f'  FAIL: token refresh raised: {exc}')
        all_ok = False

    print('[2/2] Checking real write/readback/sha256/cleanup against both pre-existing folders...')
    try:
        queue_results = drive_archive.verify_both_queues()
        for queue, result in queue_results.items():
            if result.get('verified'):
                print(f'  PASS ({queue}): uploaded, read back, sha256 matched, test file deleted. '
                      f'drive_file_id={result.get("drive_file_id")} (no longer exists -- cleaned up)')
            else:
                print(f'  FAIL ({queue}): {result}')
                all_ok = False
    except Exception as exc:  # noqa: BLE001
        print(f'  FAIL: real Drive check raised: {exc}')
        all_ok = False

    print()
    if all_ok:
        print('ALL CHECKS PASSED. Only the test artifacts created by this script were touched; '
              'nothing else in either folder was read, modified, or deleted.')
        return 0
    print('ONE OR MORE CHECKS FAILED. Do not treat Drive archival as production-ready until this passes.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
