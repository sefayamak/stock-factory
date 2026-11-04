"""Adobe Stock: the only genuinely-accessible-without-contributor-login
piece of this platform is the public Adobe Stock Search API
(https://developer.adobe.com/stock/docs/) -- a free, self-serve API key
from the Adobe Developer Console, no contributor OAuth needed. It returns
`nb_results` (catalog result count) per search term, which is a real,
permitted competition/supply signal (not a sales/search-volume figure).

Adobe Stock *Contributor Insights* (per-account trend dashboard) is a
different, OAuth-gated, contributor-only surface -- that one is NOT
implemented here (would need the account owner's contributor OAuth
tokens, which this project does not have). Only the public search-count
signal is wired up.

Real call only happens when ADOBE_STOCK_API_KEY is set; otherwise
`available()` is False and callers fall back to manual import /
calendar-based prediction, never a fabricated number.
"""
from __future__ import annotations
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from .base import TrendAdapter, TrendSignal, SIGNAL_CATALOG_SUPPLY

API_URL = 'https://stock.adobe.io/Rest/Media/1/Search/Files'


class AdobeStockSearchAdapter(TrendAdapter):
    name = 'adobe_stock_search_api'

    def __init__(self, api_key: str | None = None, product_name: str | None = None):
        self.api_key = api_key or os.getenv('ADOBE_STOCK_API_KEY', '')
        self.product_name = product_name or os.getenv('ADOBE_STOCK_PRODUCT_NAME', 'StockFactoryTrendIntel/1.0')

    def available(self) -> bool:
        return bool(self.api_key)

    def fetch(self, terms: list[str]) -> list[TrendSignal]:
        if not self.available():
            return []
        signals = []
        fetched_at = datetime.now(timezone.utc).isoformat()
        for term in terms:
            try:
                nb_results = self._search_result_count(term)
            except Exception as exc:  # network/auth/API errors never crash the scan
                signals.append(TrendSignal(
                    term=term, source=self.name, verified=False, value=None,
                    signal_type=SIGNAL_CATALOG_SUPPLY,
                    fetched_at=fetched_at, note=f'adobe_stock_search_api_error: {exc}',
                ))
                continue
            signals.append(TrendSignal(
                term=term, source=self.name, verified=True, value=float(nb_results),
                signal_type=SIGNAL_CATALOG_SUPPLY,
                unit='catalog_result_count', fetched_at=fetched_at,
                note='Adobe Stock public Search API nb_results is EXISTING CATALOG SUPPLY '
                     '(competition), not search demand -- must never be promoted into a '
                     'verified_search_demand term.',
            ))
        return signals

    def _search_result_count(self, term: str) -> int:
        params = urllib.parse.urlencode({
            'search_parameters[words]': term,
            'search_parameters[limit]': 1,
            'result_columns[]': 'nb_results',
        })
        req = urllib.request.Request(
            f'{API_URL}?{params}',
            headers={'x-api-key': self.api_key, 'x-product': self.product_name},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return int(data.get('nb_results', 0))
