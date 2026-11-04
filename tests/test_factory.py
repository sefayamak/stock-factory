from io import BytesIO
from PIL import Image
from stock_factory.qc import validate_image
from stock_factory.trends import select_concepts
from stock_factory.prompts import build_queue
from stock_factory.pipeline import run as run_pipeline


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
