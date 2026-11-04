"""Stage 4: automated technical QC. Visual/content quality screening beyond
this (composition, aesthetics, IP risk) still requires human review --
this module only catches hard technical failures."""
from __future__ import annotations
import base64
import re
from io import BytesIO
from defusedxml import ElementTree as ET  # stdlib xml.etree is XXE-vulnerable; SVGs here may be externally submitted
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


# Real vector drawing elements -- their presence is evidence of actual
# vector geometry (paths/shapes), not a raster image wrapped in SVG/EPS.
_VECTOR_GEOMETRY_TAGS = {
    'path', 'circle', 'rect', 'ellipse', 'polygon', 'polyline', 'line',
    'text', 'g',
}
_NS = '{http://www.w3.org/2000/svg}'


def validate_svg_vector(data: bytes) -> tuple[bool, str]:
    """Rejects a raster image embedded in an SVG wrapper and masquerading
    as a vector (Magnific/Adobe both require genuine vector content, and
    this is an explicit, separate QC gate from validate_image). Accepts
    only an SVG that parses as well-formed XML, contains no <image> tag
    and no base64 raster data URI anywhere in the markup, and contains at
    least one real vector geometry element (path/circle/rect/etc.)."""
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return False, 'not_utf8_text'

    if 'data:image' in text or re.search(r'base64,', text):
        return False, 'embedded_raster_data_uri'

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return False, f'invalid_svg_xml:{exc}'

    root_tag = root.tag.replace(_NS, '')
    if root_tag != 'svg':
        return False, 'not_an_svg_root_element'

    has_raster_tag = False
    has_vector_geometry = False
    for el in root.iter():
        tag = el.tag.replace(_NS, '')
        if tag == 'image':
            has_raster_tag = True
        if tag in _VECTOR_GEOMETRY_TAGS:
            has_vector_geometry = True

    if has_raster_tag:
        return False, 'embedded_raster_image_tag'
    if not has_vector_geometry:
        return False, 'no_vector_geometry_found'
    return True, 'pass'
