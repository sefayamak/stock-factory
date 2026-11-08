"""A short opportunity queue must never be padded with repeated scenes."""
import pytest
from stock_factory import trends
from stock_factory.prompts import build_queue


@pytest.fixture(autouse=True)
def isolate_market_research(monkeypatch):
    # This legacy regression covers static fallback when *no* external
    # research is present. Public research is tested in its own suite.
    monkeypatch.setattr(
        "stock_factory.trend_intelligence.market_briefs.load_market_briefs",
        lambda *args, **kwargs: ([], {"status": "unavailable"}))


def test_static_fallback_does_not_repeat_scenes(tmp_path, monkeypatch):
    monkeypatch.setattr("stock_factory.config.STATE_DIR", tmp_path / "state")
    concepts = trends.select_concepts_detailed("2026-11-08", 200)
    static = [c for c in concepts if c.source == "static_topic_bank"]
    assert len(static) == len(trends.TOPICS)
    assert len({c.scene for c in static}) == len(static)
    assert len(concepts) == len(trends.TOPICS)


def test_small_request_preserves_existing_behavior(tmp_path, monkeypatch):
    monkeypatch.setattr("stock_factory.config.STATE_DIR", tmp_path / "state")
    assert len(trends.select_concepts_detailed("2026-11-08", 5)) == 5


def test_queue_reports_actual_opportunity_count(tmp_path, monkeypatch):
    monkeypatch.setattr("stock_factory.config.STATE_DIR", tmp_path / "state")
    queue = build_queue("2026-11-08", 100)
    assert len(queue) == len(trends.TOPICS)
    assert len({item.scene for item in queue}) == len(queue)
