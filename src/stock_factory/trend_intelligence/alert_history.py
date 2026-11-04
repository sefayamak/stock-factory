"""Persistent early-warning alert history.

Stored next to feed.json as state/intelligence/alert_history.json (same
state-dir pattern as the feed). The scan workflow keeps it across runs via
its state cache AND publishes it to the `intelligence-feed` branch, from
which it is restored if the cache was evicted -- see
.github/workflows/trend_intelligence.yml.

Per event (keyed by Event.key(): country:date:name), it records:
  - first_seen               -- first scan date that indexed the event
  - alerted_thresholds       -- lead-time thresholds (days) already alerted
  - alerts                   -- [{date, thresholds, catch_up}] audit trail
  - missed_reported_on       -- date a missed-opportunity was first reported
  - production_status        -- 'unknown' unless something sets it; this repo
                                has NO automatic production tracking wired in,
                                so 'unknown' is the honest default and is
                                never reported as "not produced".
plus top-level last_successful_scan_date / previous_scan_date.
"""
from __future__ import annotations
import json
import os
from datetime import date
from pathlib import Path

from .. import config

HISTORY_SCHEMA_VERSION = 1
PRODUCTION_STATUSES = ('unknown', 'not_started', 'in_production', 'produced', 'submitted')
# Statuses that mean the opportunity is being (or was) acted on -- never "missed".
ACTIVE_PRODUCTION_STATUSES = ('in_production', 'produced', 'submitted')
# Keep records for events this many days after they pass, then prune.
PRUNE_AFTER_EVENT_DAYS = 30


def history_path() -> Path:
    return config.STATE_DIR / 'intelligence' / 'alert_history.json'


def _empty(load_status: str) -> dict:
    return {
        'schema_version': HISTORY_SCHEMA_VERSION,
        'last_successful_scan_date': None,
        'previous_scan_date': None,
        'events': {},
        '_load_status': load_status,
    }


def load_history() -> dict:
    """Never raises. A missing file starts an empty history ('new'); an
    unreadable/corrupt/wrong-shape file is reset ('corrupt_reset') and the
    bad file is kept alongside as alert_history.corrupt.json for audit."""
    path = history_path()
    if not path.exists():
        return _empty('new')
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not isinstance(data.get('events'), dict) \
                or data.get('schema_version') != HISTORY_SCHEMA_VERSION:
            raise ValueError('unexpected alert history shape/schema')
    except (OSError, ValueError) as exc:
        try:
            path.replace(path.with_name('alert_history.corrupt.json'))
        except OSError:
            pass
        h = _empty('corrupt_reset')
        h['_load_error'] = str(exc)
        return h
    data['_load_status'] = 'loaded'
    return data


def save_history(history: dict) -> Path:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in history.items() if not k.startswith('_')}
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
    os.replace(tmp, path)  # atomic: a crash mid-write never leaves a truncated history
    return path


def record_for(history: dict, event, today: date) -> dict:
    rec = history['events'].get(event.key())
    if rec is None:
        rec = {
            'event': {'country': event.country, 'event_date': event.event_date.isoformat(),
                      'english_name': event.english_name},
            'first_seen': today.isoformat(),
            'alerted_thresholds': [],
            'alerts': [],
            'missed_reported_on': None,
            'production_status': 'unknown',
        }
        history['events'][event.key()] = rec
    return rec


def set_production_status(history: dict, event_id: str, status: str) -> None:
    """Hook for a future production tracker (or a human) to record what
    actually happened. Nothing in this repo calls it automatically yet."""
    if status not in PRODUCTION_STATUSES:
        raise ValueError(f'unknown production status {status!r}; expected one of {PRODUCTION_STATUSES}')
    rec = history['events'].setdefault(event_id, {
        'event': {}, 'first_seen': None, 'alerted_thresholds': [], 'alerts': [],
        'missed_reported_on': None, 'production_status': 'unknown',
    })
    rec['production_status'] = status


def mark_scan(history: dict, today: date) -> int | None:
    """Records a successful scan; returns the gap in days since the
    previous successful scan (None on the first scan)."""
    prev = history.get('last_successful_scan_date')
    history['previous_scan_date'] = prev
    history['last_successful_scan_date'] = today.isoformat()
    if prev:
        try:
            return (today - date.fromisoformat(prev)).days
        except ValueError:
            return None
    return None


def prune(history: dict, today: date) -> None:
    keep = {}
    for k, rec in history['events'].items():
        try:
            d = date.fromisoformat(rec.get('event', {}).get('event_date', ''))
        except ValueError:
            keep[k] = rec  # manual/production-status-only records: keep
            continue
        if (today - d).days <= PRUNE_AFTER_EVENT_DAYS:
            keep[k] = rec
    history['events'] = keep
