"""Finding 6 regression tests: trend freshness and adapter health.

- Magnific: a snapshot older than the EXISTING staleness policy
  (config.TREND_STALE_AFTER_DAYS, same one trends.py uses) is not fresh
  and contributes no current signal.
- Google Trends: observation week is kept separate from fetched_at; an old
  observation is not scored as current just because it was fetched now;
  region/unit/observation date survive; labeled search interest, never
  download/purchase demand.
- Every adapter status separates configured / dependency / auth / fetch /
  freshness / signal count / error, and a caught exception shows up as
  available=False with the error recorded."""
from __future__ import annotations
import datetime as _dt
import json
import sys
import types

import pytest

from stock_factory import config
from stock_factory.trend_intelligence import feed as feed_mod
from stock_factory.trend_intelligence.adapters import base
from stock_factory.trend_intelligence.adapters.google_trends_adapter import GoogleTrendsBigQueryAdapter
from stock_factory.trend_intelligence.adapters.magnific_adapter import MagnificManualImportAdapter

TODAY = _dt.date(2026, 8, 1)
STATUS_KEYS = {'adapter', 'configured', 'dependency_ready', 'auth_ready', 'fetch_attempted',
               'fetch_succeeded', 'fresh', 'signal_count', 'error', 'available'}


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    monkeypatch.delenv('ADOBE_STOCK_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    return tmp_path / 'state'


def _write_snapshot(state_dir, imported_at, terms):
    d = state_dir / 'trend_history'
    d.mkdir(parents=True, exist_ok=True)
    with (d / 'index.jsonl').open('a') as f:
        f.write(json.dumps({'imported_at': imported_at, 'source_file': 'm.json', 'sha256': imported_at,
                            'terms': terms}) + '\n')


def _install_fake_bigquery(monkeypatch, rows=None, raise_exc=None):
    calls = {}

    class Row:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class Job:
        def result(self):
            if raise_exc:
                raise raise_exc
            return [Row(**r) for r in (rows or [])]

    class Client:
        def __init__(self, project=None):
            calls['project'] = project

        def query(self, sql, job_config=None):
            calls['sql'] = sql
            calls['job_config'] = job_config
            return Job()

    class QueryJobConfig:
        def __init__(self, query_parameters=None, maximum_bytes_billed=None):
            self.query_parameters = query_parameters
            self.maximum_bytes_billed = maximum_bytes_billed

    class ArrayQueryParameter:
        def __init__(self, name, typ, values):
            self.name, self.typ, self.values = name, typ, values

    bq = types.ModuleType('google.cloud.bigquery')
    bq.Client, bq.QueryJobConfig, bq.ArrayQueryParameter = Client, QueryJobConfig, ArrayQueryParameter
    bq.ScalarQueryParameter = ArrayQueryParameter
    cloud = types.ModuleType('google.cloud')
    cloud.bigquery = bq
    google = sys.modules.get('google') or types.ModuleType('google')
    monkeypatch.setitem(sys.modules, 'google', google)
    monkeypatch.setitem(sys.modules, 'google.cloud', cloud)
    monkeypatch.setitem(sys.modules, 'google.cloud.bigquery', bq)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    return calls


# --- Magnific -----------------------------------------------------------

def test_stale_magnific_snapshot_is_not_used_as_current_signal(state, monkeypatch):
    monkeypatch.setattr(config, 'TREND_STALE_AFTER_DAYS', 14)
    old = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)).isoformat()
    _write_snapshot(state, old, [{'term': 'Black Friday', 'rank': 1}])
    feed = feed_mod.run_scan(today=TODAY)
    assert 'black friday' not in feed['verified_search_interest_terms']
    st = feed['adapter_status']['magnific']
    assert st['configured'] is True and st['fresh'] is False and st['signal_count'] == 0
    assert st['available'] is False


def test_fresh_magnific_snapshot_is_used(state, monkeypatch):
    monkeypatch.setattr(config, 'TREND_STALE_AFTER_DAYS', 14)
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _write_snapshot(state, now, [{'term': 'Black Friday', 'rank': 1}])
    feed = feed_mod.run_scan(today=TODAY)
    assert 'black friday' in feed['verified_search_interest_terms']
    st = feed['adapter_status']['magnific']
    assert st['fresh'] is True and st['signal_count'] == 1 and st['available'] is True


def test_magnific_uses_the_same_staleness_policy_as_trends_py(state, monkeypatch):
    from stock_factory import trend_import, trends
    monkeypatch.setattr(config, 'TREND_STALE_AFTER_DAYS', 5)
    ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=6)).isoformat()
    _write_snapshot(state, ts, [{'term': 'x', 'rank': 1}])
    snap = trend_import.load_history()[-1]
    assert trend_import.snapshot_is_fresh(snap) is False
    assert trends._latest_fresh_snapshot() is None
    assert MagnificManualImportAdapter().fetch(['x']) == []


# --- Google Trends ------------------------------------------------------

def test_google_old_observation_not_scored_as_current_demand(state, monkeypatch):
    _install_fake_bigquery(monkeypatch, rows=[
        {'term': 'black friday', 'week': _dt.date(2025, 11, 23), 'rank': 3,
         'refresh_date': _dt.date(2026, 7, 30)},
    ])
    feed = feed_mod.run_scan(today=TODAY)
    assert 'black friday' not in feed['verified_search_interest_terms']
    st = feed['adapter_status']['google_trends']
    assert st['fetch_succeeded'] is True and st['fresh'] is False


def test_google_signal_keeps_observation_region_unit_and_is_labeled_search_interest(state, monkeypatch):
    calls = _install_fake_bigquery(monkeypatch, rows=[
        {'term': 'black friday', 'week': _dt.date(2026, 7, 26), 'rank': 2,
         'refresh_date': _dt.date(2026, 7, 31)},
    ])
    adapter = GoogleTrendsBigQueryAdapter()
    sigs = adapter.fetch(['Black Friday'], today=TODAY)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.observation_date == '2026-07-26'
    assert s.fetched_at and not s.fetched_at.startswith('2026-07-26')
    assert s.region and s.unit == 'weekly_top_rising_rank'
    assert s.signal_type == base.SIGNAL_SEARCH_INTEREST == 'verified_search_interest'
    assert s.measure == 'search_interest'
    assert 'download' not in s.signal_type and 'purchase' not in s.signal_type
    assert s.fresh is True
    # one bounded query for all terms, with a hard bytes-billed cap and row limit
    assert calls['job_config'].maximum_bytes_billed and calls['job_config'].maximum_bytes_billed <= 10 * 1024 ** 3
    assert 'LIMIT' in calls['sql'].upper()
    feed = feed_mod.run_scan(today=TODAY)
    assert 'black friday' in feed['verified_search_interest_terms']
    assert 'verified_demand_terms' not in feed


def test_google_configured_without_dependency_reports_dependency_not_ready(state, monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.setitem(sys.modules, 'google.cloud.bigquery', None)  # import -> ImportError
    st = feed_mod.run_scan(today=TODAY)['adapter_status']['google_trends']
    assert st['configured'] is True and st['dependency_ready'] is False
    assert st['fetch_attempted'] is False and st['available'] is False


def test_google_query_exception_is_available_false_with_error(state, monkeypatch):
    _install_fake_bigquery(monkeypatch, raise_exc=RuntimeError('403 Access Denied: credentials'))
    st = feed_mod.run_scan(today=TODAY)['adapter_status']['google_trends']
    assert st['fetch_attempted'] is True and st['fetch_succeeded'] is False
    assert st['available'] is False
    assert '403' in st['error']


# --- every adapter ------------------------------------------------------

def test_status_shape_is_uniform_and_unconfigured_is_explicit(state):
    statuses = feed_mod.run_scan(today=TODAY)['adapter_status']
    assert set(statuses) == {'adobe', 'google_trends', 'magnific'}
    for name, st in statuses.items():
        assert STATUS_KEYS <= set(st), (name, st)
        assert st['configured'] is False and st['available'] is False and st['signal_count'] == 0


def test_adapter_exception_surfaces_as_unavailable_with_error(state, monkeypatch):
    from stock_factory.trend_intelligence.adapters.adobe_stock_adapter import AdobeStockSearchAdapter

    class Exploding(AdobeStockSearchAdapter):
        def available(self):
            return True

        def fetch(self, terms, today=None):
            raise ConnectionError('boom')

    monkeypatch.setattr('stock_factory.trend_intelligence.feed.AdobeStockSearchAdapter', Exploding)
    feed = feed_mod.run_scan(today=TODAY)
    st = feed['adapter_status']['adobe']
    assert st['available'] is False
    assert 'boom' in st['error']
    assert st['fetch_attempted'] is True and st['fetch_succeeded'] is False
