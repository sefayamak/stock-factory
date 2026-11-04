"""Tests for the global trend-intelligence calendar, early-warning scan,
and scoring. All use the `holidays` library's offline computation and a
fixed `today` -- no live network access."""
from __future__ import annotations
import datetime as _dt

from stock_factory.trend_intelligence import calendar_sources, early_warning, scoring
from stock_factory.trend_intelligence.events import Event


def _names_on(events, country, year, month, day):
    target = _dt.date(year, month, day)
    return [e.english_name for e in events if e.country == country and e.event_date == target]


def test_thanksgiving_2026():
    events = calendar_sources.holiday_events(2026, ['US'])
    assert any('Thanksgiving' in n for n in _names_on(events, 'US', 2026, 11, 26))


def test_black_friday_cyber_monday_2026():
    events = calendar_sources.retail_campaign_events(2026)
    by_name = {e.english_name: e.event_date for e in events}
    assert by_name['Black Friday'] == _dt.date(2026, 11, 27)
    assert by_name['Cyber Monday'].weekday() == 0  # Monday
    assert by_name['Cyber Monday'] > by_name['Black Friday']


def test_christmas_2026():
    events = calendar_sources.holiday_events(2026, ['US'])
    assert any('Christmas' in n for n in _names_on(events, 'US', 2026, 12, 25))


def test_ramadan_eid_movable_dates_2026():
    events = calendar_sources.holiday_events(2026, ['SA'])
    eid_names = [e.english_name for e in events if 'عيد' in e.english_name or 'فطر' in e.english_name]
    assert eid_names, 'expected at least one Eid al-Fitr holiday entry for Saudi Arabia in 2026'


def test_ramadan_eid_dates_differ_by_year():
    # Movable lunar dates must be recomputed per year, never copied forward.
    events_2026 = calendar_sources.holiday_events(2026, ['SA'])
    events_2027 = calendar_sources.holiday_events(2027, ['SA'])
    fitr_2026 = sorted(e.event_date for e in events_2026 if 'فطر' in e.english_name)
    fitr_2027 = sorted(e.event_date for e in events_2027 if 'فطر' in e.english_name)
    assert fitr_2026 and fitr_2027
    assert fitr_2026[0] != fitr_2027[0]


def test_lunar_new_year_2026():
    events = calendar_sources.holiday_events(2026, ['CN'])
    assert any('春节' in e.english_name for e in events if e.event_date == _dt.date(2026, 2, 17))


def test_diwali_2026():
    events = calendar_sources.holiday_events(2026, ['IN'])
    assert any('Diwali' in e.english_name for e in events)


def test_holi_2026():
    events = calendar_sources.holiday_events(2026, ['IN'])
    assert any('Holi' in e.english_name for e in events)


def test_hanukkah_2026():
    events = calendar_sources.holiday_events(2026, ['IL'])
    assert any('חנוכה' in e.english_name for e in events)


def test_nowruz_2026():
    events = calendar_sources.holiday_events(2026, ['IR'])
    assert any('نوروز' in e.english_name or 'عیدنوروز' in e.english_name for e in events)


def test_southern_hemisphere_season_offset():
    events = calendar_sources.season_events(2026)
    dec_solstice = [e for e in events if e.local_name == 'December solstice']
    assert len(dec_solstice) == 2
    northern = next(e for e in dec_solstice if e.hemisphere == 'N')
    southern = next(e for e in dec_solstice if e.hemisphere == 'S')
    assert northern.event_date == southern.event_date  # same instant
    assert 'winter' in northern.english_name.lower()
    assert 'summer' in southern.english_name.lower()


def test_country_specific_holiday_only_appears_for_requested_country():
    events = calendar_sources.holiday_events(2026, ['US'])
    assert all(e.country == 'US' for e in events)
    assert not any('Diwali' in e.english_name for e in events)


def test_unknown_country_code_does_not_crash():
    events = calendar_sources.holiday_events(2026, ['ZZ', 'US'])
    assert all(e.country != 'ZZ' for e in events)
    assert any(e.country == 'US' for e in events)


def test_conflicting_or_overlapping_holiday_names_grouped_as_duplicates():
    events = calendar_sources.holiday_events(2026, ['US', 'CA']) + calendar_sources.holiday_events(2026, ['CA'])
    # Christmas appears in both US and CA on the same date -- should be
    # detected as a duplicate-across-countries group, not silently merged
    # or silently doubled without anyone noticing.
    all_events = calendar_sources.holiday_events(2026, ['US', 'CA'])
    groups = calendar_sources.find_duplicate_groups(all_events)
    christmas_groups = [v for k, v in groups.items() if 'christmas' in k[1]]
    assert christmas_groups, 'expected Christmas to be flagged as a cross-country duplicate group'
    countries = {e.country for e in christmas_groups[0]}
    assert {'US', 'CA'}.issubset(countries)


def test_missing_trend_data_falls_back_to_calendar_prediction():
    event = Event(
        country='US', event_date=_dt.date(2026, 11, 26), local_name='Thanksgiving Day',
        english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='2026-01-01',
    )
    score = scoring.score_event(event, today=_dt.date(2026, 8, 1), verified_demand_terms=None)
    assert score.demand_label == 'calendar_predicted_demand'
    assert 0.0 < score.total <= 1.0


def test_verified_trend_term_is_labeled_separately_from_predicted():
    event = Event(
        country='US', event_date=_dt.date(2026, 11, 26), local_name='Thanksgiving Day',
        english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='2026-01-01',
    )
    verified_score = scoring.score_event(event, today=_dt.date(2026, 8, 1), verified_demand_terms={'thanksgiving day'})
    predicted_score = scoring.score_event(event, today=_dt.date(2026, 8, 1), verified_demand_terms=None)
    assert verified_score.demand_label == 'verified_search_interest'
    assert predicted_score.demand_label == 'calendar_predicted_demand'
    assert verified_score.total >= predicted_score.total


def test_catalog_supply_is_never_treated_as_demand():
    """Regression test for PR #1 review finding: Adobe Stock nb_results is
    a SUPPLY/competition signal, not search demand. A term appearing only
    in catalog_supply_by_term must not flip demand_label to
    verified_search_interest, and must not appear in verified_search_interest_terms
    in the feed (covered in test_trend_intelligence_adapters_and_feed.py)."""
    event = Event(
        country='US', event_date=_dt.date(2026, 11, 26), local_name='Thanksgiving Day',
        english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='2026-01-01',
    )
    score = scoring.score_event(
        event, today=_dt.date(2026, 8, 1),
        verified_demand_terms=None,
        catalog_supply_by_term={'thanksgiving day': 500_000.0},
    )
    assert score.demand_label == 'calendar_predicted_demand'
    assert score.competition_label == 'catalog_supply'
    # High existing supply (500k results) should pull the competition_gap
    # factor down (less room/gap), not up.
    assert score.factors['competition_gap'] < 0.5


def test_competition_gap_defaults_safely_without_supply_data():
    event = Event(
        country='US', event_date=_dt.date(2026, 11, 26), local_name='Thanksgiving Day',
        english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='2026-01-01',
    )
    score = scoring.score_event(event, today=_dt.date(2026, 8, 1))
    assert score.competition_label == 'no_supply_data_available'
    assert score.factors['competition_gap'] == 0.5


def test_historical_download_performance_is_its_own_factor():
    event = Event(
        country='US', event_date=_dt.date(2026, 11, 26), local_name='Thanksgiving Day',
        english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='2026-01-01',
    )
    score = scoring.score_event(event, today=_dt.date(2026, 8, 1))
    assert 'historical_download_performance' in score.factors
    # No download data exists in this repo: the factor is explicitly
    # unavailable (review finding 7), not filled with the acceptance rate.
    assert score.factors['historical_download_performance'] is None
    assert score.to_dict()['factors']['historical_download_performance'] == 'unavailable'


def test_production_lead_time_math_missed_opportunity_detector():
    # Thanksgiving 2026 (Nov 26) scanned from 20 days out: well inside the
    # ~49-day total lead time, and no earlier 120/90/60/30-day alert could
    # have fired yet at this vantage point -- this is exactly the missed
    # scenario the brief describes.
    event = Event(
        country='US', event_date=_dt.date(2026, 11, 26), local_name='Thanksgiving Day',
        english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='2026-01-01',
    )
    today = _dt.date(2026, 11, 6)  # 20 days out
    missed = early_warning.missed_opportunity_check([event], today)
    assert len(missed) == 1
    assert missed[0]['days_out'] == 20
    assert missed[0]['shortfall_days'] == early_warning.TOTAL_LEAD_DAYS - 20


def test_production_lead_time_math_not_missed_when_scanned_early():
    event = Event(
        country='US', event_date=_dt.date(2026, 11, 26), local_name='Thanksgiving Day',
        english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='2026-01-01',
    )
    today = _dt.date(2026, 7, 29)  # exactly 120 days out -> alert threshold, not "missed"
    missed = early_warning.missed_opportunity_check([event], today)
    assert missed == []
    alerts = early_warning.alerts_for([event], today)
    assert any(a.threshold_days == 120 for a in alerts)


def test_alerts_fire_at_each_threshold():
    event = Event(
        country='US', event_date=_dt.date(2026, 11, 26), local_name='Thanksgiving Day',
        english_name='Thanksgiving Day', category='national_holiday', source='test', verified_at='2026-01-01',
    )
    fired_thresholds = set()
    for threshold in early_warning.ALERT_THRESHOLDS_DAYS:
        today = event.event_date - _dt.timedelta(days=threshold)
        alerts = early_warning.alerts_for([event], today)
        assert any(a.threshold_days == threshold for a in alerts)
        fired_thresholds.add(threshold)
    assert fired_thresholds == set(early_warning.ALERT_THRESHOLDS_DAYS)


def test_windowed_events_buckets_correctly():
    today = _dt.date(2026, 1, 1)
    events = [
        Event(country='US', event_date=today + _dt.timedelta(days=5), local_name='A', english_name='A',
              category='national_holiday', source='test', verified_at='2026-01-01'),
        Event(country='US', event_date=today + _dt.timedelta(days=200), local_name='B', english_name='B',
              category='national_holiday', source='test', verified_at='2026-01-01'),
        Event(country='US', event_date=today + _dt.timedelta(days=400), local_name='C', english_name='C',
              category='national_holiday', source='test', verified_at='2026-01-01'),
    ]
    buckets = early_warning.windowed_events(events, today)
    assert any(e.english_name == 'A' for e in buckets[7])
    assert all(e.english_name != 'A' for e in buckets[7] if e.english_name == 'C')
    assert any(e.english_name == 'B' for e in buckets[365])
    assert all(e.english_name != 'C' for e in buckets[365])


def test_un_observance_dates_are_fixed_and_global():
    events = calendar_sources.un_observance_events(2026)
    assert all(e.country == 'GLOBAL' for e in events)
    assert any(e.english_name == "International Women's Day" and e.event_date == _dt.date(2026, 3, 8) for e in events)


def test_movable_dates_are_never_hardcoded_across_years():
    diwali_2026 = [e.event_date for e in calendar_sources.holiday_events(2026, ['IN']) if 'Diwali' in e.english_name]
    diwali_2027 = [e.event_date for e in calendar_sources.holiday_events(2027, ['IN']) if 'Diwali' in e.english_name]
    assert diwali_2026 and diwali_2027
    assert diwali_2026[0] != diwali_2027[0]
