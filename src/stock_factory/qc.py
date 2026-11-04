"""Stage 4: automated technical QC. Visual/content quality screening beyond
this (composition, aesthetics, IP risk) still requires human review --
this module only catches hard technical failures."""
from __future__ import annotations
from io import BytesIO
from PIL import Image
from . import config


def validate_image(data: bytes) -> tuple[bool, str, tuple[int, int]]:
    try:
        with Image.open(BytesIO(data)) as im:
            im.verify()
        with Image.open(BytesIO(data)) as im:
            w, h = im.size
            if min(w, h) < config.MIN_SHORT_EDGE:
                return False, 'short_edge_below_min', (w, h)
            if max(w, h) > config.MAX_LONG_EDGE:
                return False, 'side_above_max', (w, h)
            if w * h < config.MIN_MEGAPIXELS:
                return False, 'under_min_megapixels', (w, h)
            return True, 'pass', (w, h)
    except Exception as exc:
        return False, f'invalid_image:{type(exc).__name__}', (0, 0)
