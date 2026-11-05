"""Data model for a single local-pipeline production item, end-to-end
traceable from queue -> generation -> QC -> Drive -> Magnific."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

# Full status lifecycle. An item moves strictly forward on success; any
# stage can instead move it to a '*_failed' or 'blocked_*' state, which
# is terminal for the day's run but eligible for a bounded retry
# (see config.LOCAL_PIPELINE_MAX_RETRIES).
STATUS_LIFECYCLE = [
    'queued',
    'generating',
    'generated',
    'generation_failed',
    'qc_technical_pass',
    'qc_technical_fail',
    'qc_visual_pending',
    'qc_visual_pass',
    'qc_visual_fail',
    'archived',
    'archive_failed',
    'uploaded',
    'upload_failed',
    'blocked_provider_not_implemented',
]

CONTENT_TYPES = ('photo', 'illustration')
PROVIDERS = ('google_flow', 'midjourney', 'manual_inbox', 'fallback')


@dataclass
class ProductionItem:
    item_id: str
    date: str
    content_type: str  # 'photo' | 'illustration'
    category: str
    prompt: str
    title_seed: str
    keyword_seed: list[str]
    target_marketplace: str = 'magnific'
    provider_preference: str = 'google_flow'
    status: str = 'queued'

    # Provenance / generation
    generated_by: str | None = None
    generated_at: str | None = None
    local_raw_path: str | None = None
    local_processed_path: str | None = None
    sha256_raw: str | None = None
    sha256_processed: str | None = None
    dimensions: tuple[int, int] | None = None
    file_size_bytes: int | None = None

    # QC
    qc_technical_pass: bool | None = None
    qc_technical_reason: str | None = None
    qc_visual_status: str = 'not_started'  # not_started | pending_manual | pass | fail
    qc_visual_notes: str | None = None

    # Drive archival
    drive_file_id: str | None = None
    drive_archived_at: str | None = None

    # Magnific upload
    magnific_asset_id: str | None = None
    magnific_uploaded_at: str | None = None

    # Retry / failure tracking
    retry_count: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ProductionItem':
        dims = data.get('dimensions')
        if isinstance(dims, list):
            data = {**data, 'dimensions': tuple(dims)}
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})
