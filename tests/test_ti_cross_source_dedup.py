"""Finding 3 regression tests, run against the REAL selection pipeline
(trends.select_concepts_detailed reading a written feed + a written trend
snapshot), not just the key function: the same topic must collapse to one
candidate across sources, while genuinely different country/date/year
observances of a same-named event stay separate, and ambiguous matches are
not force-merged."""
from __future__ import annotations
import datetime as _dt
import json

import pytest

from stock_factory import config, trends
from stock_factory.trend_intelligence import feed as feed_mod

TODAY = _dt.date.today()


def _brief(name, country, event_date, score=0.8):
    # Synthetic brief whose production window covers TODAY (the window
    # itself is not what these tests exercise).
    return {
        'event_country': country, 'event_name': name, 'event_date': event_date,
        'format': 'PHOTO_JPG', 'demand_evidence': 'calendar_predicted_demand', 'demand_source': 'test',
        'buyer_ready_date': event_date, 'submission_deadline': event_date,
        'production_start': (TODAY - _dt.timedelta(days=1)).isoformat(),
        'production_deadline': (TODAY + _dt.timedelta(days=5)).isoformat(),
        'schedule_status': 'compressed',
        'creative_concept': f'Concept for {name} ({country} {event_date})',
        'differentiation_strategy': 'x', 'quantity_recommendation': 3, 'qc_ip_risk_notes': 'x',
        'title': name, 'keywords': [name.lower()], 'target_platform': 'magnific',
        'opportunity_score': score, 'production_pipeline_status': 'active',
    }


def _write_feed(briefs):
    feed = feed_mod.run_scan(today=TODAY)
    feed['creative_briefs'] = briefs
    feed['provenance']['git_sha'] = 'deadbeef'
    feed['provenance']['generator'] = 'stock_factory.trend_intelligence.scan'
    feed_mod.write_feed(feed)


def _write_snapshot(state_dir, terms):
    hist_dir = state_dir / 'trend_history'
    hist_dir.mkdir(parents=True, exist_ok=True)
    entry = {'imported_at': _dt.datetime.now(_dt.timezone.utc).isoformat(), 'source_file': 'manual.json',
             'sha256': 'fake', 'terms': terms}
    with (hist_dir / 'index.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    # This suite validates cross-tier calendar/trend identity only.
    monkeypatch.setattr(
        'stock_factory.trend_intelligence.market_briefs.load_market_briefs',
        lambda *args, **kwargs: ([], {'status': 'unavailable'}))
    monkeypatch.delenv('ADOBE_STOCK_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    return tmp_path / 'state'


def _named(concepts):
    return [c for c in concepts if c.source != 'static_topic_bank']


def test_black_friday_in_trend_snapshot_and_calendar_feed_is_one_candidate(state):
    bf = (TODAY + _dt.timedelta(days=60)).isoformat()
    _write_feed([_brief('Black Friday', 'US', bf)])
    _write_snapshot(state, [{'term': 'black friday', 'category': 'retail', 'rank': 1}])
    named = _named(trends.select_concepts_detailed(TODAY.isoformat(), 20))
    bf_concepts = [c for c in named if 'black friday' in (c.trend_term or c.category).lower()]
    assert len(bf_concepts) == 1, [(c.source, c.category, c.trend_term) for c in named]
    merged = bf_concepts[0]
    # provenance of both sources is kept on the single surviving candidate
    assert set(merged.merged_sources) == {'trend_snapshot', 'calendar_opportunity'}
    assert merged.event_country == 'US' and merged.event_date == bf


def test_same_named_holiday_in_different_countries_and_dates_stays_separate(state):
    d1 = (TODAY + _dt.timedelta(days=60)).isoformat()
    d2 = (TODAY + _dt.timedelta(days=63)).isoformat()
    _write_feed([_brief("Mother's Day", 'GB', d1), _brief("Mother's Day", 'US', d2),
                 _brief('Christmas Day', 'US', d1), _brief('Christmas Day', 'GB', d1)])
    named = _named(trends.select_concepts_detailed(TODAY.isoformat(), 20))
    assert len([c for c in named if 'mother' in c.category.lower()]) == 2
    mothers = sorted((c.event_country, c.event_date) for c in named if "mother" in c.category.lower())
    assert mothers == sorted([('GB', d1), ('US', d2)])
    christmas = sorted(c.event_country for c in named if 'christmas' in c.category.lower())
    assert christmas == ['GB', 'US']  # same date, different markets: still two candidates


def test_ambiguous_trend_term_is_not_force_merged(state):
    d1 = (TODAY + _dt.timedelta(days=60)).isoformat()
    d2 = (TODAY + _dt.timedelta(days=63)).isoformat()
    _write_feed([_brief("Mother's Day", 'GB', d1), _brief("Mother's Day", 'US', d2)])
    _write_snapshot(state, [{'term': "mother's day", 'category': 'family', 'rank': 1}])
    named = _named(trends.select_concepts_detailed(TODAY.isoformat(), 20))
    # trend term can't be attributed to one specific country/date -> nothing merged
    assert len([c for c in named if 'mother' in (c.trend_term or c.category).lower()]) == 3
    assert all(len(c.merged_sources) == 1 for c in named)


def test_same_calendar_event_in_two_years_is_never_merged(state):
    _write_feed([_brief('Black Friday', 'US', '2026-11-27'), _brief('Black Friday', 'US', '2027-11-26')])
    named = _named(trends.select_concepts_detailed(TODAY.isoformat(), 20))
    assert len([c for c in named if 'black friday' in c.category.lower()]) == 2
    years = sorted(c.event_date for c in named if 'black friday' in c.category.lower())
    assert years == ['2026-11-27', '2027-11-26']


def test_dedup_key_is_source_independent():
    a = trends.Concept(category='retail', scene='x', source='trend_snapshot', trend_term='Black  Friday!')
    b = trends.Concept(category='calendar:Black Friday', scene='y', source='calendar_opportunity',
                       event_country='US', event_date='2026-11-27', topic='black friday')
    assert trends.normalize_topic(a.trend_term) == trends.normalize_topic('black friday') == 'black friday'
    assert trends._topic_of(a) == trends._topic_of(b)
