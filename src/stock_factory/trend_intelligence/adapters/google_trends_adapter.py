"""Google Trends: there is no free, officially-supported live query API.
Research findings (2026-11-04):

- The consumer trends.google.com frontend has no documented public API;
  the commonly-used `pytrends` library works by reverse-engineering that
  frontend's private endpoints -- same category of risk this project
  already declined for Google Flow (docs/ADAPTERS.md): unofficial,
  liable to break without notice, and arguably against Google's terms for
  automated querying. Not used here, by the same policy.
- Google Ads Keyword Planner API is official, but requires an active
  Google Ads account under paid-media billing, OAuth, and a `developer
  token` application -- not just an API key. Out of scope for a
  no-new-spend content pipeline.
- The one genuinely *official, permitted, no-scraping* path is Google's
  own public BigQuery dataset `bigquery-public-data.google_trends`
  (`international_top_rising_terms` / `top_rising_terms`), published by
  Google itself and queryable with an ordinary GCP project + BigQuery
  client library (free tier covers this volume). Coverage is mostly
  US/weekly top-rising terms, not a worldwide live feed, so it's a partial
  signal, not a substitute for the Adobe/Magnific signals.

This adapter implements that BigQuery path for real, gated on
`GOOGLE_CLOUD_PROJECT` being set and the `google-cloud-bigquery` package
being installed (not a hard dependency of this package -- imported lazily
so the rest of the system works without it). With neither configured,
`available()` is False and this returns no signals; callers must fall back
to calendar-based prediction or a manual snapshot, never fabricate a trend
value."""
from __future__ import annotations
import os
from datetime import datetime, timezone

from .base import TrendAdapter, TrendSignal, SIGNAL_SEARCH_DEMAND


class GoogleTrendsBigQueryAdapter(TrendAdapter):
    name = 'google_trends_bigquery_public_dataset'

    def __init__(self, project: str | None = None):
        self.project = project or os.getenv('GOOGLE_CLOUD_PROJECT', '')

    def available(self) -> bool:
        if not self.project:
            return False
        try:
            import google.cloud.bigquery  # noqa: F401
        except ImportError:
            return False
        return True

    def fetch(self, terms: list[str]) -> list[TrendSignal]:
        if not self.available():
            return []
        from google.cloud import bigquery  # lazy import, optional dependency
        client = bigquery.Client(project=self.project)
        fetched_at = datetime.now(timezone.utc).isoformat()
        signals = []
        for term in terms:
            query = """
                SELECT term, rank, week
                FROM `bigquery-public-data.google_trends.top_rising_terms`
                WHERE LOWER(term) = LOWER(@term)
                ORDER BY week DESC
                LIMIT 1
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter('term', 'STRING', term)]
            )
            try:
                rows = list(client.query(query, job_config=job_config).result())
            except Exception as exc:
                signals.append(TrendSignal(
                    term=term, source=self.name, verified=False, fetched_at=fetched_at,
                    signal_type=SIGNAL_SEARCH_DEMAND,
                    note=f'bigquery_error: {exc}',
                ))
                continue
            if not rows:
                signals.append(TrendSignal(
                    term=term, source=self.name, verified=True, value=None,
                    signal_type=SIGNAL_SEARCH_DEMAND,
                    fetched_at=fetched_at, note='no matching row in top_rising_terms (US/weekly coverage only)',
                ))
                continue
            row = rows[0]
            signals.append(TrendSignal(
                term=term, source=self.name, verified=True, value=float(row.rank),
                signal_type=SIGNAL_SEARCH_DEMAND,
                unit='weekly_top_rising_rank', fetched_at=fetched_at,
                note=f'bigquery-public-data.google_trends.top_rising_terms, week={row.week}',
            ))
        return signals
