"""Ingests images a human already generated/downloaded (e.g. from Flow) into INBOX_DIR.

This is the legitimate path for using a Google Flow/AI Pro subscription: the
account owner generates through the real, authenticated Flow web UI and
downloads the files themselves. No login, CAPTCHA, or rate limit is bypassed.
A file is claimed (moved to INBOX_DIR/_claimed) once read, so a run never
double-ingests the same file.
"""
from __future__ import annotations
from pathlib import Path
from .base import Adapter, RawAsset

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}


class ManualInboxAdapter(Adapter):
    name = 'manual_inbox'

    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir
        self.claimed_dir = inbox_dir / '_claimed'

    def fetch(self, n: int) -> list[RawAsset]:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.claimed_dir.mkdir(parents=True, exist_ok=True)
        candidates = sorted(
            p for p in self.inbox_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        )
        assets = []
        for path in candidates[:n]:
            data = path.read_bytes()
            assets.append(RawAsset(data=data, source=self.name, origin_name=path.name))
            path.rename(self.claimed_dir / path.name)
        return assets
