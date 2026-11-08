"""Market scout handoff: dated, platform-separated, fail-closed."""
import json
from datetime import date
from stock_factory.trend_intelligence import market_briefs
from stock_factory import trends, config
from stock_factory.prompts import build_queue


def _brief(category="urban cooling", platform="magnific", media="photo",
           observed_on="2026-11-08", scene="Aerial view of reflective city roofs"):
    return {"category": category, "platform": platform, "media": media,
            "scene": scene, "observed_on": observed_on,
            "signal_type": "editorial_hypothesis",
            "source_url": "https://example.org/urban-cooling-report"}


def _save(tmp_path, rows, schema_version=1):
    p = tmp_path / "market_briefs.json"
    p.write_text(json.dumps({"schema_version": schema_version, "briefs": rows}))
    return p


def test_missing_or_bad_version_fails_closed(tmp_path):
    assert market_briefs.load_market_briefs("2026-11-08", path=tmp_path/"missing.json")[0] == []
    r, state = market_briefs.load_market_briefs("2026-11-08", path=_save(tmp_path, [], 5))
    assert r == [] and state["status"] == "invalid"


def test_filters_media_platform_and_stale(tmp_path):
    rows = [_brief(), _brief(category="isolated", platform="adobe"),
            _brief(category="graphic", media="vector"),
            _brief(category="stale", observed_on="2026-10-01")]
    result, state = market_briefs.load_market_briefs("2026-11-08", path=_save(tmp_path, rows))
    assert len(result) == 1 and result[0]["category"] == "urban cooling"
    assert state["eligible"] == 1


def test_invalid_source_does_not_enter_queue(tmp_path):
    row = _brief()
    row["source_url"] = "no verified URL"
    result, status = market_briefs.load_market_briefs("2026-11-08", path=_save(tmp_path, [row]))
    assert result == [] and status["status"] == "invalid"


def test_deduplicates_identical_market_scenes(tmp_path):
    result, _ = market_briefs.load_market_briefs("2026-11-08",
        path=_save(tmp_path, [_brief(), _brief()]))
    assert len(result) == 1


def test_market_brief_reaches_queue_with_source_url(tmp_path, monkeypatch):
    state = tmp_path / "state"
    folder = state / "intelligence"
    folder.mkdir(parents=True)
    _save(folder, [_brief()])
    monkeypatch.setattr(config, "STATE_DIR", state)
    monkeypatch.setattr("stock_factory.trends._latest_fresh_snapshot", lambda: None)
    monkeypatch.setattr("stock_factory.trends._calendar_opportunity_concepts", lambda day: [])
    result = build_queue("2026-11-08", 30)
    chosen = [x for x in result if x.source == "market_brief"]
    assert len(chosen) == 1
    assert chosen[0].market_source_url.startswith("https://")
    assert len(set(x.scene for x in result)) == len(result)
