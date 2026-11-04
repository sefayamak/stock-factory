import csv
from io import BytesIO
from PIL import Image
from stock_factory.qc import validate_image
from stock_factory.trends import select_concepts
from stock_factory.prompts import build_queue
from stock_factory.pipeline import run as run_pipeline, _select_queue


def test_small_short_edge_rejected():
    b = BytesIO()
    Image.new('RGB', (2752, 1536), 'blue').save(b, format='JPEG')
    ok, reason, _ = validate_image(b.getvalue())
    assert not ok and reason == 'short_edge_below_min'


def test_four_k_pass():
    b = BytesIO()
    Image.new('RGB', (4096, 3072), 'blue').save(b, format='JPEG')
    assert validate_image(b.getvalue())[0]


def test_deterministic_concepts():
    assert select_concepts('2026-11-04', 10) == select_concepts('2026-11-04', 10)


def test_queue_size_matches_target():
    queue = build_queue('2026-11-04', 120)
    assert len(queue) == 120
    assert len({q.job_id for q in queue}) == 120


def test_dry_run_builds_queue_without_fetching(tmp_path, monkeypatch):
    monkeypatch.setattr('stock_factory.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr('stock_factory.pipeline.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.pipeline.config.STATE_DIR', tmp_path / 'state')
    summary = run_pipeline('2026-11-04', 100, dry_run=True)
    assert summary['counts']['fetched'] == 0
    assert len(list((tmp_path / 'out').glob('*.jpg'))) == 0
    assert (tmp_path / 'out' / 'submission.csv').exists()


def test_submission_csv_has_ai_disclosure_column(tmp_path, monkeypatch):
    import os
    inbox_dir = tmp_path / 'inbox'
    inbox_dir.mkdir()
    size = (2560, 2048)  # above MIN_SHORT_EDGE/MIN_MEGAPIXELS with room to spare
    noise = os.urandom(size[0] * size[1] * 3)
    im = Image.frombytes('RGB', size, noise)
    b = BytesIO()
    im.save(b, format='JPEG', quality=95)
    data = b.getvalue()
    assert len(data) >= 1_500_000, f'fixture too small: {len(data)} bytes'
    (inbox_dir / 'asset-001.jpg').write_bytes(data)

    monkeypatch.setattr('stock_factory.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr('stock_factory.config.INBOX_DIR', inbox_dir)
    monkeypatch.setattr('stock_factory.pipeline.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.pipeline.config.STATE_DIR', tmp_path / 'state')

    run_pipeline('2026-11-04', 1, dry_run=False)

    csv_path = tmp_path / 'out' / 'submission.csv'
    assert csv_path.exists()
    with csv_path.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert '_ai_generated' in rows[0].keys()
    accepted = [r for r in rows if r['status'] == 'PENDING_HUMAN_VISUAL_QC']
    assert accepted, 'expected at least one accepted asset in the CSV'
    assert all(r['_ai_generated'] == 'yes' for r in accepted)


def test_select_queue_defaults_to_magnific_only(monkeypatch):
    monkeypatch.setattr('stock_factory.pipeline.config.ADOBE_MARKETPLACE_ACTIVE', False)
    monkeypatch.setattr('stock_factory.pipeline.config.MAGNIFIC_MARKETPLACE_ACTIVE', True)
    assert _select_queue(1) == 'magnific'
    assert _select_queue(2) == 'magnific'
    assert _select_queue(100) == 'magnific'


def test_select_queue_adobe_disabled_never_routes_to_adobe(monkeypatch):
    monkeypatch.setattr('stock_factory.pipeline.config.ADOBE_MARKETPLACE_ACTIVE', False)
    monkeypatch.setattr('stock_factory.pipeline.config.MAGNIFIC_MARKETPLACE_ACTIVE', True)
    for n in range(50):
        assert _select_queue(n) != 'adobe'


def test_select_queue_no_active_marketplace_returns_none(monkeypatch):
    monkeypatch.setattr('stock_factory.pipeline.config.ADOBE_MARKETPLACE_ACTIVE', False)
    monkeypatch.setattr('stock_factory.pipeline.config.MAGNIFIC_MARKETPLACE_ACTIVE', False)
    assert _select_queue(1) is None


def test_select_queue_both_active_alternates(monkeypatch):
    monkeypatch.setattr('stock_factory.pipeline.config.ADOBE_MARKETPLACE_ACTIVE', True)
    monkeypatch.setattr('stock_factory.pipeline.config.MAGNIFIC_MARKETPLACE_ACTIVE', True)
    assert _select_queue(1) == 'adobe'
    assert _select_queue(2) == 'magnific'


def test_pipeline_run_with_magnific_only_never_dispatches_adobe(tmp_path, monkeypatch):
    import os
    inbox_dir = tmp_path / 'inbox'
    inbox_dir.mkdir()
    size = (2560, 2048)
    noise = os.urandom(size[0] * size[1] * 3)
    for i in range(3):
        im = Image.frombytes('RGB', size, noise)
        b = BytesIO()
        im.save(b, format='JPEG', quality=95)
        (inbox_dir / f'asset-{i:03d}.jpg').write_bytes(b.getvalue())

    monkeypatch.setattr('stock_factory.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr('stock_factory.config.INBOX_DIR', inbox_dir)
    monkeypatch.setattr('stock_factory.pipeline.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.pipeline.config.STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr('stock_factory.pipeline.config.ADOBE_MARKETPLACE_ACTIVE', False)
    monkeypatch.setattr('stock_factory.pipeline.config.MAGNIFIC_MARKETPLACE_ACTIVE', True)

    run_pipeline('2026-11-04', 3, dry_run=False)

    csv_path = tmp_path / 'out' / 'submission.csv'
    with csv_path.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    accepted = [r for r in rows if r['status'] == 'PENDING_HUMAN_VISUAL_QC']
    assert accepted, 'expected at least one accepted asset'
    assert all(r['drive_queue'] != 'adobe' for r in accepted)
    assert all(r['drive_queue'] == 'magnific' for r in accepted)
