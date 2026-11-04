"""Common interface every trend-demand adapter implements, so a real
integration can be dropped in later without touching the scoring/feed code.

`signal_type` is load-bearing, not decorative: a catalog result count
(supply/competition) must never be treated as search demand just because
it came from a "verified" live API call. Every adapter below must set it
correctly, and `feed._collect_signals` routes by it, not by adapter name."""
from __future__ import annotations
from dataclasses import dataclass

# What the signal actually measures. Keep these four distinct -- conflating
# any two of them (e.g. Adobe's catalog nb_results into search demand) is
# exactly the defect this module exists to prevent.
SIGNAL_SEARCH_DEMAND = 'verified_search_demand'           # real search/interest volume or rank
SIGNAL_CATALOG_SUPPLY = 'catalog_supply'                   # existing-content/competition count
SIGNAL_CALENDAR_PREDICTED_DEMAND = 'calendar_predicted_demand'  # heuristic, not from any adapter
SIGNAL_HISTORICAL_DOWNLOAD_PERFORMANCE = 'historical_download_performance'  # past acceptance/download record


@dataclass
class TrendSignal:
    term: str
    source: str            # 'adobe_stock_search_api' | 'google_trends_bigquery' | 'magnific_manual_import' | ...
    verified: bool          # True only for a real, live-queried/official-dataset value
    signal_type: str = SIGNAL_SEARCH_DEMAND  # one of the SIGNAL_* constants above
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
