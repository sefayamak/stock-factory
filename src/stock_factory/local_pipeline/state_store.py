"""Machine-readable state for the local pipeline. Every write is append
-or-replace to a plain JSON/JSONL file under config.LOCAL_PIPELINE_STATE_DIR
so a human or another process can always answer, for any item: was it
generated, by which provider, did it pass QC, was it archived, was it
uploaded, what's its final status -- without re-deriving anything.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from .models import ProductionItem


def _state_dir() -> Path:
    d = config.LOCAL_PIPELINE_STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / 'daily_summary').mkdir(parents=True, exist_ok=True)
    return d


def _append_jsonl(path: Path, record: dict) -> None:
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record) + '\n')


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def save_queue_history(day: str, items: list[ProductionItem]) -> None:
    _append_jsonl(_state_dir() / 'queue_history.jsonl', {
        'day': day,
        'written_at': datetime.now(timezone.utc).isoformat(),
        'item_count': len(items),
        'item_ids': [i.item_id for i in items],
    })


def load_today_items(day: str) -> dict[str, ProductionItem]:
    """Resume support: reconstructs the latest known state of every item
    for `day` from production_log.jsonl (last record per item_id wins)."""
    items: dict[str, ProductionItem] = {}
    for record in _read_jsonl(_state_dir() / 'production_log.jsonl'):
        if record.get('date') == day:
            items[record['item_id']] = ProductionItem.from_dict(record)
    return items


def record_item(item: ProductionItem) -> None:
    """Append-only log of an item's state at a point in time. The log is
    the source of truth; load_today_items() folds it down to current
    state by taking each item's last record."""
    _append_jsonl(_state_dir() / 'production_log.jsonl', item.to_dict())


def record_upload(item: ProductionItem) -> None:
    _append_jsonl(_state_dir() / 'upload_log.jsonl', {
        'item_id': item.item_id,
        'date': item.date,
        'magnific_asset_id': item.magnific_asset_id,
        'uploaded_at': item.magnific_uploaded_at,
        'retry_count': item.retry_count,
    })


def record_failure(item: ProductionItem, stage: str, reason: str) -> None:
    _append_jsonl(_state_dir() / 'failures.jsonl', {
        'item_id': item.item_id,
        'date': item.date,
        'stage': stage,
        'reason': reason,
        'retry_count': item.retry_count,
        'recorded_at': datetime.now(timezone.utc).isoformat(),
    })


def write_daily_summary(day: str, items: list[ProductionItem]) -> dict:
    summary = {
        'day': day,
        'written_at': datetime.now(timezone.utc).isoformat(),
        'target': {
            'total': config.DAILY_TOTAL_TARGET,
            'photo': config.DAILY_PHOTO_TARGET,
            'illustration': config.DAILY_ILLUSTRATION_TARGET,
        },
        'queued': len(items),
        'by_status': {},
        'by_provider': {},
        'archived': sum(1 for i in items if i.drive_file_id),
        'uploaded': sum(1 for i in items if i.magnific_asset_id),
        'failed': sum(1 for i in items if i.status.endswith('_failed') or i.status.startswith('blocked_')),
    }
    for i in items:
        summary['by_status'][i.status] = summary['by_status'].get(i.status, 0) + 1
        key = i.generated_by or i.provider_preference
        summary['by_provider'][key] = summary['by_provider'].get(key, 0) + 1

    (_state_dir() / 'daily_summary' / f'{day}.json').write_text(json.dumps(summary, indent=2))
    return summary
