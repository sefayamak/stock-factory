"""Common interface every trend-demand adapter implements, so a real
integration can be dropped in later without touching the scoring/feed code.

`signal_type` is load-bearing, not decorative: a catalog result count
(supply/competition) must never be treated as search demand just because
it came from a "verified" live API call. Every adapter below must set it
correctly, and `feed._collect_signals` routes by it, not by adapter name."""
from __future__ import annotations
from dataclasses import dataclass, asdict

# What the signal actually measures. Keep these four distinct -- conflating
# any two of them (e.g. Adobe's catalog nb_results into search demand) is
# exactly the defect this module exists to prevent.
#
# SEARCH INTEREST is what Google Trends / Magnific search-trend ranks
# measure: people searching for a term. It is NOT stock-buyer download or
# purchase demand, and is labeled accordingly (value 'verified_search_interest').
SIGNAL_SEARCH_INTEREST = 'verified_search_interest'       # real search-interest rank/index, observed recently
SIGNAL_SEARCH_DEMAND = SIGNAL_SEARCH_INTEREST              # backward-compatible alias (same value)
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
    fetched_at: str = ''          # when WE retrieved it
    note: str = ''
    observation_date: str = ''    # when the SOURCE observed it (e.g. Google Trends week) -- never fetched_at
    region: str = ''              # geography the observation covers
    measure: str = ''             # e.g. 'search_interest', 'catalog_result_count'
    fresh: bool | None = None     # observation recent enough to count as current (None = not applicable)


@dataclass
class AdapterStatus:
    """Separates every distinct reason an adapter may or may not have
    contributed data. `available` is derived, never set by hand: True only
    if configured, dependency-ready, not auth-failed, fetched successfully,
    fresh (if freshness applies), with no error."""
    adapter: str
    configured: bool = False
    dependency_ready: bool | None = None   # None = no optional dependency involved
    auth_ready: bool | None = None         # None = not checkable before a real call
    fetch_attempted: bool = False
    fetch_succeeded: bool = False
    fresh: bool | None = None
    signal_count: int = 0
    error: str | None = None
    notes: str = ''

    @property
    def available(self) -> bool:
        return (self.configured and self.dependency_ready is not False and self.auth_ready is not False
                and self.fetch_succeeded and self.fresh is not False and self.error is None)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['available'] = self.available
        return d


class TrendAdapter:
    name: str = 'base'

    def available(self) -> bool:
        """Whether this adapter can run right now (credentials/config present)."""
        raise NotImplementedError

    def readiness(self) -> AdapterStatus:
        """Pre-fetch status: configured / dependency_ready. Subclasses
        override to report these separately; default derives from
        available()."""
        ok = bool(self.available())
        return AdapterStatus(adapter=self.name, configured=ok)

    def fetch(self, terms: list[str], today=None) -> list[TrendSignal]:
        raise NotImplementedError
