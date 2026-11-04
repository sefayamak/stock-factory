"""Finding 5 regression tests: alert history is persisted on disk
(state/intelligence/alert_history.json) across runs, so a crossed
lead-time threshold is alerted exactly once even across a scan gap, an
already-alerted event is never re-alerted, unknown production status is
reported as "unknown", and "missed" is never claimed for an event that was
already alerted or is already in production."""
from __future__ import annotations
import datetime as _dt
import json

import pytest

from stock_factory import config
from stock_factory.trend_intelligence import feed as feed_mod, early_warning, alert_history, deadlines
from stock_factory.trend_intelligence.events import Event

THANKSGIVING = _dt.date(2026, 11, 26)


def _tg():
    return Event(country='US', event_date=THANKSGIVING, local_name='Thanksgiving Day',
                 english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='')


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    monkeypatch.delenv('ADOBE_STOCK_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    return tmp_path / 'state'


def _tg_alerts(feed):
    return [a for a in feed['alerts'] if a['country'] == 'US' and a['english_name'] == 'Thanksgiving Day']


def test_scan_gap_skipping_threshold_day_still_alerts_exactly_once(state):
    day_121 = THANKSGIVING - _dt.timedelta(days=121)
    day_118 = THANKSGIVING - _dt.timedelta(days=118)   # the 120-day threshold day was skipped
    day_117 = THANKSGIVING - _dt.timedelta(days=117)
    assert _tg_alerts(feed_mod.run_scan(today=day_121)) == []
    caught_up = _tg_alerts(feed_mod.run_scan(today=day_118))
    assert len(caught_up) == 1
    assert caught_up[0]['threshold_days'] == 120
    assert caught_up[0]['catch_up'] is True
    assert _tg_alerts(feed_mod.run_scan(today=day_117)) == []  # not re-alerted next scan


def test_history_survives_across_runs_on_disk(state):
    day_120 = THANKSGIVING - _dt.timedelta(days=120)
    feed_mod.run_scan(today=day_120)
    path = state / 'intelligence' / 'alert_history.json'
    assert path.exists()
    data = json.loads(path.read_text())
    rec = data['events'][_tg().key()]
    assert rec['alerted_thresholds'] == [120]
    assert rec['first_seen'] <= day_120.isoformat()
    assert rec['production_status'] == 'unknown'
    assert data['last_successful_scan_date'] == day_120.isoformat()


def test_already_alerted_event_is_not_realerted_on_rerun_same_day(state):
    day_120 = THANKSGIVING - _dt.timedelta(days=120)
    assert len(_tg_alerts(feed_mod.run_scan(today=day_120))) == 1
    assert _tg_alerts(feed_mod.run_scan(today=day_120)) == []


def test_each_threshold_alerts_once_over_a_daily_sequence(state):
    # Daily scans, each loading and saving the on-disk history (the same
    # load/evaluate/save path run_scan uses, minus the full calendar build).
    fired = []
    for days_out in range(125, 25, -1):
        hist = alert_history.load_history()
        alerts, _ = early_warning.evaluate([_tg()], THANKSGIVING - _dt.timedelta(days=days_out), hist)
        alert_history.save_history(hist)
        fired += [a.threshold_days for a in alerts]
    assert fired == [120, 90, 60, 30]


def test_long_gap_crossing_several_thresholds_alerts_once(state):
    feed_mod.run_scan(today=THANKSGIVING - _dt.timedelta(days=130))
    feed = feed_mod.run_scan(today=THANKSGIVING - _dt.timedelta(days=58))  # 120, 90, 60 all skipped
    alerts = _tg_alerts(feed)
    assert len(alerts) == 1
    assert sorted(alerts[0]['thresholds_crossed']) == [60, 90, 120]
    assert feed['alert_state']['scan_gap_days'] == 72


def test_not_missed_when_already_alerted(state):
    hist = alert_history.load_history()
    early_warning.evaluate([_tg()], THANKSGIVING - _dt.timedelta(days=120), hist)  # 120-day alert recorded
    later = THANKSGIVING - _dt.timedelta(days=40)  # inside lead time, no scans in between
    assert deadlines.schedule_for(THANKSGIVING).status(later) != deadlines.ON_TIME
    _, missed = early_warning.evaluate([_tg()], later, hist)
    assert missed == []
    assert early_warning.missed_opportunity_check([_tg()], later, hist) == []


def test_first_seen_inside_lead_time_is_missed_with_unknown_production_status(state):
    hist = alert_history.load_history()
    _, missed = early_warning.evaluate([_tg()], THANKSGIVING - _dt.timedelta(days=40), hist)
    assert len(missed) == 1
    assert missed[0]['production_status'] == 'unknown'   # never a false "not produced"
    assert 'not produced' not in json.dumps(missed[0]).lower()


def test_not_missed_when_already_in_production(state):
    hist = alert_history.load_history()
    alert_history.set_production_status(hist, _tg().key(), 'in_production')
    _, missed = early_warning.evaluate([_tg()], THANKSGIVING - _dt.timedelta(days=40), hist)
    assert missed == []


def test_missed_reported_once_not_every_scan(state):
    first = feed_mod.run_scan(today=THANKSGIVING - _dt.timedelta(days=40))
    assert any(m['event']['english_name'] == 'Thanksgiving Day' and m['event']['country'] == 'US'
               for m in first['missed_opportunities'])
    second = feed_mod.run_scan(today=THANKSGIVING - _dt.timedelta(days=39))
    assert not any(m['event']['english_name'] == 'Thanksgiving Day' and m['event']['country'] == 'US'
                   for m in second['missed_opportunities'])


def test_corrupt_history_file_does_not_crash_and_is_reported(state):
    d = state / 'intelligence'
    d.mkdir(parents=True)
    (d / 'alert_history.json').write_text('{not json')
    feed = feed_mod.run_scan(today=THANKSGIVING - _dt.timedelta(days=120))
    assert feed['alert_state']['history_load_status'] == 'corrupt_reset'
    assert len(_tg_alerts(feed)) == 1
