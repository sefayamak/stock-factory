"""Magnific Search Trends: confirmed BLOCKED for programmatic access
(contributor.magnific.com/search-trends is a login-gated, JS-rendered SPA
with no static fetch or export API -- see docs/PLATFORM_RULES.md, verified
2026-11-04, re-checked for this feature). No official API, RSS/export
feature, or documented permitted data path exists for this platform as of
this writing.

This adapter does not scrape. It wraps the existing manual-import path
(`stock_factory.trend_import`, already implemented) in the common
TrendAdapter interface, so the feed builder can treat "verified via human
snapshot" uniformly with the other adapters, and so a future adapter that
replaces this one needs no other code changes."""
from __future__ import annotations
from datetime import datetime, timezone

from .base import TrendAdapter, TrendSignal, AdapterStatus, SIGNAL_SEARCH_INTEREST
from ... import trend_import


class MagnificManualImportAdapter(TrendAdapter):
    """Freshness uses the project's EXISTING snapshot staleness policy
    (trend_import.snapshot_is_fresh / config.TREND_STALE_AFTER_DAYS, the
    same one trends.py applies) -- a stale snapshot yields no signals."""
    name = 'magnific_manual_import'

    def available(self) -> bool:
        history = trend_import.load_history()
        return bool(history) and trend_import.snapshot_is_fresh(history[-1])

    def readiness(self) -> AdapterStatus:
        history = trend_import.load_history()
        st = AdapterStatus(adapter=self.name, configured=bool(history), dependency_ready=None, auth_ready=None)
        if not history:
            st.notes = 'no manual Magnific snapshot imported (state/trend_history empty)'
        return st

    def fetch(self, terms: list[str], today=None) -> list[TrendSignal]:
        history = trend_import.load_history()
        if not history:
            return []
        latest = history[-1]
        if not trend_import.snapshot_is_fresh(latest):
            return []  # stale snapshot: never presented as a current signal
        fetched_at = datetime.now(timezone.utc).isoformat()
        by_term = {t.key(): t for t in latest.terms}
        signals = []
        for term in terms:
            match = by_term.get(term.strip().lower())
            if match is None:
                continue
            signals.append(TrendSignal(
                term=match.term, source=self.name, verified=True,
                value=float(match.rank) if match.rank is not None else match.volume,
                signal_type=SIGNAL_SEARCH_INTEREST,
                unit='rank' if match.rank is not None else 'volume',
                fetched_at=fetched_at,
                observation_date=latest.imported_at[:10],
                region='magnific_marketplace_global',
                measure='search_interest',
                fresh=True,
                note=f'human-exported Magnific search-trend snapshot imported_at={latest.imported_at}; '
                     'marketplace search interest, not downloads; not live monitoring.',
            ))
        return signals

    def freshness(self) -> bool | None:
        history = trend_import.load_history()
        return trend_import.snapshot_is_fresh(history[-1]) if history else None
