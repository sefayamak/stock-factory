"""Common interface every trend-demand adapter implements, so a real
integration can be dropped in later without touching the scoring/feed code."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class TrendSignal:
    term: str
    source: str            # 'adobe_stock_search_api' | 'google_trends_bigquery' | 'magnific_manual_import' | ...
    verified: bool          # True only for a real, live-queried/official-dataset value
    value: float | None = None   # meaning depends on source (e.g. result count, interest index)
    unit: str = ''
    fetched_at: str = ''
    note: str = ''


class TrendAdapter:
    name: str = 'base'

    def available(self) -> bool:
        """Whether this adapter can run right now (credentials/config present)."""
        raise NotImplementedError

    def fetch(self, terms: list[str]) -> list[TrendSignal]:
        raise NotImplementedError
