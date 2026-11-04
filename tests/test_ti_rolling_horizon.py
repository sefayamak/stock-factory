"""Finding 1 regression tests: the scan must look a real HORIZON_DAYS
(365) days ahead from the scan date -- not "this calendar year, plus next
year only once fewer than 90 days remain" -- and nothing outside
[scan_date, scan_date + HORIZON_DAYS] may reach production candidates."""
from __future__ import annotations
import datetime as _dt

import pytest

from stock_factory import config
from stock_factory.trend_intelligence import feed as feed_mod, early_warning


def _horizon_end(today):
    return today + _dt.timedelta(days=early_warning.HORIZON_DAYS)


def _assert_no_out_of_horizon_candidates(feed, today):
    end = _horizon_end(today)
    for s in feed['top_opportunities']:
        d = _dt.date.fromisoformat(s['event']['event_date'])
        assert today <= d <= end, f'top_opportunity outside horizon: {d} ({s["event"]["english_name"]})'
    for b in feed['creative_briefs']:
        d = _dt.date.fromisoformat(b['event_date'])
        assert today <= d <= end, f'brief outside horizon: {d} ({b["event_name"]})'
    for a in feed['alerts']:
        d = _dt.date.fromisoformat(a['event_date'])
        assert today <= d <= end


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    monkeypatch.delenv('ADOBE_STOCK_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)


def test_horizon_is_365_days():
    assert early_warning.HORIZON_DAYS == 365


@pytest.mark.parametrize('today', [
    _dt.date(2026, 1, 1), _dt.date(2026, 8, 1), _dt.date(2026, 12, 31),
    _dt.date(2028, 2, 29),   # leap day scan
    _dt.date(2027, 12, 31),  # year-boundary scan
])
def test_horizon_events_cover_exactly_scan_date_to_plus_365(today):
    events = feed_mod.collect_horizon_events(today)
    end = _horizon_end(today)
    assert events
    assert all(today <= e.event_date <= end for e in events)
    # Something must exist in the last ~2 months of the horizon too (no
    # "cliff" at the calendar-year boundary).
    assert any(e.event_date >= end - _dt.timedelta(days=60) for e in events)


def test_august_scan_surfaces_next_years_january_to_july_events():
    today = _dt.date(2026, 8, 1)
    events = feed_mod.collect_horizon_events(today)
    next_year_h1 = [e for e in events if e.event_date.year == 2027 and e.event_date.month <= 7]
    assert next_year_h1, 'Aug 2026 scan must see Jan-Jul 2027 events'
    names = {(e.country, e.event_date) for e in next_year_h1}
    # New Year's Day 2027 (US) and Lunar New Year 2027 (CN, Feb 6) are inside the horizon.
    assert ('US', _dt.date(2027, 1, 1)) in names
    assert ('CN', _dt.date(2027, 2, 6)) in names
    # ...and nothing from Jan-Jul 2026 (already past) is included.
    assert not [e for e in events if e.event_date < today]


@pytest.mark.parametrize('today', [
    _dt.date(2026, 1, 1), _dt.date(2026, 8, 1), _dt.date(2026, 12, 31),
    _dt.date(2028, 2, 29), _dt.date(2027, 12, 31),
])
def test_run_scan_never_ranks_events_outside_horizon(isolated_state, today):
    feed = feed_mod.run_scan(today=today)
    _assert_no_out_of_horizon_candidates(feed, today)
    assert feed['horizon']['start'] == today.isoformat()
    assert feed['horizon']['end'] == _horizon_end(today).isoformat()
    # every indexed event is inside the horizon, so the 365-day window holds all of them
    assert feed['window_counts']['365'] == feed['events_indexed']


def test_leap_day_horizon_end_is_one_year_later():
    today = _dt.date(2028, 2, 29)
    assert _horizon_end(today) == _dt.date(2029, 2, 28)
    events = feed_mod.collect_horizon_events(today)
    assert any(e.event_date.year == 2029 for e in events)
