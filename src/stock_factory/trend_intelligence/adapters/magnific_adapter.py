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

from .base import TrendAdapter, TrendSignal, SIGNAL_SEARCH_DEMAND
from ... import trend_import


class MagnificManualImportAdapter(TrendAdapter):
    name = 'magnific_manual_import'

    def available(self) -> bool:
        history = trend_import.load_history()
        return bool(history)

    def fetch(self, terms: list[str]) -> list[TrendSignal]:
        history = trend_import.load_history()
        if not history:
            return []
        latest = history[-1]
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
                signal_type=SIGNAL_SEARCH_DEMAND,
                unit='rank' if match.rank is not None else 'volume',
                fetched_at=fetched_at,
                note=f'human-exported snapshot imported_at={latest.imported_at}; '
                     'not live monitoring, only as fresh as the last manual export.',
            ))
        return signals
