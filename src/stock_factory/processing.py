"""Stage 5: JPEG preparation, metadata, and duplicate protection."""
from __future__ import annotations
import hashlib
import json
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps
from . import config


def convert_jpeg(raw: bytes) -> bytes:
    with Image.open(BytesIO(raw)) as src:
        im = ImageOps.exif_transpose(src).convert('RGB')
        output = BytesIO()
        icc = src.info.get('icc_profile', b'')
        im.save(output, 'JPEG', quality=config.JPEG_QUALITY, subsampling=0, optimize=True, icc_profile=icc)
        return output.getvalue()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DuplicateLedger:
    """Persistent sha256 ledger so a hash seen on any past day is rejected,
    not just within a single run."""

    def __init__(self, state_dir: Path):
        self.path = state_dir / 'seen_hashes.json'
        state_dir.mkdir(parents=True, exist_ok=True)
        self.seen: set[str] = set(json.loads(self.path.read_text())) if self.path.exists() else set()

    def is_duplicate(self, digest: str) -> bool:
        return digest in self.seen

    def record(self, digest: str) -> None:
        self.seen.add(digest)

    def save(self) -> None:
        self.path.write_text(json.dumps(sorted(self.seen)))
