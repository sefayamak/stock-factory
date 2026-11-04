"""Finding 4 regression tests: verify_feed (CLI) and the trends.py
consumer use ONE shared validator, and every failure mode fails soft (no
crash) while contributing ZERO calendar candidates to selection."""
from __future__ import annotations
import datetime as _dt
import hashlib
import json

import pytest

from stock_factory import config, trends
from stock_factory.trend_intelligence import feed as feed_mod, verify_feed, scoring, briefs
from stock_factory.trend_intelligence.events import Event

TODAY = _dt.date.today()


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path / 'state')
    monkeypatch.delenv('ADOBE_STOCK_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    return tmp_path / 'state'


def _valid_feed() -> dict:
    """A real run_scan() feed plus one real brief whose production window
    covers TODAY, so a *valid* feed demonstrably yields calendar
    candidates (otherwise "zero candidates" would prove nothing)."""
    feed = feed_mod.run_scan(today=TODAY)
    ev = Event(country='GB', event_date=TODAY + _dt.timedelta(days=60), local_name='Synthetic Fair',
               english_name='Synthetic Fair', category='national_holiday', source='test', verified_at='')
    b = briefs.build_brief(scoring.score_event(ev, TODAY), 'PHOTO_JPG').to_dict()
    assert b['production_start'] <= TODAY.isoformat() <= b['production_deadline']
    feed['creative_briefs'] = [b] + feed['creative_briefs']
    feed['provenance']['git_sha'] = 'deadbeef'
    return feed


def _write_raw(text: str):
    d = config.STATE_DIR / 'intelligence'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'feed.json').write_text(text)
    (d / 'feed.sha256').write_text(hashlib.sha256(text.encode('utf-8')).hexdigest() + '\n')


def _calendar_candidates():
    return [c for c in trends.select_concepts_detailed(TODAY.isoformat(), 30)
            if 'calendar_opportunity' in c.merged_sources]


def _cli(argv, monkeypatch):
    monkeypatch.setattr('sys.argv', ['verify_feed'] + argv)
    return verify_feed.main()


def test_valid_feed_passes_both_cli_and_consumer(state, monkeypatch):
    feed_mod.write_feed(_valid_feed())
    result = feed_mod.validate_feed()
    assert result.ok, result.problems
    assert _cli([], monkeypatch) == 0
    assert _calendar_candidates(), 'control: a valid feed must produce calendar candidates'


def _mutations():
    def drop(key):
        def f(feed):
            del feed[key]
            return json.dumps(feed)
        return f

    def setv(path, value):
        def f(feed):
            target = feed
            for k in path[:-1]:
                target = target[k]
            target[path[-1]] = value
            return json.dumps(feed)
        return f

    future = (TODAY + _dt.timedelta(days=30)).isoformat()
    stale = (TODAY - _dt.timedelta(days=10)).isoformat()
    return {
        'malformed_json': lambda feed: json.dumps(feed)[:-20],
        'top_level_list': lambda feed: json.dumps([feed]),
        'top_level_null': lambda feed: 'null',
        'missing_creative_briefs': drop('creative_briefs'),
        'missing_scan_date': drop('scan_date'),
        'missing_provenance': drop('provenance'),
        'wrong_type_creative_briefs': setv(['creative_briefs'], 'not-a-list'),
        'wrong_type_schema_version': setv(['schema_version'], '3'),
        'wrong_type_events_indexed': setv(['events_indexed'], 'many'),
        'brief_missing_field': lambda feed: (feed['creative_briefs'][0].pop('production_deadline'), json.dumps(feed))[1],
        'brief_bad_date': setv(['creative_briefs', 0, 'production_start'], '2026-13-45'),
        'bad_scan_date': setv(['scan_date'], 'yesterday'),
        'future_dated_scan_date': setv(['scan_date'], future),
        'stale_scan_date': setv(['scan_date'], stale),
        'unsupported_schema_version': setv(['schema_version'], 99),
        'empty_git_sha': setv(['provenance', 'git_sha'], ''),
        'missing_git_sha': lambda feed: (feed['provenance'].pop('git_sha'), json.dumps(feed))[1],
    }


@pytest.mark.parametrize('mode', sorted(_mutations().keys()))
def test_every_failure_mode_is_rejected_by_cli_and_yields_zero_calendar_candidates(state, monkeypatch, capsys, mode):
    _write_raw(_mutations()[mode](_valid_feed()))
    result = feed_mod.validate_feed()
    assert result.ok is False and result.problems, mode
    assert _cli([], monkeypatch) == 1
    assert _cli(['--fail-soft'], monkeypatch) == 0  # fail-soft: production continues...
    assert _calendar_candidates() == []           # ...but WITHOUT calendar candidates
    # the consumer still produced a full queue from the static bank (no crash)
    assert len(trends.select_concepts_detailed(TODAY.isoformat(), 10)) == 10


def test_checksum_mismatch_rejected_and_yields_zero_calendar_candidates(state, monkeypatch):
    feed_mod.write_feed(_valid_feed())
    p = config.STATE_DIR / 'intelligence' / 'feed.json'
    p.write_text(p.read_text().replace('Synthetic Fair', 'Synthetic Fake', 1))
    result = feed_mod.validate_feed()
    assert not result.ok and any('FEED_INTEGRITY_FAILED' in x for x in result.problems)
    assert _cli([], monkeypatch) == 1
    assert _calendar_candidates() == []


def test_missing_checksum_file_rejected(state, monkeypatch):
    feed_mod.write_feed(_valid_feed())
    (config.STATE_DIR / 'intelligence' / 'feed.sha256').unlink()
    assert not feed_mod.validate_feed().ok
    assert _calendar_candidates() == []


def test_cli_and_consumer_share_the_same_validator(state, monkeypatch):
    calls = []
    real = feed_mod.validate_feed

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(feed_mod, 'validate_feed', spy)
    feed_mod.write_feed(_valid_feed())
    _cli([], monkeypatch)
    trends.select_concepts_detailed(TODAY.isoformat(), 5)
    assert len(calls) == 2


def test_small_clock_skew_is_tolerated(state):
    feed = _valid_feed()
    feed['scan_date'] = (TODAY + _dt.timedelta(days=feed_mod.FEED_MAX_FUTURE_SKEW_DAYS)).isoformat()
    feed_mod.write_feed(feed)
    assert feed_mod.validate_feed().ok


def test_local_scan_records_a_traceable_git_sha(state, monkeypatch):
    for var in ('GITHUB_SHA', 'GITHUB_WORKFLOW', 'GITHUB_RUN_ID'):
        monkeypatch.delenv(var, raising=False)  # simulate a local (non-Actions) run, also when run in CI
    feed = feed_mod.run_scan(today=TODAY)
    sha = feed['provenance']['git_sha']
    assert sha and len(sha) == 40 and all(ch in '0123456789abcdef' for ch in sha)
    assert feed['provenance']['workflow'] == 'local'
