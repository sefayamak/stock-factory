"""The dated, published public-market snapshot is never evergreen sales data."""
from datetime import date
from pathlib import Path
from stock_factory import config, trends
from stock_factory.trend_intelligence import market_briefs


def test_packaged_market_research_is_fresh_on_research_day(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "empty_state")
    rows, status = market_briefs.load_market_briefs("2026-11-08")
    assert status["status"] == "loaded"
    assert len(rows) == 10
    assert all(x["source_url"].startswith("https://") for x in rows)
    assert all(x["platform"] == "magnific" and x["media"] == "photo" for x in rows)
    assert all(x["signal_type"] != "observed_downloads" for x in rows)


def test_packaged_snapshot_expires_instead_of_faking_live_trends(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "empty_state")
    rows, status = market_briefs.load_market_briefs("2026-12-01")
    assert rows == [] and status["eligible"] == 0


def test_public_shutterstock_growth_never_becomes_sales():
    path = Path(market_briefs.__file__).with_name("public_market_seed.json")
    import json
    items = json.loads(path.read_text())["briefs"]
    assert all("revenue" not in x and "downloads" not in x for x in items)
    assert all(x["signal_type"] in {"verified_search_interest", "editorial_hypothesis"} for x in items)


def test_new_sectors_reach_magnific_photo_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "empty_state")
    monkeypatch.setattr("stock_factory.trends._latest_fresh_snapshot", lambda: None)
    monkeypatch.setattr("stock_factory.trends._calendar_opportunity_concepts", lambda day: [])
    result = trends.select_concepts_detailed("2026-11-08", 50)
    market = [x for x in result if x.source == "market_brief"]
    assert len(market) == 10
    assert all(x.market_source_url for x in market)
    assert len({x.scene for x in result}) == len(result)
