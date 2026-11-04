#!/usr/bin/env python3
"""One-off/occasional tool: seed processing.DuplicateLedger's persistent
sha256 ledger with hashes of files already in the existing Adobe/Magnific
catalogs, so the pipeline's duplicate detection (processing.DuplicateLedger,
checked in pipeline.run) treats pre-existing catalog content as already
seen, not just assets this pipeline itself produced going forward.

Read-only against the source folders: this script only computes sha256
hashes of existing files, never moves/modifies/deletes anything in them.

Usage:
  python3 scripts/seed_duplicate_ledger.py --state-dir state \
      "/path/to/production/adobe_submission" \
      "/path/to/production/adobe_submission_batch_02" \
      "/path/to/production/magnific_submission_01"

Known gap (not solved by this script): GitHub Actions' daily.yml runner
does not currently persist state/seen_hashes.json between runs (no cache/
artifact-restore step wired up for it), so in the real cloud schedule,
re-seeding or persisting this ledger across runs is still unresolved --
see docs/GLOBAL_TREND_INTELLIGENCE.md "Known limitations". Running this
script locally only affects local/manual runs until that is fixed.
"""
from __future__ import annotations
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from stock_factory.processing import DuplicateLedger  # noqa: E402

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp'}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--state-dir', default='state')
    ap.add_argument('folders', nargs='+')
    args = ap.parse_args()

    ledger = DuplicateLedger(Path(args.state_dir))
    before = len(ledger.seen)
    scanned = 0
    for folder in args.folders:
        root = Path(folder)
        if not root.exists():
            print(f'[seed] WARNING: folder does not exist, skipping: {root}', file=sys.stderr)
            continue
        for path in root.rglob('*'):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            ledger.record(digest)
            scanned += 1
    ledger.save()
    after = len(ledger.seen)
    print(f'[seed] scanned {scanned} image files across {len(args.folders)} folder(s)')
    print(f'[seed] ledger grew from {before} to {after} unique sha256 hashes')


if __name__ == '__main__':
    main()
