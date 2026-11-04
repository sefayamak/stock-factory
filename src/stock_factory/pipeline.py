"""Orchestrates stages 1-8 for a single daily run."""
from __future__ import annotations
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config, qc, reporting
from .adapters.base import Adapter
from .adapters.manual_inbox_adapter import ManualInboxAdapter
from .prompts import build_queue
from .processing import convert_jpeg, sha256_hex, DuplicateLedger
from .tracking import RunTracker
from . import drive_archive


def _select_queue(tracker: RunTracker) -> str:
    if not config.ADOBE_MARKETPLACE_ACTIVE:
        return 'magnific'
    return 'adobe' if (tracker.counts['qc_passed'] % 2 == 1) else 'magnific'


def build_adapters(queue_prompts: list[str]) -> list[Adapter]:
    adapters: list[Adapter] = []
    for name in config.ENABLED_ADAPTERS:
        if name == 'manual_inbox':
            adapters.append(ManualInboxAdapter(config.INBOX_DIR))
        elif name == 'gemini':
            if not config.ALLOW_PAID_GENERATION or not config.GEMINI_API_KEY:
                print(f'[pipeline] skipping gemini adapter: ALLOW_PAID_GENERATION/GEMINI_API_KEY not set', file=sys.stderr)
                continue
            from .adapters.gemini_adapter import GeminiAdapter
            adapters.append(GeminiAdapter(queue_prompts))
        elif name == 'flow':
            from .adapters.flow_adapter import FlowAdapter
            adapters.append(FlowAdapter())  # will raise BLOCKED if actually fetched from
        else:
            print(f'[pipeline] unknown adapter "{name}", skipping', file=sys.stderr)
    return adapters


def run(day: str, target: int, dry_run: bool) -> dict:
    target = min(target, config.DAILY_TARGET_CEILING)
    queue = build_queue(day, target)
    tracker = RunTracker()
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger = DuplicateLedger(config.STATE_DIR)
    rows = []

    if dry_run:
        for item in queue:
            rows.append({
                'job_id': item.job_id, 'category': item.category, 'title': item.scene.split(',')[0][:145],
                'prompt': item.prompt, 'status': 'NOT_FETCHED_DRY_RUN',
                'trend_source': item.source, 'trend_term': item.trend_term,
                'trend_status': item.trend_status, 'trend_snapshot_imported_at': item.trend_snapshot_imported_at,
                'opportunity_score': item.opportunity_score, 'event_country': item.event_country,
            })
        tracker.record('fetched', 0)
    else:
        adapters = build_adapters([q.prompt for q in queue])
        remaining = target
        for adapter in adapters:
            if remaining <= 0:
                break
            try:
                assets = adapter.fetch(remaining)
            except NotImplementedError as exc:
                print(f'[pipeline] adapter "{adapter.name}" is blocked: {exc}', file=sys.stderr)
                continue
            tracker.record('fetched', len(assets))
            remaining -= len(assets)
            for i, asset in enumerate(assets):
                digest_raw = sha256_hex(asset.data)
                if ledger.is_duplicate(digest_raw):
                    tracker.record_rejection(asset.origin_name, 'duplicate_raw', 'duplicate')
                    continue
                ok, reason, (w, h) = qc.validate_image(asset.data)
                if not ok:
                    tracker.record_rejection(asset.origin_name, reason, 'qc')
                    rows.append({'job_id': asset.origin_name, 'status': 'REJECTED_QC', 'reason': reason, 'source': asset.source})
                    continue
                jpeg = convert_jpeg(asset.data)
                if len(jpeg) < config.MIN_BYTES:
                    tracker.record_rejection(asset.origin_name, 'filesize_below_min', 'qc')
                    rows.append({'job_id': asset.origin_name, 'status': 'REJECTED_QC', 'reason': 'filesize_below_min', 'source': asset.source})
                    continue
                digest = sha256_hex(jpeg)
                if ledger.is_duplicate(digest):
                    tracker.record_rejection(asset.origin_name, 'duplicate_jpeg', 'duplicate')
                    continue
                ledger.record(digest_raw)
                ledger.record(digest)
                name = f'{asset.source}-{digest[:12]}.jpg'
                out_path = config.OUT_DIR / name
                out_path.write_bytes(jpeg)
                tracker.record('qc_passed')

                queue_name = _select_queue(tracker)
                archive_result = drive_archive.archive(out_path, queue_name)
                if archive_result.get('archived'):
                    tracker.record('archived')
                else:
                    tracker.record('archive_skipped')

                rows.append({
                    'job_id': name, 'status': 'PENDING_HUMAN_VISUAL_QC', 'dimensions': f'{w}x{h}',
                    'source': asset.source, 'drive_queue': queue_name, 'drive_status': archive_result.get('reason', 'archived'),
                    '_ai_generated': 'yes',
                })
        ledger.save()

    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = config.OUT_DIR / 'submission.csv'
    fieldnames = [
        'job_id', 'category', 'title', 'prompt', 'status', 'reason', 'dimensions', 'source',
        'drive_queue', 'drive_status', '_ai_generated',
        'trend_source', 'trend_term', 'trend_status', 'trend_snapshot_imported_at',
        'opportunity_score', 'event_country',
    ]
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    summary = tracker.finalize(config.STATE_DIR, day)
    report_path = reporting.write_report(summary, config.STATE_DIR)
    print(report_path.read_text())
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--day', default=datetime.now(timezone.utc).date().isoformat())
    ap.add_argument('--target', type=int, default=config.DAILY_TARGET_MIN)
    ap.add_argument('--execute', action='store_true', help='Actually fetch/process; default is a safe dry run that only builds the queue')
    args = ap.parse_args()
    summary = run(args.day, args.target, dry_run=not args.execute)
    if args.execute and reporting.shortfall(summary):
        sys.exit(1)


if __name__ == '__main__':
    main()
