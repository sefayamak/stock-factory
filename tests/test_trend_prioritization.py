import json
from datetime import datetime, timedelta, timezone

from stock_factory import trend_import, trends
from stock_factory.prompts import build_queue


def _write_history_entry(state_dir, imported_at: str, terms: list[dict]):
    hist_dir = state_dir / 'trend_history'
    hist_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        'imported_at': imported_at,
        'source_file': 'manual.json',
        'sha256': f'fake-{imported_at}',
        'terms': terms,
    }
    with (hist_dir / 'index.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')


def test_no_snapshot_falls_back_to_static_bank(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    concepts = trends.select_concepts_detailed('2026-11-04', 5)
    assert len(concepts) == 5
    assert all(c.source == 'static_topic_bank' for c in concepts)
    assert all(c.trend_term is None for c in concepts)


def test_fresh_snapshot_prioritizes_trend_terms_with_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    state_dir = tmp_path / 'state'
    now = datetime.now(timezone.utc).isoformat()
    _write_history_entry(state_dir, now, [
        {'term': 'cozy harvest', 'category': 'seasonal', 'rank': 1, 'volume': 500},
        {'term': 'minimalist desk', 'category': 'workspace', 'rank': 2, 'volume': 300},
    ])

    concepts = trends.select_concepts_detailed('2026-11-04', 5)
    trend_concepts = [c for c in concepts if c.source == 'trend_snapshot']
    static_concepts = [c for c in concepts if c.source == 'static_topic_bank']

    assert len(concepts) == 5
    assert {c.trend_term for c in trend_concepts} == {'cozy harvest', 'minimalist desk'}
    assert len(static_concepts) == 3
    for c in trend_concepts:
        assert c.trend_snapshot_imported_at == now
        assert c.category in ('seasonal', 'workspace')


def test_stale_snapshot_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr('stock_factory.config.TREND_STALE_AFTER_DAYS', 14)
    state_dir = tmp_path / 'state'
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _write_history_entry(state_dir, old, [{'term': 'ancient trend', 'rank': 1}])

    concepts = trends.select_concepts_detailed('2026-11-04', 5)
    assert all(c.source == 'static_topic_bank' for c in concepts)
    assert all(c.trend_term != 'ancient trend' for c in concepts)


def test_rising_terms_rank_above_falling_terms(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    state_dir = tmp_path / 'state'
    t1 = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    t2 = datetime.now(timezone.utc).isoformat()
    _write_history_entry(state_dir, t1, [
        {'term': 'falling term', 'rank': 1, 'volume': 100},
        {'term': 'rising term', 'rank': 5, 'volume': 10},
    ])
    _write_history_entry(state_dir, t2, [
        {'term': 'falling term', 'rank': 5, 'volume': 80},
        {'term': 'rising term', 'rank': 1, 'volume': 90},
    ])

    concepts = trends.select_concepts_detailed('2026-11-04', 2)
    assert concepts[0].trend_term == 'rising term'
    assert concepts[0].trend_status == 'rising'
    assert concepts[1].trend_term == 'falling term'
    assert concepts[1].trend_status == 'falling'


def test_select_concepts_backward_compatible_shape(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    out = trends.select_concepts('2026-11-04', 3)
    assert all(isinstance(t, tuple) and len(t) == 2 for t in out)


def test_build_queue_carries_provenance_through(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    state_dir = tmp_path / 'state'
    now = datetime.now(timezone.utc).isoformat()
    _write_history_entry(state_dir, now, [{'term': 'trending scene', 'category': 'trending', 'rank': 1}])

    queue = build_queue('2026-11-04', 3)
    trend_items = [q for q in queue if q.source == 'trend_snapshot']
    assert len(trend_items) == 1
    assert trend_items[0].trend_term == 'trending scene'
    assert trend_items[0].trend_snapshot_imported_at == now
    assert all(q.source == 'static_topic_bank' for q in queue if q not in trend_items)


def test_dry_run_csv_includes_trend_provenance_columns(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr('stock_factory.pipeline.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.pipeline.config.STATE_DIR', tmp_path / 'state')
    state_dir = tmp_path / 'state'
    now = datetime.now(timezone.utc).isoformat()
    _write_history_entry(state_dir, now, [{'term': 'dry run trend', 'category': 'trending', 'rank': 1}])

    from stock_factory.pipeline import run as run_pipeline
    run_pipeline('2026-11-04', 3, dry_run=True)

    import csv
    with (tmp_path / 'out' / 'submission.csv').open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert 'trend_source' in rows[0]
    trend_rows = [r for r in rows if r['trend_source'] == 'trend_snapshot']
    assert len(trend_rows) == 1
    assert trend_rows[0]['trend_term'] == 'dry run trend'
