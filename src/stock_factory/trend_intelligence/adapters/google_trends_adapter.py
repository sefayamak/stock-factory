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

This adapter implements that BigQuery path, gated on `GOOGLE_CLOUD_PROJECT`
being set and the OPTIONAL `google-cloud-bigquery` package being installed
(deliberately NOT in requirements.txt; imported lazily so the rest of the
system works without it). It is NOT enabled in this repo's CI.

Operational requirements (documented, not enabled here):
  - Auth: Application Default Credentials for a GCP project with the
    BigQuery API enabled (GOOGLE_APPLICATION_CREDENTIALS service-account
    key, `gcloud auth application-default login`, or workload identity).
    Querying the public dataset bills query bytes to *that* project.
  - Cost bound: ONE query per scan for all candidate terms, restricted to
    the last GOOGLE_TRENDS_REFRESH_LOOKBACK_DAYS of the `refresh_date`
    partition, a hard `maximum_bytes_billed` cap
    (GOOGLE_TRENDS_MAX_BYTES_BILLED, default 2 GiB -- BigQuery fails the
    job rather than bill more), and a LIMIT of GOOGLE_TRENDS_MAX_ROWS rows.
  - Coverage: US DMA-level weekly top-rising terms only (region recorded
    on each signal).

What it measures: Google SEARCH INTEREST (rank among rising searches) --
never stock-buyer download or purchase demand. Each signal keeps the
source's observation week (`observation_date`) separate from `fetched_at`;
an observation older than GOOGLE_TRENDS_MAX_OBSERVATION_AGE_DAYS is
marked fresh=False and is not scored as current interest, however
recently it was fetched. With nothing configured, it returns no signals;
callers fall back to calendar-based prediction, never a fabricated value."""
from __future__ import annotations
import datetime as _dt
import os
from datetime import datetime, timezone

from .base import TrendAdapter, TrendSignal, AdapterStatus, SIGNAL_SEARCH_INTEREST

TABLE = 'bigquery-public-data.google_trends.top_rising_terms'
GOOGLE_TRENDS_MAX_BYTES_BILLED = int(os.getenv('GOOGLE_TRENDS_MAX_BYTES_BILLED', str(2 * 1024 ** 3)))
GOOGLE_TRENDS_MAX_ROWS = int(os.getenv('GOOGLE_TRENDS_MAX_ROWS', '1000'))
GOOGLE_TRENDS_REFRESH_LOOKBACK_DAYS = int(os.getenv('GOOGLE_TRENDS_REFRESH_LOOKBACK_DAYS', '7'))
GOOGLE_TRENDS_MAX_OBSERVATION_AGE_DAYS = int(os.getenv('GOOGLE_TRENDS_MAX_OBSERVATION_AGE_DAYS', '14'))
REGION = 'US (Nielsen DMA-level; best rank across DMAs)'

QUERY = f"""
    SELECT LOWER(term) AS term, MAX(week) AS week, MIN(rank) AS rank, MAX(refresh_date) AS refresh_date
    FROM `{TABLE}`
    WHERE refresh_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @lookback_days DAY)
      AND LOWER(term) IN UNNEST(@terms)
    GROUP BY term
    LIMIT {GOOGLE_TRENDS_MAX_ROWS}
"""


def _dependency_ready() -> bool:
    try:
        import google.cloud.bigquery  # noqa: F401
    except ImportError:
        return False
    return True


class GoogleTrendsBigQueryAdapter(TrendAdapter):
    name = 'google_trends_bigquery_public_dataset'

    def __init__(self, project: str | None = None):
        self.project = project if project is not None else os.getenv('GOOGLE_CLOUD_PROJECT', '')

    def available(self) -> bool:
        return bool(self.project) and _dependency_ready()

    def readiness(self) -> AdapterStatus:
        configured = bool(self.project)
        dep = _dependency_ready()
        notes = []
        if not configured:
            notes.append('GOOGLE_CLOUD_PROJECT not set')
        if not dep:
            notes.append('optional dependency google-cloud-bigquery not installed')
        return AdapterStatus(adapter=self.name, configured=configured, dependency_ready=dep,
                             auth_ready=None, notes='; '.join(notes))

    def fetch(self, terms: list[str], today=None) -> list[TrendSignal]:
        """One bounded query for all terms. Raises on query/auth errors --
        the caller (feed._collect_signals) records them as
        available=False with the error, rather than this method silently
        returning nothing."""
        if not self.available():
            return []
        today = today or datetime.now(timezone.utc).date()
        from google.cloud import bigquery  # lazy import, optional dependency
        client = bigquery.Client(project=self.project)
        wanted = sorted({t.strip().lower() for t in terms if t and t.strip()})
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter('terms', 'STRING', wanted),
                bigquery.ScalarQueryParameter('lookback_days', 'INT64', GOOGLE_TRENDS_REFRESH_LOOKBACK_DAYS),
            ],
            maximum_bytes_billed=GOOGLE_TRENDS_MAX_BYTES_BILLED,
        )
        rows = list(client.query(QUERY, job_config=job_config).result())
        fetched_at = datetime.now(timezone.utc).isoformat()
        original = {t.strip().lower(): t for t in terms}
        signals = []
        for row in rows:
            week = row.week if isinstance(row.week, _dt.date) else _dt.date.fromisoformat(str(row.week)[:10])
            fresh = (today - week).days <= GOOGLE_TRENDS_MAX_OBSERVATION_AGE_DAYS
            signals.append(TrendSignal(
                term=original.get(row.term, row.term), source=self.name, verified=True,
                value=float(row.rank), signal_type=SIGNAL_SEARCH_INTEREST,
                unit='weekly_top_rising_rank', measure='search_interest',
                fetched_at=fetched_at, observation_date=week.isoformat(), region=REGION, fresh=fresh,
                note=(f'{TABLE}, week={week.isoformat()}; Google search interest, NOT stock-buyer '
                      'download/purchase demand' + ('' if fresh else
                      f'; observation older than {GOOGLE_TRENDS_MAX_OBSERVATION_AGE_DAYS}d -> not current')),
            ))
        return signals
