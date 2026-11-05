"""Stage 4.5: resolution upscaling for generator outputs below Magnific's
MIN_SHORT_EDGE (src/stock_factory/qc.py).

Why Pillow/Lanczos and not a GAN/diffusion upscaler: @cf/black-forest-labs/
flux-1-schnell on Cloudflare Workers AI exposes no width/height parameter
(see adapters/cloudflare_flux_adapter.py) and is fixed at 1024x1024 native
output. A paid upscaling API (Magnific's own paid tier, Replicate, Topaz,
etc.) is explicitly out of scope for this free-tier pipeline. Pillow's
Lanczos resampling is already a hard dependency (requirements.txt), runs
locally with no network call, has no usage cost, and is clearly licensed
for commercial use (PIL/Pillow, HPND-derived license). It cannot invent
detail a generative upscaler would, so it is a deterministic, inspectable
floor -- not a substitute for a real super-resolution model if one is
later added as a paid/local option.
"""
from __future__ import annotations
from io import BytesIO
from PIL import Image
from . import config


def lanczos_upscale(data: bytes, factor: int = 2) -> bytes:
    """Upscale JPEG/PNG bytes by an integer factor using Lanczos resampling.
    Re-encodes as JPEG at config.JPEG_QUALITY -- no artificial padding is
    added; file size is whatever the real re-encoded pixel data produces."""
    if factor < 1:
        raise ValueError(f'factor must be >= 1, got {factor}')

    with Image.open(BytesIO(data)) as im:
        im = im.convert('RGB')
        w, h = im.size
        target = (w * factor, h * factor)
        upscaled = im.resize(target, Image.Resampling.LANCZOS)

        output = BytesIO()
        upscaled.save(output, 'JPEG', quality=config.JPEG_QUALITY, subsampling=0, optimize=True)
        return output.getvalue()
