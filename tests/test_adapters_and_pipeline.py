import os
import pytest
from io import BytesIO
from PIL import Image
from stock_factory.adapters.manual_inbox_adapter import ManualInboxAdapter
from stock_factory.adapters.flow_adapter import FlowAdapter
from stock_factory import drive_archive
from stock_factory.pipeline import run as run_pipeline


def make_jpeg(w=2100, h=2100, noisy=False):
    b = BytesIO()
    if noisy:
        # High-entropy (os.urandom-style) content makes libjpeg's huffman
        # optimizer pathologically slow in this sandbox. A checkerboard
        # pattern is cheap to encode but still compresses far less than a
        # flat color, which is all this test needs (file size > MIN_BYTES).
        im = Image.new('RGB', (w, h))
        px = im.load()
        for y in range(h):
            shade = (y * 17) % 256
            for x in range(0, w, 2):
                px[x, y] = (shade, (x * 7) % 256, (y * 3) % 256)
    else:
        im = Image.new('RGB', (w, h), 'blue')
    im.save(b, format='JPEG', quality=100, subsampling=0)
    return b.getvalue()


def test_flow_adapter_is_blocked():
    with pytest.raises(NotImplementedError, match='no officially supported'):
        FlowAdapter().fetch(1)


def test_drive_archive_noop_without_credentials(tmp_path):
    f = tmp_path / 'x.jpg'
    f.write_bytes(make_jpeg())
    result = drive_archive.archive(f, 'adobe')
    assert result['archived'] is False
    assert result['reason'] == 'drive_not_configured'


def test_manual_inbox_claims_files(tmp_path):
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    (inbox / 'a.jpg').write_bytes(make_jpeg())
    adapter = ManualInboxAdapter(inbox)
    assets = adapter.fetch(10)
    assert len(assets) == 1
    assert assets[0].source == 'manual_inbox'
    assert not (inbox / 'a.jpg').exists()
    assert (inbox / '_claimed' / 'a.jpg').exists()
    # second fetch finds nothing left to claim
    assert adapter.fetch(10) == []


def test_pipeline_execute_ingests_from_manual_inbox(tmp_path, monkeypatch):
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    (inbox / 'a.jpg').write_bytes(make_jpeg(noisy=True))
    (inbox / 'b.jpg').write_bytes(make_jpeg(1024, 768))  # too small, should fail QC

    monkeypatch.setattr('stock_factory.config.INBOX_DIR', inbox)
    monkeypatch.setattr('stock_factory.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.config.STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr('stock_factory.config.ENABLED_ADAPTERS', ['manual_inbox'])
    monkeypatch.setattr('stock_factory.pipeline.config.INBOX_DIR', inbox)
    monkeypatch.setattr('stock_factory.pipeline.config.OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr('stock_factory.pipeline.config.STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr('stock_factory.pipeline.config.ENABLED_ADAPTERS', ['manual_inbox'])

    summary = run_pipeline('2026-11-04', 10, dry_run=False)
    assert summary['counts']['fetched'] == 2
    assert summary['counts']['qc_passed'] == 1
    assert summary['counts']['qc_rejected'] == 1
    assert summary['counts']['archive_skipped'] == 1
    assert len(list((tmp_path / 'out').glob('*.jpg'))) == 1
