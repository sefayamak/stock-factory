# Global Trend Intelligence -- status (2026-11-04)

Addresses the missed-Thanksgiving-2026 problem: stage 1 (`trends.py`) no
longer depends only on a static topic bank or a single platform's
dashboard. `trend_intelligence/` adds a worldwide event calendar, a
rolling early-warning scan, an explainable opportunity score, and a
versioned feed that `trends.py` actually reads to fill queue slots --
verified by a real dry run (see "Dry run" below): Black Friday / Cyber
Monday / Thanksgiving Day led the Nov 4 2026 queue.

## What's real vs. what's a documented gap

| Component | Status |
|---|---|
| Holiday calendar (25 countries, Gregorian + Islamic/Hebrew/Hindu/Chinese-lunisolar/Persian via the `holidays` library) | **VERIFIED_WORKING** -- offline, recomputed per year, no live network |
| UN international observances (25 curated, fixed-date) | **VERIFIED_WORKING** -- static but sourced/dated, fixed annual dates so no staleness risk |
| Astronomical seasons (both hemispheres) | **VERIFIED_WORKING** -- computed, not fetched |
| Black Friday / Cyber Monday | **VERIFIED_WORKING** -- derived from Thanksgiving date |
| Early-warning scan (7/30/60/90/180/365-day windows, 120/90/60/30-day alerts, missed-opportunity detector) | **VERIFIED_WORKING** -- unit tested + dry run |
| Opportunity scoring (explainable, 7-factor) | **VERIFIED_WORKING**, but several factors are documented *assumptions* (market-size table, competition-gap proxy from the Magnific baseline) -- not licensed market data. See `scoring.py` docstrings. |
| Creative briefs (PHOTO_JPG, VECTOR_EPS) | **VERIFIED_WORKING** for the two formats this repo has a working pipeline for. ILLUSTRATION/ICON_PACK/PATTERN/DESIGN_BACKGROUND are **not activated** -- no production pipeline exists for them yet. |
| Feed -> `trends.py` queue integration | **VERIFIED_WORKING** -- dry run shows calendar opportunities filling queue slots ahead of the static topic bank, ranked by score. |
| Adobe Stock Search API adapter (`nb_results` as a supply/competition signal) | **IMPLEMENTED_NOT_TESTED against the real API** -- code path is real (not a stub), gated on `ADOBE_STOCK_API_KEY` which is not set anywhere in this repo/CI. Unit tests only exercise the "unavailable" path. |
| Google Trends via BigQuery public dataset | **IMPLEMENTED_NOT_TESTED against real BigQuery** -- same situation, gated on `GOOGLE_CLOUD_PROJECT` + `google-cloud-bigquery` (not a declared dependency, imported lazily). |
| Magnific trend signal | **BLOCKED** for any new programmatic path -- confirmed login-gated SPA with no official export (matches prior `docs/PLATFORM_RULES.md` finding, re-checked for this feature). Wrapped the existing manual-import adapter (`trend_import.py`) in the common adapter interface instead of duplicating it. |
| GitHub Actions daily scan | **VERIFIED_WORKING** as a workflow definition (retry, caching, stale-feed guard, artifact upload) -- not yet verified against a live scheduled run in this PR (first run will be on merge + schedule, or via `workflow_dispatch`). |

## Why Adobe/Google Trends/Magnific aren't "real data today"

Per the project's own established policy (see `docs/ADAPTERS.md` on Google
Flow): we do not scrape authenticated/ToS-restricted surfaces. For each of
the three mandated platforms we researched the actual official/permitted
access path rather than defaulting to manual-only or to scraping:

- **Adobe Stock**: the public **Search API** (`stock.adobe.io`) needs only
  a free self-serve API key (Adobe Developer Console) -- no contributor
  OAuth. It returns a catalog result count (`nb_results`), a genuine
  supply/competition signal. *Contributor Insights* (the account's own
  trend dashboard) is a different, OAuth-gated surface this project has
  no credentials for, so that one stays out of scope. Code for the Search
  API path is real; it just has no key configured in this environment.
- **Google Trends**: no official live-query API exists. The one
  genuinely official, scrape-free path is Google's own public BigQuery
  dataset `bigquery-public-data.google_trends` (weekly top-rising terms,
  US-only coverage). Implemented for real, gated on a GCP project being
  configured -- none is, in this environment.
- **Magnific**: still confirmed blocked; no new finding changes that.

None of the three require new credentials to be *requested* from the
contributor in this PR -- `ADOBE_STOCK_API_KEY` and `GOOGLE_CLOUD_PROJECT`
are both already-optional, already-named config points. Setting them
(owner action, outside this PR) switches the corresponding adapter from
"unavailable, falls back to calendar-based prediction" to "live-verified
signal" with no further code change.

## Known limitations / gaps (not closed in this PR)

1. **Not full worldwide coverage.** 25 countries chosen for calendar-system
   diversity and hemisphere balance -- a real subset, not a claim of
   covering every country with reliable data.
2. **Season/retail/school/tourism calendars beyond what's listed above**
   (school terms, tourism-board campaigns, sports fixtures) need
   per-country sources with no uniform free/official API; not attempted
   here rather than guessed at.
3. **Per-topic historical acceptance/download performance** is not tracked
   anywhere in this repo yet (`acceptance_learning.py` tracks rejection
   *reasons*, not topic performance) -- the scoring's "portfolio coverage"
   and "competition gap" factors use documented proxies, not real
   per-topic history. Flagged in `scoring.py`.
4. **Religious/cultural movable-date precision**: the `holidays` library's
   Islamic-calendar dates in particular carry a documented ±1 day
   uncertainty (depends on local moon sighting); treat as planning
   guidance, verify locally before a hard production deadline.
5. Non-photo formats (vector is a brief-only path; ICON_PACK etc. have no
   pipeline) stay unactivated by design -- activating a format with no
   working production/QC path would be worse than not listing it.

## Dry run (this PR, 2026-11-04)

```
$ PYTHONPATH=src python -m stock_factory.trend_intelligence.scan
[trend-intelligence] wrote state/intelligence/feed.json
[trend-intelligence] events_indexed=834 countries=25 duplicate_groups=25
  alerts=0 missed_opportunities=38 briefs=50
[trend-intelligence] adapter[adobe] = {'available': False}
[trend-intelligence] adapter[google_trends] = {'available': False}
[trend-intelligence] adapter[magnific] = {'available': False}
```

`missed_opportunities=38` is expected and honest for a *first-ever* run:
with no prior alert history, every event already inside the lead-time
window shows up as "would have been missed had this system not just
turned on" -- which is exactly the Thanksgiving 2026 scenario the brief
describes. Running this daily from here on, each event gets its
120/90/60/30-day alerts on schedule and this number should normally be 0.

Feeding straight into the production queue (`pipeline --target 20`), the
top rows of `output/submission.csv` were Black Friday, Cyber Monday, and
Thanksgiving Day concepts (source=`calendar_opportunity`, scores 0.84-0.88)
-- ahead of the static topic bank, exactly the intended behavior.
