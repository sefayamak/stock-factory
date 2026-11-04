# Global Trend Intelligence -- status (2026-11-04, updated for PR #1 acceptance fixes)

Addresses the missed-Thanksgiving-2026 problem: stage 1 (`trends.py`) no
longer depends only on a static topic bank or a single platform's
dashboard. `trend_intelligence/` adds a worldwide event calendar, a
rolling early-warning scan, an explainable opportunity score, and a
versioned feed that `trends.py` actually reads to fill queue slots --
verified by a real dry run and, as of this update, a real cross-workflow
GitHub Actions run (see "Cloud feed handoff" below).

## PR #1 review findings and fixes (this update)

1. **Cloud feed handoff was local-only.** The scan workflow wrote
   `state/intelligence/feed.json` and uploaded it as a GitHub Actions
   artifact, but `daily.yml` (the main production workflow) never
   downloaded that artifact -- the two workflows don't share a filesystem,
   so in the real cloud scheduler the feed never actually reached
   production. **Fixed**: the scan workflow now publishes `feed.json` +
   `feed.sha256` as a new commit on a dedicated, persistent
   `intelligence-feed` branch (real git history = "versioned"); `daily.yml`
   fetches that branch before running the pipeline and runs
   `verify_feed.py` (freshness + integrity + source-identification) before
   proceeding, logging PASS/FAIL explicitly either way, and falling back
   safely (`--fail-soft`: never blocks or crashes production) if the feed
   is missing, stale, or fails its checksum.
2. **Adobe Stock `nb_results` was being treated as demand.** The adapter's
   signal was flowing into the same `verified_terms` set used for
   `demand_evidence` scoring, which would let a catalog *supply*/competition
   count masquerade as search *demand*. **Fixed**: `TrendSignal` now
   carries an explicit `signal_type` (`verified_search_demand` |
   `catalog_supply` | `calendar_predicted_demand` |
   `historical_download_performance`), `feed._collect_signals` routes
   strictly by that field into two separate sets
   (`verified_demand_terms` vs `catalog_supply_terms`), and scoring uses
   `catalog_supply_by_term` only for the `competition_gap` factor (log-scale
   normalized, more existing supply -> smaller gap), never for
   `demand_evidence`. `historical_download_performance` is now its own
   scoring factor (portfolio-wide Magnific acceptance rate -- still not
   per-topic history, documented gap), no longer silently reused as a
   competition proxy. See `tests/test_trend_intelligence.py::test_catalog_supply_is_never_treated_as_demand`
   and `tests/test_trend_intelligence_adapters_and_feed.py::test_adobe_supply_signal_never_lands_in_verified_demand_terms`.
3. **No duplicate-production-candidate guard.** Added a cross-tier dedup
   key (`trends._dedup_key`) so the same named trend-snapshot term or
   calendar opportunity can't be queued twice in one day's run. The static
   topic bank's intentional repetition (filling 100-150/day from a ~12-item
   pool) is explicitly exempted -- that repetition is pre-existing, correct
   behavior, not a duplicate-candidate defect. See
   `tests/test_trend_intelligence_adapters_and_feed.py::test_no_duplicate_production_candidates_across_tiers`.

`FEED_SCHEMA_VERSION` was bumped 1 -> 2 to mark this incompatible fix
(the v1 feed's `verified_demand_terms` could have contained supply-derived
terms; v2's never can).

## What's real vs. what's a documented gap

| Component | Status |
|---|---|
| Holiday calendar (92 countries, Gregorian + Islamic/Hebrew/Hindu/Chinese-lunisolar/Persian/Ethiopian via the `holidays` library) | **VERIFIED_WORKING** -- offline, recomputed per year, no live network. Expanded 2026-11-04 from 25 to 92; every added country code was verified to return real, non-empty 2026 holiday data before inclusion (`UA`/Ukraine was tried and excluded -- the library returned empty for 2026 at check time). |
| UN international observances (25 curated, fixed-date) | **VERIFIED_WORKING** -- static but sourced/dated, fixed annual dates so no staleness risk |
| Astronomical seasons (both hemispheres) | **VERIFIED_WORKING** -- computed, not fetched |
| Black Friday / Cyber Monday | **VERIFIED_WORKING** -- derived from Thanksgiving date |
| Early-warning scan (7/30/60/90/180/365-day windows, 120/90/60/30-day alerts, missed-opportunity detector) | **VERIFIED_WORKING** -- unit tested + dry run |
| Opportunity scoring (explainable, 8-factor, demand/supply/historical kept strictly separate) | **VERIFIED_WORKING**, with documented assumptions (market-size table, portfolio-wide-not-per-topic historical performance). See `scoring.py` docstrings. |
| Creative briefs (PHOTO_JPG, VECTOR_EPS) | **VERIFIED_WORKING** for the two formats this repo has a working pipeline for. |
| Feed -> `trends.py` queue integration, with cross-tier dedup | **VERIFIED_WORKING** -- dry run + tests show Black Friday/Cyber Monday/Thanksgiving Day ranking ahead of the static topic bank, with no duplicate named candidates. |
| **Cloud feed handoff (`intelligence-feed` branch, fetch + verify in daily.yml)** | **VERIFIED_WORKING** -- real cross-workflow GitHub Actions run, see "Cloud feed handoff" below. |
| Adobe Stock Search API adapter (`catalog_supply` signal only) | **IMPLEMENTED_NOT_TESTED against the real API** -- gated on `ADOBE_STOCK_API_KEY`, not set in this repo/CI. Supply/demand separation itself is unit-tested with a fake adapter. |
| Google Trends via BigQuery public dataset (`verified_search_demand` signal) | **IMPLEMENTED_NOT_TESTED against real BigQuery** -- gated on `GOOGLE_CLOUD_PROJECT`. |
| Magnific trend signal | **BLOCKED** for any new programmatic path (confirmed login-gated SPA, no official export). Wrapped the existing manual-import adapter in the common adapter interface. |

## Why Adobe/Google Trends/Magnific aren't "real data today"

Unchanged from the original PR -- see the researched findings per platform
below; this update only fixes how the Adobe signal is *used*, not whether
it's live:

- **Adobe Stock**: public Search API (`stock.adobe.io`), free self-serve
  key, no contributor OAuth -- returns `nb_results`, a genuine
  **supply/competition** signal, now explicitly never scored as demand.
- **Google Trends**: no live-query API; `bigquery-public-data.google_trends`
  (official, scrape-free, US/weekly top-rising terms) is implemented,
  gated on a configured GCP project.
- **Magnific**: still confirmed blocked; no new finding changes that.

## Cloud feed handoff (real cross-workflow test, this update)

`trend_intelligence.yml`'s "Publish feed to intelligence-feed branch" step
commits `state/intelligence/feed.json` + `feed.sha256` to the
`intelligence-feed` branch on every run where the feed content changed.
`daily.yml`'s "Fetch global-trend-intelligence feed" step pulls that
branch's files into its own job before running the pipeline, then
`verify_feed.py` checks freshness (`is_feed_stale`), integrity
(`verify_integrity`, a sha256 check), and source identification
(`provenance.git_sha`/`workflow_run_id`), logging an explicit PASS or a
named failure (`FEED_MISSING` / `FEED_INTEGRITY_FAILED` / `FEED_STALE` /
`FEED_SOURCE_UNIDENTIFIED`) either way, with `--fail-soft` so production
never blocks on it.

**Evidence of a real run** (not just local dry-run) is recorded in PR #1's
comments: a `workflow_dispatch` run of `trend_intelligence.yml` on this
branch, followed by a `workflow_dispatch` run of `daily.yml`, with the
latter's "Fetch global-trend-intelligence feed" / "Verify fetched feed"
step logs showing the published feed was actually retrieved and verified
(run URLs and log excerpts in the PR comment).

## Known limitations / gaps (not closed in this PR)

1. **Not full worldwide coverage.** 92 of the `holidays` library's 250
   supported countries chosen for calendar-system diversity, regional
   spread (added NE/SE/S Asia, Middle East, broader Africa, Central/South
   America, Central/Eastern Europe), and hemisphere balance -- a real,
   larger subset, still not a claim of covering every country.
2. **Season/retail/school/tourism calendars beyond what's listed above**
   need per-country sources with no uniform free/official API; not
   attempted here rather than guessed at.
3. **Per-topic historical acceptance/download performance** is not tracked
   anywhere in this repo (`acceptance_learning.py` tracks rejection
   *reasons*, not topic performance) -- `historical_download_performance`
   uses the portfolio-wide Magnific baseline, not real per-topic history.
4. **Religious/cultural movable-date precision**: the `holidays` library's
   Islamic-calendar dates carry a documented ±1 day uncertainty.
5. Non-photo formats beyond PHOTO_JPG/VECTOR_EPS stay unactivated by
   design -- no working production/QC path exists for them yet.
6. The `intelligence-feed` branch grows by one small-JSON commit per
   changed scan (not squashed/rotated) -- fine at this scale, but a future
   iteration might want to prune history if it becomes a concern.

## Dry run (original PR, 2026-11-04)

```
$ PYTHONPATH=src python -m stock_factory.trend_intelligence.scan
[trend-intelligence] wrote state/intelligence/feed.json
[trend-intelligence] events_indexed=834 countries=25 duplicate_groups=25
  alerts=0 missed_opportunities=38 briefs=50
[trend-intelligence] adapter[adobe] = {'available': False}
[trend-intelligence] adapter[google_trends] = {'available': False}
[trend-intelligence] adapter[magnific] = {'available': False}
[trend-intelligence] integrity_check=PASS: ok
```

Feeding straight into the production queue (`pipeline --target 20`), the
top rows of `output/submission.csv` were Black Friday, Cyber Monday, and
Thanksgiving Day concepts (source=`calendar_opportunity`, scores 0.84-0.88)
-- ahead of the static topic bank, exactly the intended behavior.
