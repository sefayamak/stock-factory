"""Builds and persists the versioned production-intelligence feed that
`trends.py` (stage 1) reads to influence concept selection."""
from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime, date, timezone
from pathlib import Path

from .. import config
from . import calendar_sources, early_warning, scoring, briefs
from .adapters.adobe_stock_adapter import AdobeStockSearchAdapter
from .adapters.google_trends_adapter import GoogleTrendsBigQueryAdapter
from .adapters.magnific_adapter import MagnificManualImportAdapter

FEED_SCHEMA_VERSION = 1


def _feed_dir() -> Path:
    return config.STATE_DIR / 'intelligence'


def _feed_path() -> Path:
    return _feed_dir() / 'feed.json'


def _collect_verified_terms(candidate_terms: list[str]) -> set[str]:
    """Queries every adapter that reports itself available and returns the
    set of terms any adapter verified (case-folded), for scoring's
    'verified_search_demand' path. Adapter failures never crash the scan --
    an unavailable/erroring adapter just contributes nothing."""
    verified: set[str] = set()
    for adapter in (AdobeStockSearchAdapter(), GoogleTrendsBigQueryAdapter(), MagnificManualImportAdapter()):
        try:
            if not adapter.available():
                continue
            for sig in adapter.fetch(candidate_terms):
                if sig.verified and sig.value is not None:
                    verified.add(sig.term.strip().lower())
        except Exception:
            continue
    return verified


def adapter_status() -> dict[str, dict]:
    statuses = {}
    for adapter, platform in (
        (AdobeStockSearchAdapter(), 'adobe'),
        (GoogleTrendsBigQueryAdapter(), 'google_trends'),
        (MagnificManualImportAdapter(), 'magnific'),
    ):
        try:
            available = adapter.available()
        except Exception as exc:
            available = False
            statuses[platform] = {'adapter': adapter.name, 'available': False, 'error': str(exc)}
            continue
        statuses[platform] = {'adapter': adapter.name, 'available': available}
    return statuses


def run_scan(today: date | None = None, year: int | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    year = year or today.year
    events = calendar_sources.all_events(year, countries=None)
    # Also pull in next year's events near year-end so the 365-day horizon
    # doesn't fall off a cliff on Dec 31.
    if (date(year, 12, 31) - today).days < 90:
        events += calendar_sources.all_events(year + 1, countries=None)

    duplicate_groups = calendar_sources.find_duplicate_groups(events)

    candidate_terms = list({e.english_name for e in events})
    verified_terms = _collect_verified_terms(candidate_terms)

    scores = scoring.score_events(events, today, verified_trend_terms=verified_terms)
    windows = early_warning.windowed_events(events, today)
    alerts = early_warning.alerts_for(events, today)
    missed = early_warning.missed_opportunity_check(events, today)
    briefs_list = briefs.qualifying_briefs(scores)

    feed = {
        'schema_version': FEED_SCHEMA_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'scan_date': today.isoformat(),
        'countries_covered': sorted(calendar_sources.SUPPORTED_COUNTRIES.keys()),
        'events_indexed': len(events),
        'duplicate_event_groups': len(duplicate_groups),
        'adapter_status': adapter_status(),
        'verified_demand_terms': sorted(verified_terms),
        'window_counts': {str(k): len(v) for k, v in windows.items()},
        'alerts': [a.to_dict() for a in alerts],
        'missed_opportunities': missed,
        'top_opportunities': [s.to_dict() for s in scores[:50]],
        'creative_briefs': [b.to_dict() for b in briefs_list],
    }
    return feed


def write_feed(feed: dict) -> Path:
    _feed_dir().mkdir(parents=True, exist_ok=True)
    path = _feed_path()
    # Keep one prior version for auditability of what changed day-to-day.
    if path.exists():
        prior = _feed_dir() / f'feed.v{feed["schema_version"]}.prior.json'
        path.replace(prior)
    path.write_text(json.dumps(feed, indent=2, ensure_ascii=False))
    return path


def load_feed() -> dict | None:
    path = _feed_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def is_feed_stale(feed: dict | None, today: date | None = None, max_age_days: int = 2) -> bool:
    if feed is None:
        return True
    today = today or datetime.now(timezone.utc).date()
    try:
        scan_date = date.fromisoformat(feed['scan_date'])
    except (KeyError, ValueError):
        return True
    return (today - scan_date).days > max_age_days
