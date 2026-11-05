from io import BytesIO
from PIL import Image
from stock_factory import upscale, qc


def _make_jpeg(size):
    im = Image.new('RGB', size, color=(120, 60, 200))
    buf = BytesIO()
    im.save(buf, 'JPEG', quality=90)
    return buf.getvalue()


def test_lanczos_upscale_doubles_dimensions():
    original = _make_jpeg((1024, 1024))
    out = upscale.lanczos_upscale(original, factor=2)
    with Image.open(BytesIO(out)) as im:
        assert im.size == (2048, 2048)
        assert im.format == 'JPEG'


def test_lanczos_upscale_factor_one_is_noop_dimension():
    original = _make_jpeg((512, 512))
    out = upscale.lanczos_upscale(original, factor=1)
    with Image.open(BytesIO(out)) as im:
        assert im.size == (512, 512)


def test_lanczos_upscale_rejects_invalid_factor():
    original = _make_jpeg((64, 64))
    try:
        upscale.lanczos_upscale(original, factor=0)
        assert False, 'expected ValueError'
    except ValueError:
        pass


def test_upscaled_1024_passes_min_short_edge_qc():
    original = _make_jpeg((1024, 1024))
    out = upscale.lanczos_upscale(original, factor=2)
    qc_pass, reason, (w, h) = qc.validate_image(out)
    assert (w, h) == (2048, 2048)
    assert qc_pass, reason


def test_low_detail_upscale_passes_dimension_prescreen_but_is_not_magnific_ready():
    """Regression test for the incident where a 573,116-byte 2048x2048
    Lanczos upscale was reported TECHNICAL_QC=PASS and read as submission
    ready. A flat-color source has almost no detail for Lanczos to spread
    across the larger canvas, so its upscale re-encodes far below
    config.MIN_BYTES (1,500,000) -- exactly the failure mode that slipped
    through before check_magnific_acceptance() existed."""
    original = _make_jpeg((1024, 1024))  # flat color -> compresses tiny
    out = upscale.lanczos_upscale(original, factor=2)

    with Image.open(BytesIO(out)) as im:
        assert im.size == (2048, 2048)
    assert len(out) < 1_500_000, (
        f'test fixture must reproduce the under-detailed-upscale case; got {len(out)} bytes'
    )

    # Gate 1 (dimension pre-screen) passes -- this is the trap.
    prescreen_pass, _reason, _dims = qc.validate_image(out)
    assert prescreen_pass

    # Gate 2 (the full acceptance contract) must NOT be fooled by Gate 1.
    ready, reason, details = qc.check_magnific_acceptance(out)
    assert ready is False
    assert reason == 'filesize_below_min'
    assert details['file_size'] == len(out)
    assert details['dimensions'] == (2048, 2048)


def test_magnific_acceptance_passes_for_sufficiently_detailed_large_jpeg():
    """Sanity check that check_magnific_acceptance() is not simply always
    False: a genuinely large, high-entropy, correctly-sized JPEG passes."""
    im = Image.new('RGB', (2048, 2048))
    px = im.load()
    for y in range(2048):
        shade = (y * 17) % 256
        for x in range(0, 2048, 2):
            px[x, y] = (shade, (x * 7) % 256, (y * 3) % 256)
    buf = BytesIO()
    im.save(buf, 'JPEG', quality=100, subsampling=0)
    data = buf.getvalue()
    assert len(data) >= 1_500_000, 'fixture must actually clear MIN_BYTES to be a useful sanity check'

    ready, reason, details = qc.check_magnific_acceptance(data)
    assert ready is True, reason
    assert details['format'] == 'JPEG'


def test_magnific_acceptance_rejects_duplicate():
    class _StubLedger:
        def is_duplicate(self, digest):
            return True

    im = Image.new('RGB', (2048, 2048))
    px = im.load()
    for y in range(2048):
        shade = (y * 17) % 256
        for x in range(0, 2048, 2):
            px[x, y] = (shade, (x * 7) % 256, (y * 3) % 256)
    buf = BytesIO()
    im.save(buf, 'JPEG', quality=100, subsampling=0)
    data = buf.getvalue()

    ready, reason, _details = qc.check_magnific_acceptance(data, digest='anything', ledger=_StubLedger())
    assert ready is False
    assert reason == 'duplicate'
