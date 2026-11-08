"""Measured topic-performance evidence must not fabricate demand or sales."""
import json
from datetime import date, timedelta
from stock_factory.trend_intelligence import performance_signals, scoring, feed
from stock_factory.trend_intelligence.events import Event


TODAY = date(2026, 11, 8)


def _write(tmp_path, payload):
    path = tmp_path / "topic_performance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload(**kwargs):
    return {
        "source": "owner_verified_platform_export",
        "observed_on": TODAY.isoformat(),
        "topics": [{"topic": "Christmas Day", "downloads": 12, "published_asset_days": 1200}],
        **kwargs,
    }


def test_missing_data_does_not_invent_downloads(tmp_path):
    scores, status = performance_signals.load_topic_performance(TODAY, tmp_path / "absent.json")
    assert scores == {} and status["status"] == "unavailable"


def test_valid_data_produces_measured_topic_score(tmp_path):
    scores, status = performance_signals.load_topic_performance(TODAY, _write(tmp_path, _payload()))
    assert scores == {"christmas day": 1.0}
    assert status["status"] == "measured"
    assert status["eligible_topics"] == 1


def test_insufficient_asset_days_remain_unknown(tmp_path):
    payload = _payload(topics=[{"topic": "Christmas Day", "downloads": 1, "published_asset_days": 20}])
    scores, status = performance_signals.load_topic_performance(TODAY, _write(tmp_path, payload))
    assert scores == {} and status["eligible_topics"] == 0


def test_stale_or_unverified_data_is_excluded(tmp_path):
    stale = _payload(observed_on=(TODAY - timedelta(days=60)).isoformat())
    scores, status = performance_signals.load_topic_performance(TODAY, _write(tmp_path, stale))
    assert scores == {} and status["status"] == "invalid"
    unsupported = _payload(source="estimated_revenue")
    scores, status = performance_signals.load_topic_performance(TODAY, _write(tmp_path, unsupported))
    assert scores == {} and status["status"] == "invalid"


def test_negative_and_duplicate_metrics_are_rejected(tmp_path):
    invalid = _payload(topics=[{"topic": "Christmas Day", "downloads": -1, "published_asset_days": 100}])
    assert performance_signals.load_topic_performance(TODAY, _write(tmp_path, invalid))[1]["status"] == "invalid"
    duplicated = _payload(topics=[
        {"topic": "Christmas Day", "downloads": 1, "published_asset_days": 100},
        {"topic": "Christmas Day", "downloads": 2, "published_asset_days": 100},
    ])
    assert performance_signals.load_topic_performance(TODAY, _write(tmp_path, duplicated))[1]["status"] == "invalid"


def test_scoring_only_applies_exact_topic_match():
    event = Event(country="US", event_date=date(2026, 12, 25), local_name="Christmas Day",
                  english_name="Christmas Day", category="national_holiday", source="test", verified_at="")
    measured = scoring.score_event(event, TODAY, historical_download_by_topic={"christmas day": 0.7})
    missing = scoring.score_event(event, TODAY)
    unrelated = scoring.score_event(event, TODAY, historical_download_by_topic={"new year": 0.8})
    assert measured.factors["historical_download_performance"] == 0.7
    assert missing.factors["historical_download_performance"] is None
    assert unrelated.factors["historical_download_performance"] is None


def test_feed_reports_missing_source_without_claiming_performance(tmp_path, monkeypatch):
    monkeypatch.setattr("stock_factory.config.STATE_DIR", tmp_path / "state")
    result = feed.run_scan(today=TODAY, persist_history=False)
    assert result["historical_download_performance"]["status"] == "unavailable"
