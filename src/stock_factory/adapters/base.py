"""Adapter interface: anything that can supply raw image bytes + a source tag."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class RawAsset:
    data: bytes
    source: str          # adapter name, e.g. 'manual_inbox', 'gemini'
    origin_name: str      # original filename or identifier
    prompt: str | None = None


class Adapter:
    name = 'base'

    def fetch(self, n: int) -> list[RawAsset]:
        raise NotImplementedError
