"""Finding 2 regression tests: production/submission deadlines are a
single, named, configurable date model shared by scoring, briefs,
early-warning and the trends.py consumer -- and opportunities whose
submission deadline has already passed are bucketed as late, never ranked
or briefed as normal on-time candidates."""
from __future__ import annotations
import datetime as _dt

import pytest

from stock_factory import config, trends
from stock_factory.trend_intelligence import deadlines, scoring, briefs, feed as feed_mod
from stock_factory.trend_intelligence.events import Event

THANKSGIVING = _dt.date(2026, 11, 26)


def _event(d=THANKSGIVING, name='Thanksgiving Day', country='US', category='national_holiday'):
    return Event(country=country, event_date=d, local_name=name, english_name=name,
                 category=category, source='test', verified_at='')


def test_schedule_has_separate_named_dates_derived_from_configurable_durations():
    s = deadlines.schedule_for(THANKSGIVING)
    assert s.event_date == THANKSGIVING
    assert s.buyer_ready_date == THANKSGIVING - _dt.timedelta(days=deadlines.BUYER_LEAD_DAYS)
    assert s.submission_deadline == s.buyer_ready_date - _dt.timedelta(days=deadlines.PLATFORM_REVIEW_DAYS)
    assert s.production_deadline == s.submission_deadline - _dt.timedelta(days=deadlines.SUBMISSION_PREP_DAYS)
    assert s.production_start == s.production_deadline - _dt.timedelta(days=deadlines.PRODUCTION_DAYS)
    # review time is subtracted from the delivery date, not folded into production
    assert s.production_start < s.production_deadline <= s.submission_deadline < s.buyer_ready_date < s.event_date
    assert deadlines.total_lead_days() == (deadlines.BUYER_LEAD_DAYS + deadlines.PLATFORM_REVIEW_DAYS
                                           + deadlines.SUBMISSION_PREP_DAYS + deadlines.PRODUCTION_DAYS)


def test_durations_are_configurable(monkeypatch):
    monkeypatch.setattr(deadlines, 'PLATFORM_REVIEW_DAYS', 10)
    monkeypatch.setattr(deadlines, 'BUYER_LEAD_DAYS', 0)
    monkeypatch.setattr(deadlines, 'PRODUCTION_DAYS', 5)
    monkeypatch.setattr(deadlines, 'SUBMISSION_PREP_DAYS', 0)
    s = deadlines.schedule_for(THANKSGIVING)
    assert s.submission_deadline == THANKSGIVING - _dt.timedelta(days=10)
    assert s.production_start == THANKSGIVING - _dt.timedelta(days=15)


def test_status_on_time_compressed_late():
    s = deadlines.schedule_for(THANKSGIVING)
    assert s.status(s.production_start) == deadlines.ON_TIME
    assert s.status(s.production_start + _dt.timedelta(days=1)) == deadlines.COMPRESSED
    assert s.status(s.submission_deadline) == deadlines.COMPRESSED
    assert s.status(s.submission_deadline + _dt.timedelta(days=1)) == deadlines.LATE


def test_brief_uses_same_date_model_as_scoring():
    today = _dt.date(2026, 8, 1)
    score = scoring.score_event(_event(), today)
    s = deadlines.schedule_for(THANKSGIVING)
    assert score.schedule == s
    b = briefs.build_brief(score, 'PHOTO_JPG').to_dict()
    assert b['event_date'] == s.event_date.isoformat()
    assert b['buyer_ready_date'] == s.buyer_ready_date.isoformat()
    assert b['submission_deadline'] == s.submission_deadline.isoformat()
    assert b['production_start'] == s.production_start.isoformat()
    assert b['production_deadline'] == s.production_deadline.isoformat()
    assert b['schedule_status'] == deadlines.ON_TIME
    # the old ambiguous "event_date - 49 .. event_date" window is gone
    assert 'production_window_end' not in b


def test_late_opportunity_is_not_ranked_or_briefed_as_on_time(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    today = _dt.date(2026, 11, 6)  # Thanksgiving 20 days out: submission deadline long passed
    s = deadlines.schedule_for(THANKSGIVING)
    assert s.status(today) == deadlines.LATE
    feed = feed_mod.run_scan(today=today)
    for opp in feed['top_opportunities']:
        assert opp['schedule']['status'] != deadlines.LATE, opp['event']['english_name']
        assert opp['event']['english_name'] != 'Thanksgiving Day'
    for b in feed['creative_briefs']:
        assert b['schedule_status'] != deadlines.LATE
        assert b['submission_deadline'] >= today.isoformat()
    late_names = {o['event']['english_name'] for o in feed['late_opportunities']}
    assert 'Thanksgiving Day' in late_names
    assert all(o['schedule']['status'] == deadlines.LATE for o in feed['late_opportunities'])


def test_scoring_marks_late_and_gives_no_urgency():
    today = _dt.date(2026, 11, 6)
    score = scoring.score_event(_event(), today)
    assert score.schedule_status == deadlines.LATE
    assert score.factors['seasonal_urgency'] == 0.0


def test_trends_consumer_skips_brief_past_production_deadline(tmp_path, monkeypatch):
    """Even if a feed (e.g. 2 days old) still lists a brief, the consumer
    must not queue it on a day after its production deadline."""
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    today = _dt.date.today()
    ev = _event(d=today + _dt.timedelta(days=deadlines.total_lead_days() - deadlines.PRODUCTION_DAYS + 1),
                name='Synthetic Festival', country='GB')
    feed = feed_mod.run_scan(today=today)
    score = scoring.score_event(ev, today)
    b = briefs.build_brief(score, 'PHOTO_JPG').to_dict()
    assert b['production_start'] <= today.isoformat() <= b['production_deadline']
    feed['creative_briefs'] = [b]
    feed['provenance']['git_sha'] = 'deadbeef'
    feed_mod.write_feed(feed)
    on_day = trends.select_concepts_detailed(today.isoformat(), 10)
    assert any(c.source == 'calendar_opportunity' for c in on_day)
    after_deadline = (_dt.date.fromisoformat(b['production_deadline']) + _dt.timedelta(days=1)).isoformat()
    later = trends.select_concepts_detailed(after_deadline, 10)
    assert not any(c.source == 'calendar_opportunity' for c in later)
