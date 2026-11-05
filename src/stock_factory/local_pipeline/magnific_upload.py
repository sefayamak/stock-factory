"""Phase 4 target, NOT YET IMPLEMENTED: Magnific upload automation.

Same execution-location constraint as the generation providers (see
providers/base.py) -- Magnific has no public upload API referenced
anywhere in this repo (see docs/PLATFORM_RULES.md), so this will also be
browser automation against the operator's authenticated Magnific session.
"""
from __future__ import annotations
from dataclasses import dataclass


class UploadUnavailable(Exception):
    pass


@dataclass
class UploadResult:
    uploaded: bool
    magnific_asset_id: str | None
    reason: str


def upload(local_path: str, title: str, keywords: list[str]) -> UploadResult:
    raise UploadUnavailable(
        'magnific_upload is not yet implemented (Phase 4). Run on the '
        'operator machine and implement the browser flow against the '
        'live Magnific upload UI there.'
    )
