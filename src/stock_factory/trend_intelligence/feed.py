"""Builds and persists the versioned production-intelligence feed that
`trends.py` (stage 1) reads to influence concept selection."""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, date, timezone
from pathlib import Path

from .. import config
from . import calendar_sources, early_warning, scoring, briefs
from .adapters.base import SIGNAL_SEARCH_DEMAND, SIGNAL_CATALOG_SUPPLY
from .adapters.adobe_stock_adapter import AdobeStockSearchAdapter
from .adapters.google_trends_adapter import GoogleTrendsBigQueryAdapter
from .adapters.magnific_adapter import MagnificManualImportAdapter

FEED_SCHEMA_VERSION = 2  # bumped: v1 incorrectly conflated catalog_supply into demand terms


def _feed_dir() -> Path:
    return config.STATE_DIR / 'intelligence'


def _feed_path() -> Path:
    return _feed_dir() / 'feed.json'


def _checksum_path() -> Path:
    return _feed_dir() / 'feed.sha256'


def _collect_signals(candidate_terms: list[str]) -> tuple[set[str], dict[str, float]]:
    """Queries every adapter that reports itself available and splits its
    signals STRICTLY by `signal_type`:
      - demand_terms: term is in a SIGNAL_SEARCH_DEMAND signal only.
      - catalog_supply_by_term: term -> value, SIGNAL_CATALOG_SUPPLY only.
    A term is never counted as demand just because some adapter call
    succeeded ("verified=True") -- verified only means "this is a real
    live/official value", not "this is demand". Adapter failures never
    crash the scan -- an unavailable/erroring adapter just contributes
    nothing to either set."""
    demand_terms: set[str] = set()
    catalog_supply_by_term: dict[str, float] = {}
    for adapter in (AdobeStockSearchAdapter(), GoogleTrendsBigQueryAdapter(), MagnificManualImportAdapter()):
        try:
            if not adapter.available():
                continue
            for sig in adapter.fetch(candidate_terms):
                if not sig.verified or sig.value is None:
                    continue
                key = sig.term.strip().lower()
                if sig.signal_type == SIGNAL_SEARCH_DEMAND:
                    demand_terms.add(key)
                elif sig.signal_type == SIGNAL_CATALOG_SUPPLY:
                    catalog_supply_by_term[key] = sig.value
                # Any other signal_type (e.g. historical_download_performance)
                # is intentionally not routed here -- it has its own factor.
        except Exception:
            continue
    return demand_terms, catalog_supply_by_term


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
    demand_terms, catalog_supply_by_term = _collect_signals(candidate_terms)

    scores = scoring.score_events(
        events, today,
        verified_demand_terms=demand_terms,
        catalog_supply_by_term=catalog_supply_by_term,
    )
    windows = early_warning.windowed_events(events, today)
    alerts = early_warning.alerts_for(events, today)
    missed = early_warning.missed_opportunity_check(events, today)
    briefs_list = briefs.qualifying_briefs(scores)

    feed = {
        'schema_version': FEED_SCHEMA_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'scan_date': today.isoformat(),
        # Source identification: which code/run produced this feed, so a
        # consuming workflow can tell a stale local file from a fresh
        # cloud-generated one even if the clock looks right.
        'provenance': {
            'generator': 'stock_factory.trend_intelligence.scan',
            'git_sha': os.getenv('GITHUB_SHA', ''),
            'workflow_run_id': os.getenv('GITHUB_RUN_ID', ''),
            'workflow': os.getenv('GITHUB_WORKFLOW', ''),
        },
        'countries_covered': sorted(calendar_sources.SUPPORTED_COUNTRIES.keys()),
        'events_indexed': len(events),
        'duplicate_event_groups': len(duplicate_groups),
        'adapter_status': adapter_status(),
        # Four distinct evidence categories -- see scoring.py module docstring.
        # Never merge verified_demand_terms and catalog_supply_terms.
        'verified_demand_terms': sorted(demand_terms),
        'catalog_supply_terms': {k: v for k, v in sorted(catalog_supply_by_term.items())},
        'historical_download_performance_basis': 'portfolio_wide_magnific_baseline_acceptance_rate',
        'window_counts': {str(k): len(v) for k, v in windows.items()},
        'alerts': [a.to_dict() for a in alerts],
        'missed_opportunities': missed,
        'top_opportunities': [s.to_dict() for s in scores[:50]],
        'creative_briefs': [b.to_dict() for b in briefs_list],
    }
    return feed


def _sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def write_feed(feed: dict) -> Path:
    _feed_dir().mkdir(parents=True, exist_ok=True)
    path = _feed_path()
    # Keep one prior version for auditability of what changed day-to-day.
    if path.exists():
        prior = _feed_dir() / f'feed.v{feed["schema_version"]}.prior.json'
        path.replace(prior)
    serialized = json.dumps(feed, indent=2, ensure_ascii=False)
    path.write_text(serialized)
    # Integrity: a companion checksum file, verified by the consumer before
    # trusting the feed (see verify_integrity below and the daily workflow's
    # fetch step). Computed over the exact bytes written, not re-derived
    # from the dict (which could mask a mid-write truncation).
    _checksum_path().write_text(_sha256_of(path.read_text()) + '\n')
    return path


def load_feed() -> dict | None:
    path = _feed_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def verify_integrity() -> tuple[bool, str]:
    """Returns (ok, message). Checks that feed.json's bytes match the
    sha256 recorded in feed.sha256 at write time -- catches a truncated or
    corrupted handoff (e.g. a partial artifact download) that `load_feed`
    alone would not notice as long as the JSON still happens to parse."""
    path, checksum_path = _feed_path(), _checksum_path()
    if not path.exists():
        return False, 'feed.json missing'
    if not checksum_path.exists():
        return False, 'feed.sha256 missing -- cannot verify integrity'
    expected = checksum_path.read_text().strip()
    actual = _sha256_of(path.read_text())
    if expected != actual:
        return False, f'checksum mismatch: expected {expected}, got {actual}'
    return True, 'ok'


def is_feed_stale(feed: dict | None, today: date | None = None, max_age_days: int = 2) -> bool:
    if feed is None:
        return True
    today = today or datetime.now(timezone.utc).date()
    try:
        scan_date = date.fromisoformat(feed['scan_date'])
    except (KeyError, ValueError):
        return True
    return (today - scan_date).days > max_age_days
