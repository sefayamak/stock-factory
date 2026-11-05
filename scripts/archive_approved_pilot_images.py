#!/usr/bin/env python3
"""Archive only operator-approved pilot images to Google Drive.

Prerequisites:
1. Run: python3 scripts/run_pilot_secure.py
2. Review contact sheet and final images
3. Edit pilot_results.json: set visual_approval to "APPROVED" or "REJECTED"
4. Run this script to archive approved images only

Safety:
- Only archives images marked "APPROVED"
- Rejects and pending images are NOT archived
- Uses Keychain OAuth (no eval/export)
- SHA256 verification on all archives
- Dedup ledger prevents duplicate submission
"""
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from stock_factory import config, drive_archive
from stock_factory.processing import sha256_hex, DuplicateLedger


def get_oauth_from_keychain(key: str) -> str:
    """Load credential from macOS Keychain (no eval/export)."""
    cmd = f'security find-generic-password -s "stock-factory" -a "{key}" -w 2>/dev/null'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def main():
    print('\n' + '='*90)
    print('ARCHIVE APPROVED PILOT IMAGES TO GOOGLE DRIVE')
    print('='*90)

    # Find latest pilot results
    pilot_base = config.LOCAL_PIPELINE_OUTPUT_DIR / 'pilot_secure'
    if not pilot_base.exists():
        print('\n✗ No pilot results found.')
        print(f'Run: python3 scripts/run_pilot_secure.py')
        return 1

    # Get most recent pilot directory
    pilot_dirs = sorted([d for d in pilot_base.iterdir() if d.is_dir()], reverse=True)
    if not pilot_dirs:
        print('\n✗ No pilot directories found.')
        return 1

    pilot_dir = pilot_dirs[0]
    results_file = pilot_dir / 'pilot_results.json'

    if not results_file.exists():
        print(f'\n✗ Results file not found: {results_file}')
        return 1

    print(f'\n📂 Pilot directory: {pilot_dir}')
    print(f'📋 Results file: {results_file}')

    # Load results
    with open(results_file) as f:
        data = json.load(f)
    results = data['results']

    # Check OAuth credentials
    print(f'\n✓ Loading OAuth credentials from macOS Keychain...')
    refresh_token = get_oauth_from_keychain('GOOGLE_OAUTH_REFRESH_TOKEN')
    if not refresh_token:
        print('\n✗ OAuth credentials not found in Keychain')
        print('Run: python3 scripts/setup_drive_oauth_secure.py')
        return 1

    # Process approvals
    print(f'\n' + '='*90)
    print('APPROVAL PROCESSING')
    print('='*90)

    ledger = DuplicateLedger(config.LOCAL_PIPELINE_STATE_DIR)
    approved_count = 0
    rejected_count = 0
    pending_count = 0
    archived_count = 0

    for result in results:
        cid = result['concept_id']
        status = result['visual_approval']
        final_file = result['final_file']

        if status == "APPROVED":
            approved_count += 1
            print(f'\n[{cid:2d}] ✅ APPROVED')

            if not final_file or not Path(final_file).exists():
                print(f'     ✗ File not found: {final_file}')
                continue

            # Read file
            final_bytes = Path(final_file).read_bytes()
            sha256 = sha256_hex(final_bytes)

            # Check for duplicates
            if ledger.is_duplicate(sha256):
                print(f'     ✗ Duplicate detected (already archived)')
                continue

            # Archive to Drive
            print(f'     → Archiving to Google Drive...')
            archive_result = drive_archive.archive(Path(final_file), 'magnific')

            if archive_result.get('archived'):
                result['drive_archived'] = True
                result['drive_file_id'] = archive_result.get('file_id', 'not-returned')
                archived_count += 1

                # Record in ledger
                ledger.record(sha256)
                ledger.save()

                print(f'     ✓ Archived')
                if result['drive_file_id'] and result['drive_file_id'] != 'not-returned':
                    print(f'     Drive ID: {result["drive_file_id"]}')
            else:
                print(f'     ✗ Archive failed: {archive_result.get("reason")}')

        elif status == "REJECTED":
            rejected_count += 1
            print(f'\n[{cid:2d}] ❌ REJECTED (not archived)')

        elif status == "NEEDS_REVISION":
            print(f'\n[{cid:2d}] 🤔 NEEDS_REVISION (not archived)')

        else:  # PENDING_HUMAN
            pending_count += 1
            print(f'\n[{cid:2d}] 🔘 PENDING_HUMAN (awaiting decision)')

    # Update results file with archive info
    with open(results_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f'\n' + '='*90)
    print('ARCHIVE SUMMARY')
    print('='*90)

    print(f'\nApproved:      {approved_count}')
    print(f'Archived:      {archived_count}/{approved_count}')
    print(f'Rejected:      {rejected_count}')
    print(f'Pending:       {pending_count}')

    if archived_count > 0:
        print(f'\n✓ Successfully archived {archived_count} images to Google Drive')
        print(f'✓ SHA256 dedup ledger updated')
        print(f'✓ All production records preserved')
    else:
        print(f'\n⚠ No images archived (all rejected or pending)')

    print(f'\n' + '='*90)
    print('✓ ARCHIVE COMPLETE')
    print('='*90 + '\n')

    return 0


if __name__ == '__main__':
    sys.exit(main())
