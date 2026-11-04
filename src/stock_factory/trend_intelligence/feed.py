"""Builds and persists the versioned production-intelligence feed that
`trends.py` (stage 1) reads to influence concept selection."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

from .. import config
from . import calendar_sources, early_warning, scoring, briefs, deadlines, alert_history
from .adapters.base import SIGNAL_SEARCH_DEMAND, SIGNAL_CATALOG_SUPPLY
from .adapters.adobe_stock_adapter import AdobeStockSearchAdapter
from .adapters.google_trends_adapter import GoogleTrendsBigQueryAdapter
from .adapters.magnific_adapter import MagnificManualImportAdapter

FEED_SCHEMA_VERSION = 3  # v2: separated catalog_supply from demand; v3: shared deadline model in briefs (no production_window_*)


# Shared validation policy (used by BOTH verify_feed.py and trends.py).
SUPPORTED_SCHEMA_VERSIONS = (FEED_SCHEMA_VERSION,)
FEED_MAX_AGE_DAYS = 2
# A feed's scan_date may be at most this many days AFTER the validating
# machine's date (UTC vs local-midnight skew); anything further in the
# future is a bad clock or a forged feed, never "fresh".
FEED_MAX_FUTURE_SKEW_DAYS = 1


def _local_git_sha() -> str:
    """Commit of the code producing a locally-run scan, so a local feed is
    as traceable as a CI one. '' if git is unavailable (the feed then
    fails validation as FEED_SOURCE_UNIDENTIFIED, by design)."""
    try:
        out = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                             timeout=5, cwd=Path(__file__).resolve().parent)
        sha = out.stdout.strip()
        return sha if out.returncode == 0 and len(sha) == 40 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


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


def horizon_bounds(today: date) -> tuple[date, date]:
    """Inclusive [start, end] of the rolling scan horizon."""
    return today, today + timedelta(days=early_warning.HORIZON_DAYS)


def collect_horizon_events(today: date, countries: list[str] | None = None) -> list:
    """Every calendar event dated within [today, today + HORIZON_DAYS].

    Generates events for EVERY calendar year the horizon touches (normally
    two: the scan year and the next one), then filters strictly to the
    horizon, so e.g. an Aug 1 scan sees next year's Jan-Jul events and
    never sees this year's already-past Jan-Jul events."""
    start, end = horizon_bounds(today)
    events = []
    for year in range(start.year, end.year + 1):
        events += calendar_sources.all_events(year, countries=countries)
    return [e for e in events if start <= e.event_date <= end]


def run_scan(today: date | None = None, year: int | None = None, persist_history: bool = True) -> dict:
    """`year` is accepted for backward compatibility only and ignored:
    the horizon is always derived from `today` (see collect_horizon_events).

    Loads the persistent alert history (alert_history.py), evaluates
    alerts / missed opportunities against it, and -- unless
    persist_history=False -- saves the updated history at the end."""
    today = today or datetime.now(timezone.utc).date()
    horizon_start, horizon_end = horizon_bounds(today)
    events = collect_horizon_events(today)

    duplicate_groups = calendar_sources.find_duplicate_groups(events)

    candidate_terms = list({e.english_name for e in events})
    demand_terms, catalog_supply_by_term = _collect_signals(candidate_terms)

    scores = scoring.score_events(
        events, today,
        verified_demand_terms=demand_terms,
        catalog_supply_by_term=catalog_supply_by_term,
    )
    windows = early_warning.windowed_events(events, today)
    history = alert_history.load_history()
    history_load_status = history.get('_load_status')
    scan_gap_days = alert_history.mark_scan(history, today)
    alerts, missed = early_warning.evaluate(events, today, history)
    alert_history.prune(history, today)
    # Same date model as briefs (deadlines.py): opportunities whose
    # submission deadline has passed are bucketed separately and never
    # compete for top_opportunities / brief slots.
    on_time_scores = [s for s in scores if s.schedule_status != deadlines.LATE]
    late_scores = [s for s in scores if s.schedule_status == deadlines.LATE]
    briefs_list = briefs.qualifying_briefs(on_time_scores)

    feed = {
        'schema_version': FEED_SCHEMA_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'scan_date': today.isoformat(),
        'horizon': {
            'start': horizon_start.isoformat(),
            'end': horizon_end.isoformat(),
            'days': early_warning.HORIZON_DAYS,
            'calendar_years_generated': list(range(horizon_start.year, horizon_end.year + 1)),
        },
        # Source identification: which code/run produced this feed, so a
        # consuming workflow can tell a stale local file from a fresh
        # cloud-generated one even if the clock looks right.
        'provenance': {
            'generator': 'stock_factory.trend_intelligence.scan',
            'git_sha': os.getenv('GITHUB_SHA', '') or _local_git_sha(),
            'workflow_run_id': os.getenv('GITHUB_RUN_ID', ''),
            'workflow': os.getenv('GITHUB_WORKFLOW', '') or 'local',
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
        'alert_state': {
            'history_file': 'state/intelligence/alert_history.json',
            'history_load_status': history_load_status,
            'last_successful_scan_date': today.isoformat(),
            'previous_scan_date': history.get('previous_scan_date'),
            'scan_gap_days': scan_gap_days,
            'events_tracked': len(history['events']),
            'production_status_source': 'none wired -- every event reports production_status="unknown" '
                                        'unless alert_history.set_production_status() recorded one',
        },
        'missed_opportunities': missed,
        'deadline_model': deadlines.config_dict(),
        'top_opportunities': [s.to_dict() for s in on_time_scores[:50]],
        'late_opportunities': [s.to_dict() for s in late_scores[:50]],
        'late_opportunities_total': len(late_scores),
        'creative_briefs': [b.to_dict() for b in briefs_list],
    }
    if persist_history:
        alert_history.save_history(history)
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


def is_feed_stale(feed: dict | None, today: date | None = None, max_age_days: int = FEED_MAX_AGE_DAYS) -> bool:
    """True if the feed is missing, undated, older than max_age_days, or
    dated further in the future than FEED_MAX_FUTURE_SKEW_DAYS (a future
    scan_date is never "fresh"). Prefer validate_feed(), which applies this
    plus every structural/integrity/provenance check."""
    if not isinstance(feed, dict):
        return True
    today = today or datetime.now(timezone.utc).date()
    try:
        scan_date = date.fromisoformat(feed['scan_date'])
    except (KeyError, ValueError, TypeError):
        return True
    age = (today - scan_date).days
    return age > max_age_days or -age > FEED_MAX_FUTURE_SKEW_DAYS


# --- Shared feed validation ---------------------------------------------

_REQUIRED_TOP_LEVEL: dict[str, type | tuple] = {
    'schema_version': int,
    'generated_at': str,
    'scan_date': str,
    'horizon': dict,
    'provenance': dict,
    'countries_covered': list,
    'events_indexed': int,
    'top_opportunities': list,
    'alerts': list,
    'creative_briefs': list,
}
_REQUIRED_PROVENANCE = ('generator', 'git_sha')
_REQUIRED_BRIEF: dict[str, type | tuple] = {
    'event_country': str,
    'event_name': str,
    'event_date': str,
    'format': str,
    'production_start': str,
    'production_deadline': str,
    'submission_deadline': str,
    'schedule_status': str,
    'creative_concept': str,
    'opportunity_score': (int, float),
}
_BRIEF_DATE_FIELDS = ('event_date', 'production_start', 'production_deadline', 'submission_deadline')


@dataclass
class FeedValidation:
    ok: bool
    problems: list[str] = field(default_factory=list)
    feed: dict | None = None  # only set when ok -- callers must not use a rejected feed


def _type_ok(value, expected) -> bool:
    if isinstance(value, bool):  # bool is an int subclass; never a valid count/version/score
        return False
    return isinstance(value, expected)


def _iso_date_ok(value) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_feed(today: date | None = None, max_age_days: int = FEED_MAX_AGE_DAYS,
                  max_future_days: int = FEED_MAX_FUTURE_SKEW_DAYS) -> FeedValidation:
    """THE feed validator -- verify_feed.py (CLI) and trends.py (consumer)
    both call this, so a feed the CLI rejects can never be consumed.

    Never raises: every failure mode becomes a named problem string.
    Checks, in order: file present; parses as JSON; top level is an object;
    supported schema_version; required fields present with correct types;
    brief structure; well-formed dates; sha256 checksum; age within
    max_age_days; scan_date not more than max_future_days in the future;
    non-empty provenance (generator, git_sha)."""
    today = today or datetime.now(timezone.utc).date()
    path = _feed_path()
    try:
        if not path.exists():
            return FeedValidation(False, ['FEED_MISSING: no state/intelligence/feed.json present'])
        raw = path.read_text()
    except OSError as exc:
        return FeedValidation(False, [f'FEED_UNREADABLE: {exc}'])
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return FeedValidation(False, [f'FEED_MALFORMED_JSON: {exc}'])
    if not isinstance(data, dict):
        return FeedValidation(False, [f'FEED_NOT_OBJECT: top-level JSON is {type(data).__name__}, expected object'])

    problems: list[str] = []
    version = data.get('schema_version')
    if not _type_ok(version, int) or version not in SUPPORTED_SCHEMA_VERSIONS:
        problems.append(f'FEED_SCHEMA_UNSUPPORTED: schema_version={version!r}, '
                        f'supported={list(SUPPORTED_SCHEMA_VERSIONS)}')
    for key, expected in _REQUIRED_TOP_LEVEL.items():
        if key not in data:
            problems.append(f'FEED_FIELD_MISSING: {key}')
        elif key != 'schema_version' and not _type_ok(data[key], expected):
            problems.append(f'FEED_FIELD_TYPE: {key} is {type(data[key]).__name__}')

    if isinstance(data.get('creative_briefs'), list):
        for i, b in enumerate(data['creative_briefs']):
            if not isinstance(b, dict):
                problems.append(f'FEED_BRIEF_INVALID: creative_briefs[{i}] is {type(b).__name__}')
                continue
            for key, expected in _REQUIRED_BRIEF.items():
                if key not in b:
                    problems.append(f'FEED_BRIEF_INVALID: creative_briefs[{i}] missing {key}')
                elif not _type_ok(b[key], expected):
                    problems.append(f'FEED_BRIEF_INVALID: creative_briefs[{i}].{key} is {type(b[key]).__name__}')
            for key in _BRIEF_DATE_FIELDS:
                if isinstance(b.get(key), str) and not _iso_date_ok(b[key]):
                    problems.append(f'FEED_BAD_DATE: creative_briefs[{i}].{key}={b[key]!r}')

    scan_date = None
    if isinstance(data.get('scan_date'), str):
        if _iso_date_ok(data['scan_date']):
            scan_date = date.fromisoformat(data['scan_date'])
        else:
            problems.append(f'FEED_BAD_DATE: scan_date={data["scan_date"]!r}')
    if isinstance(data.get('generated_at'), str):
        try:
            datetime.fromisoformat(data['generated_at'])
        except ValueError:
            problems.append(f'FEED_BAD_DATE: generated_at={data["generated_at"]!r}')
    if scan_date is not None:
        age = (today - scan_date).days
        if age > max_age_days:
            problems.append(f'FEED_STALE: scan_date={scan_date} is {age} day(s) old (max {max_age_days})')
        if -age > max_future_days:
            problems.append(f'FEED_FUTURE_DATED: scan_date={scan_date} is {-age} day(s) in the future '
                            f'(max skew {max_future_days})')

    provenance = data.get('provenance')
    if isinstance(provenance, dict):
        for key in _REQUIRED_PROVENANCE:
            value = provenance.get(key)
            if not isinstance(value, str) or not value.strip():
                problems.append(f'FEED_SOURCE_UNIDENTIFIED: provenance.{key} missing/empty -- '
                                'feed was not produced by a traceable run')

    integrity_ok, integrity_msg = verify_integrity()
    if not integrity_ok:
        problems.append(f'FEED_INTEGRITY_FAILED: {integrity_msg}')

    if problems:
        return FeedValidation(False, problems)
    return FeedValidation(True, [], data)
