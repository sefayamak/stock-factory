"""Finding 7 regression tests: metric and capability labels must say what
they actually are."""
from __future__ import annotations
import datetime as _dt

import pytest

from stock_factory import acceptance_learning, config
from stock_factory.trend_intelligence import scoring, briefs, calendar_sources, feed as feed_mod
from stock_factory.trend_intelligence.events import Event

TODAY = _dt.date(2026, 8, 1)


def _tg():
    return Event(country='US', event_date=_dt.date(2026, 11, 26), local_name='Thanksgiving Day',
                 english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='')


@pytest.fixture(scope='module')
def feed(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(config, 'STATE_DIR', tmp_path_factory.mktemp('s') / 'state')
    mp.delenv('ADOBE_STOCK_API_KEY', raising=False)
    mp.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    f = feed_mod.run_scan(today=TODAY)
    yield f
    mp.undo()


def test_acceptance_rate_is_not_presented_as_download_performance():
    s = scoring.score_event(_tg(), TODAY)
    d = s.to_dict()
    assert d['factors']['historical_download_performance'] == 'unavailable'
    assert s.factors['historical_download_performance'] is None
    rate = round(acceptance_learning.MAGNIFIC_BASELINE['acceptance_rate'], 2)
    assert all(v != rate for k, v in s.factors.items() if 'download' in k)


def test_feed_reports_download_data_unavailable_and_acceptance_rate_under_its_own_name(feed):
    assert feed['historical_download_performance']['status'] == 'unavailable'
    par = feed['portfolio_acceptance_rate']
    assert par['value'] == acceptance_learning.MAGNIFIC_BASELINE['acceptance_rate']
    assert 'not per-topic' in par['scope'] and 'not downloads' in par['scope']
    assert 'historical_download_performance_basis' not in feed


def test_portfolio_coverage_not_computed_without_topic_data():
    s = scoring.score_event(_tg(), TODAY)
    assert s.factors['portfolio_coverage'] is None
    assert s.to_dict()['factors']['portfolio_coverage'] == 'not_computed'
    computed = scoring.score_event(_tg(), TODAY, existing_topics={'thanksgiving'})
    assert computed.factors['portfolio_coverage'] == 0.0  # covered -> inverted factor 0


def test_total_uses_only_computed_factors_renormalized():
    s = scoring.score_event(_tg(), TODAY)
    computed = {k: v for k, v in s.factors.items() if v is not None}
    expected = sum(v * scoring.WEIGHTS[k] for k, v in computed.items()) / sum(scoring.WEIGHTS[k] for k in computed)
    assert abs(s.total - expected) < 1e-9
    assert 0.0 <= s.total <= 1.0


def test_vector_eps_briefs_are_labeled_planned_blocked_not_production(feed):
    by_fmt = {}
    for b in feed['creative_briefs']:
        by_fmt.setdefault(b['format'], set()).add(b['production_pipeline_status'])
    assert by_fmt.get('PHOTO_JPG') == {'active'}
    assert by_fmt.get('VECTOR_EPS') == {'planned_blocked'}
    assert briefs.FORMAT_PIPELINE_STATUS['VECTOR_EPS'] == 'planned_blocked'
    assert feed['brief_counts_by_pipeline_status']['planned_blocked'] > 0


def test_calendar_coverage_is_never_presented_as_worldwide(feed):
    cov = feed['calendar_coverage']
    assert cov['is_worldwide'] is False
    assert cov['countries_covered'] == len(calendar_sources.SUPPORTED_COUNTRIES)
    assert cov['library_supported_not_covered'], 'gap list must be explicit'
    assert not set(cov['library_supported_not_covered']) & set(calendar_sources.SUPPORTED_COUNTRIES)
    assert cov['gaps']


def test_scan_date_kept_separate_from_source_verification(feed):
    sv = feed['source_verification']
    assert sv['calendar_generated_on'] == TODAY.isoformat()
    assert sv['un_observances']['list_last_verified_on'] == calendar_sources.UN_LIST_VERIFIED_ON
    assert sv['holidays_library']['last_verified_against_official_source'] is None
    # Events computed from the holidays library were NOT verified on scan day.
    hol = calendar_sources.holiday_events(2026, ['US'])
    assert hol and all(e.verified_at == '' for e in hol)
    un = calendar_sources.un_observance_events(2027)
    assert all(e.verified_at == calendar_sources.UN_LIST_VERIFIED_ON for e in un)
