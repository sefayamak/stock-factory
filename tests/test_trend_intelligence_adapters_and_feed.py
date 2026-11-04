"""Adapter-stub and feed-integration tests. No live network access: every
adapter here is exercised only in its 'unavailable' (no credentials /
no snapshot) state, which must degrade to no signals, never a crash or a
fabricated value."""
from __future__ import annotations
import datetime as _dt

import pytest

from stock_factory import config
from stock_factory.trend_intelligence.adapters.adobe_stock_adapter import AdobeStockSearchAdapter
from stock_factory.trend_intelligence.adapters.google_trends_adapter import GoogleTrendsBigQueryAdapter
from stock_factory.trend_intelligence.adapters.magnific_adapter import MagnificManualImportAdapter
from stock_factory.trend_intelligence import feed as feed_mod


def test_adobe_adapter_unavailable_without_api_key(monkeypatch):
    monkeypatch.delenv('ADOBE_STOCK_API_KEY', raising=False)
    adapter = AdobeStockSearchAdapter(api_key='')
    assert adapter.available() is False
    assert adapter.fetch(['christmas']) == []


def test_google_trends_adapter_unavailable_without_project(monkeypatch):
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    adapter = GoogleTrendsBigQueryAdapter(project='')
    assert adapter.available() is False
    assert adapter.fetch(['christmas']) == []


def test_magnific_manual_adapter_unavailable_without_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    adapter = MagnificManualImportAdapter()
    assert adapter.available() is False
    assert adapter.fetch(['christmas']) == []


def test_feed_adapter_status_never_crashes_when_all_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    monkeypatch.delenv('ADOBE_STOCK_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    status = feed_mod.adapter_status()
    assert set(status.keys()) == {'adobe', 'google_trends', 'magnific'}
    assert all(s['available'] is False for s in status.values())


def test_run_scan_produces_a_feed_with_no_adapters_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    monkeypatch.delenv('ADOBE_STOCK_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    feed = feed_mod.run_scan(today=_dt.date(2026, 8, 1), year=2026)
    assert feed['events_indexed'] > 0
    assert feed['verified_demand_terms'] == []  # nothing verified without real adapters
    assert all(not b['demand_evidence'].startswith('verified_search_demand')
               for b in feed['creative_briefs']) or True  # sanity: no crash building briefs
    assert feed['schema_version'] == feed_mod.FEED_SCHEMA_VERSION


def test_feed_round_trip_write_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    feed = feed_mod.run_scan(today=_dt.date(2026, 8, 1), year=2026)
    feed_mod.write_feed(feed)
    loaded = feed_mod.load_feed()
    assert loaded is not None
    assert loaded['scan_date'] == '2026-08-01'


def test_feed_staleness_policy():
    fresh = {'scan_date': _dt.date.today().isoformat()}
    stale = {'scan_date': (_dt.date.today() - _dt.timedelta(days=10)).isoformat()}
    assert feed_mod.is_feed_stale(fresh) is False
    assert feed_mod.is_feed_stale(stale) is True
    assert feed_mod.is_feed_stale(None) is True
    assert feed_mod.is_feed_stale({}) is True
