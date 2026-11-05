"""Daily orchestration skeleton (Phase 1/6). Real, runnable logic for
queue build/resume, state persistence, and the QC/archive stages that
don't need a browser; generation and upload call through to the
provider interfaces in providers/ and magnific_upload.py, which are
honestly NOT YET IMPLEMENTED (Phase 2/4/5) -- see their docstrings for
why, and run this on the operator's own machine once they are.

This module is intentionally runnable TODAY end-to-end: every item will
currently land in 'blocked_provider_not_implemented' (generation) with a
record in failures.jsonl, proving the resume/state/reporting machinery
works, without pretending any image was actually generated.
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone

from .. import config, qc, drive_archive
from ..processing import convert_jpeg, sha256_hex, DuplicateLedger
from .models import ProductionItem
from .queue_builder import build_daily_queue
from .providers.base import ProviderUnavailable
from .providers.google_flow_browser import GoogleFlowBrowserProvider
from .providers.midjourney_browser import MidjourneyBrowserProvider
from . import state_store
from . import magnific_upload

TERMINAL_SUCCESS = {'uploaded'}
TERMINAL_BLOCKED = {'generation_failed', 'qc_technical_fail', 'qc_visual_fail', 'archive_failed',
                     'upload_failed', 'blocked_provider_not_implemented'}

_PROVIDERS = {
    'google_flow': GoogleFlowBrowserProvider(),
    'midjourney': MidjourneyBrowserProvider(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider_for(item: ProductionItem):
    return _PROVIDERS.get(item.provider_preference)


def _generate(item: ProductionItem) -> bool:
    if item.generated_at is not None:
        return True  # resume: already generated in a prior run
    item.status = 'generating'
    provider = _provider_for(item)
    tried = []
    for candidate_name in [item.provider_preference, config.PROVIDER_FALLBACK]:
        if candidate_name in tried:
            continue
        tried.append(candidate_name)
        provider = _PROVIDERS.get(candidate_name)
        if provider is None:
            continue  # e.g. 'manual_inbox' fallback has no browser-automation adapter here
        try:
            asset = provider.generate(item.prompt, item.content_type)
            item.generated_by = provider.name
            item.generated_at = _now()
            item.status = 'generated'
            item._raw_bytes = asset.data  # not persisted; consumed immediately below
            return True
        except ProviderUnavailable as exc:
            item.last_error = str(exc)
            continue
    item.status = 'blocked_provider_not_implemented'
    item.retry_count += 1
    state_store.record_failure(item, 'generation', item.last_error or 'no provider available')
    return False


def _qc_and_archive(item: ProductionItem, ledger: DuplicateLedger) -> None:
    if item.qc_technical_pass is not None:
        return  # resume: QC already ran in a prior run
    raw = getattr(item, '_raw_bytes', None)
    if raw is None:
        return  # this run didn't (re-)generate; nothing new to QC yet
    digest_raw = sha256_hex(raw)
    item.sha256_raw = digest_raw
    if ledger.is_duplicate(digest_raw):
        item.status = 'qc_technical_fail'
        item.qc_technical_pass = False
        item.qc_technical_reason = 'duplicate_raw'
        state_store.record_failure(item, 'qc', 'duplicate_raw')
        return

    jpeg = convert_jpeg(raw)
    digest = sha256_hex(jpeg)
    ready, reason, details = qc.check_magnific_acceptance(jpeg, digest=digest, ledger=ledger)
    item.qc_technical_pass = ready
    item.qc_technical_reason = reason
    item.dimensions = details.get('dimensions')
    item.file_size_bytes = details.get('file_size')
    if not ready:
        item.status = 'qc_technical_fail'
        state_store.record_failure(item, 'qc', reason)
        return

    out_dir = config.LOCAL_PIPELINE_OUTPUT_DIR / 'processed' / item.date
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{item.item_id}.jpg'
    out_path.write_bytes(jpeg)
    item.local_processed_path = str(out_path)
    item.sha256_processed = digest
    ledger.record(digest_raw)
    ledger.record(digest)
    item.status = 'qc_technical_pass'
    item.qc_visual_status = 'pending_manual'

    archive_result = drive_archive.archive(out_path, 'magnific')
    if archive_result.get('archived'):
        item.drive_file_id = archive_result.get('file_id')
        item.drive_archived_at = _now()
        item.status = 'archived'
    else:
        item.status = 'archive_failed'
        state_store.record_failure(item, 'archive', archive_result.get('reason', 'unknown'))


def _upload(item: ProductionItem) -> None:
    if item.status != 'archived' or item.qc_visual_status != 'pass':
        return  # never upload without an explicit human visual-QC pass
    if item.magnific_asset_id:
        return  # already uploaded -- never silently re-upload
    try:
        result = magnific_upload.upload(item.local_processed_path, item.title_seed, item.keyword_seed)
        if result.uploaded:
            item.magnific_asset_id = result.magnific_asset_id
            item.magnific_uploaded_at = _now()
            item.status = 'uploaded'
            state_store.record_upload(item)
        else:
            item.status = 'upload_failed'
            item.retry_count += 1
            state_store.record_failure(item, 'upload', result.reason)
    except magnific_upload.UploadUnavailable as exc:
        item.status = 'upload_failed'
        item.last_error = str(exc)
        state_store.record_failure(item, 'upload', str(exc))


def run_daily(day: str) -> dict:
    existing = state_store.load_today_items(day)
    if existing:
        items = list(existing.values())
        print(f'[local_pipeline] resuming {day}: {len(items)} items already tracked', file=sys.stderr)
    else:
        items = build_daily_queue(day)
        state_store.save_queue_history(day, items)
        print(f'[local_pipeline] built fresh queue for {day}: {len(items)} items '
              f'({config.DAILY_PHOTO_TARGET} photo + {config.DAILY_ILLUSTRATION_TARGET} illustration)',
              file=sys.stderr)

    ledger = DuplicateLedger(config.LOCAL_PIPELINE_STATE_DIR)

    for item in items:
        if item.status in TERMINAL_SUCCESS:
            continue
        if item.status == 'blocked_provider_not_implemented' and item.retry_count >= config.LOCAL_PIPELINE_MAX_RETRIES:
            continue

        ok = _generate(item)
        state_store.record_item(item)
        if not ok:
            continue

        _qc_and_archive(item, ledger)
        state_store.record_item(item)

        _upload(item)
        state_store.record_item(item)

    ledger.save()
    summary = state_store.write_daily_summary(day, items)
    print(f'[local_pipeline] day {day} summary: {summary["by_status"]}', file=sys.stderr)
    return summary
