"""Stage 4: automated technical QC. Visual/content quality screening beyond
this (composition, aesthetics, IP risk) still requires human review --
this module only catches hard technical failures.

Two distinct gates live here, and they are NOT interchangeable:

* validate_image() -- a cheap, early screen on whatever bytes an adapter
  handed back (often pre-upscale, pre-JPEG-encode). It only checks pixel
  dimensions/megapixels. A True here means "worth spending the upscale/
  encode step on", nothing more.

* check_magnific_acceptance() -- the complete submission-acceptance
  contract, run on the FINAL encoded file (post-upscale, post-JPEG-encode).
  This is the only function allowed to declare a file MAGNIFIC_READY.

A prior incident conflated the two: a 2048x2048 Lanczos-upscaled JPEG that
was only 573,116 bytes passed validate_image() (dimensions were fine) and
a verification script reported that as "TECHNICAL_QC=PASS", which was read
as marketplace-ready. It was not -- config.MIN_BYTES=1,500,000 exists
precisely to reject under-detailed upscales like this, but validate_image()
never checked it, and the script never called the function that does.
check_magnific_acceptance() exists so there is exactly one place that can
answer "is this file actually submittable" and it cannot be bypassed by
calling the cheaper pre-filter instead.
"""
from __future__ import annotations
from io import BytesIO
from PIL import Image, ExifTags
from . import config

MAGNIFIC_ACCEPTED_FORMATS = {'JPEG'}

# EXIF GPS IFD pointer tag. Presence of GPS metadata on a stock submission
# is an identifying-location/IP risk, not a technical defect -- but it is
# cheap to catch mechanically, so it belongs in the acceptance contract.
_GPS_IFD_TAG = next((k for k, v in ExifTags.TAGS.items() if v == 'GPSInfo'), 0x8825)


def validate_image(data: bytes) -> tuple[bool, str, tuple[int, int]]:
    """Cheap early screen: pixel dimensions/megapixels only. Does NOT check
    file size, format whitelist, metadata, or duplicates -- see module
    docstring. Never treat a True return here as "ready to submit"."""
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


def check_magnific_acceptance(
    data: bytes,
    digest: str | None = None,
    ledger=None,
) -> tuple[bool, str, dict]:
    """The complete Magnific submission-acceptance contract, applied to the
    FINAL encoded file. Checks, in order: valid/decodable image, accepted
    format, minimum short edge, maximum long edge, minimum megapixels,
    minimum file size (config.MIN_BYTES), absence of GPS EXIF metadata, and
    (if digest/ledger given) duplicate detection. Returns
    (is_ready, reason, details) where details always carries whatever
    dimensions/format/size could be determined, even on failure, so callers
    can log a full picture instead of just a reason code.

    Passing this function, and only this function, is what MAGNIFIC_READY
    means. It must run against the bytes that would actually be uploaded --
    after upscaling and after final JPEG encoding, never against a raw
    generator output or an intermediate buffer.
    """
    details: dict = {'dimensions': (0, 0), 'file_size': len(data), 'format': None}

    try:
        with Image.open(BytesIO(data)) as im:
            im.verify()
        with Image.open(BytesIO(data)) as im:
            w, h = im.size
            fmt = im.format
            exif = im.getexif()
    except Exception as exc:
        return False, f'invalid_image:{type(exc).__name__}', details

    details['dimensions'] = (w, h)
    details['format'] = fmt

    if fmt not in MAGNIFIC_ACCEPTED_FORMATS:
        return False, f'format_not_accepted:{fmt}', details
    if min(w, h) < config.MIN_SHORT_EDGE:
        return False, 'short_edge_below_min', details
    if max(w, h) > config.MAX_LONG_EDGE:
        return False, 'side_above_max', details
    if w * h < config.MIN_MEGAPIXELS:
        return False, 'under_min_megapixels', details
    if len(data) < config.MIN_BYTES:
        return False, 'filesize_below_min', details
    if exif and _GPS_IFD_TAG in exif:
        return False, 'gps_metadata_present', details
    if digest is not None and ledger is not None and ledger.is_duplicate(digest):
        return False, 'duplicate', details

    return True, 'pass', details
