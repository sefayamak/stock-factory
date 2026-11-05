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
