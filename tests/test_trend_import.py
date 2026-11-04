import json

from stock_factory import trend_import


def _write_snapshot(path, terms):
    path.write_text(json.dumps(terms), encoding='utf-8')


def test_import_snapshot_records_history(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    snap = tmp_path / 'snap1.json'
    _write_snapshot(snap, [{'term': 'autumn cozy', 'category': 'seasonal', 'rank': 1, 'volume': 100}])

    result = trend_import.import_snapshot(snap)
    assert result['imported'] is True
    assert result['term_count'] == 1

    history = trend_import.load_history()
    assert len(history) == 1
    assert history[0].terms[0].term == 'autumn cozy'


def test_duplicate_snapshot_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    snap = tmp_path / 'snap1.json'
    _write_snapshot(snap, [{'term': 'x', 'rank': 1}])

    first = trend_import.import_snapshot(snap)
    second = trend_import.import_snapshot(snap)

    assert first['imported'] is True
    assert second['imported'] is False
    assert second['reason'] == 'duplicate_snapshot'
    assert len(trend_import.load_history()) == 1


def test_csv_snapshot_parses(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    snap = tmp_path / 'snap.csv'
    snap.write_text('term,category,rank,volume\nminimalist home,lifestyle,2,55\n', encoding='utf-8')

    result = trend_import.import_snapshot(snap)
    assert result['imported'] is True
    history = trend_import.load_history()
    assert history[0].terms[0].term == 'minimalist home'
    assert history[0].terms[0].rank == 2


def test_score_trend_changes_detects_new_rising_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    snap1 = tmp_path / 'snap1.json'
    snap2 = tmp_path / 'snap2.json'
    _write_snapshot(snap1, [
        {'term': 'cozy autumn', 'rank': 1, 'volume': 100},
        {'term': 'old trend', 'rank': 2, 'volume': 40},
    ])
    _write_snapshot(snap2, [
        {'term': 'cozy autumn', 'rank': 3, 'volume': 90},   # falling
        {'term': 'brand new term', 'rank': 1, 'volume': 120},  # new
    ])
    trend_import.import_snapshot(snap1)
    trend_import.import_snapshot(snap2)

    report = trend_import.latest_trend_report()
    assert report is not None
    statuses = {c['term']: c['status'] for c in report['changes']}
    assert statuses['brand new term'] == 'new'
    assert statuses['cozy autumn'] == 'falling'
    assert statuses['old trend'] == 'dropped'


def test_latest_trend_report_none_with_fewer_than_two_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    assert trend_import.latest_trend_report() is None

    snap = tmp_path / 'snap1.json'
    _write_snapshot(snap, [{'term': 'x', 'rank': 1}])
    trend_import.import_snapshot(snap)
    assert trend_import.latest_trend_report() is None


def test_import_pending_snapshots_claims_files(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    snapshot_dir = tmp_path / 'trend_inbox'
    snapshot_dir.mkdir()
    _write_snapshot(snapshot_dir / 'a.json', [{'term': 'x', 'rank': 1}])

    results = trend_import.import_pending_snapshots(snapshot_dir)
    assert len(results) == 1
    assert results[0]['imported'] is True
    assert not (snapshot_dir / 'a.json').exists()
    assert (snapshot_dir / '_claimed' / 'a.json').exists()

    # A second run with nothing new pending claims nothing further.
    assert trend_import.import_pending_snapshots(snapshot_dir) == []
