# Global Trend Intelligence -- status (2026-11-04, updated for the second PR #1 review)

Addresses the missed-Thanksgiving-2026 problem: stage 1 (`trends.py`) no
longer depends only on a static topic bank or a single platform's
dashboard. `trend_intelligence/` adds a multi-country event calendar (an
explicit subset -- NOT worldwide; see `calendar_coverage` in the feed), a
rolling 365-day early-warning scan, an explainable opportunity score, and a
versioned feed that `trends.py` actually reads to fill queue slots.

**Evidence levels (read this before trusting any "VERIFIED" below):**
local unit tests + local dry runs; a *local replay* of the workflow shell
steps (`act` / hand replay / the verbatim-step replay against a local bare
repo described below); and GitHub-hosted Actions runs. These are different
kinds of evidence and are labeled separately. **A GitHub-hosted run of the
producer workflow (`trend_intelligence.yml`) has NOT been performed --
hosted end-to-end feed handoff is NOT VERIFIED** (see "Cloud feed handoff").

## Second review (8 findings) -- what changed

| # | Finding | Fix | Regression tests |
|---|---|---|---|
| 1 | Scan only added next year's events with <90 days left in the year (Aug scan missed Jan-Jul of next year; Dec scan ranked past events) | `feed.collect_horizon_events()` generates every calendar year touched by `[scan_date, scan_date + HORIZON_DAYS]` and filters strictly to it | `tests/test_ti_rolling_horizon.py` |
| 2 | Brief "production window" was `event_date-49 .. event_date`, ignoring review/buyer lead time; scoring used its own urgency | `deadlines.py`: one configurable date model (`buyer_ready_date`, `submission_deadline`, `production_deadline`, `production_start`, status ON_TIME/COMPRESSED/LATE) used by scoring, briefs, alerts and `trends.py`; LATE opportunities go to `late_opportunities`, never to briefs/top slots | `tests/test_ti_deadlines.py` |
| 3 | `_dedup_key` baked the source into the key (`trend:black friday` vs `event:us:...`), and calendar dedup ignored the date (two years merged) | Source-independent identity (normalized topic + country + event date); trend term merged only when unambiguous | `tests/test_ti_cross_source_dedup.py` (real selection path) |
| 4 | CLI and consumer validated differently; a 30-day future-dated feed was "fresh"; malformed shapes crashed | `feed.validate_feed()` -- the single validator for `verify_feed.py`, `trends.py` and the scan workflow guard; any failure -> zero calendar candidates, fail-soft | `tests/test_ti_feed_validation.py` (17 failure modes x CLI + real selection) |
| 5 | No alert history; thresholds fired only on the exact day; "missed" always assumed no prior alert | `alert_history.py` persists `state/intelligence/alert_history.json`; catch-up alerts exactly once; unknown production status reported as `unknown` | `tests/test_ti_alert_history.py` |
| 6 | Stale Magnific snapshot treated as fresh; Google observation week conflated with fetch time; adapter errors swallowed | Existing `TREND_STALE_AFTER_DAYS` policy reused (`trend_import.snapshot_is_fresh`); `observation_date` vs `fetched_at`; `verified_search_interest` label; per-adapter `AdapterStatus` | `tests/test_ti_adapter_health.py` |
| 7 | Acceptance rate shown as download performance; fake portfolio coverage; VECTOR_EPS implied working; "worldwide"; scan date used as verification date | `historical_download_performance: unavailable`, `portfolio_acceptance_rate` separate, `portfolio_coverage: not_computed`, `production_pipeline_status`, `calendar_coverage` report, `source_verification` block | `tests/test_ti_labeling.py` |
| 8 | `assert ... or True` and a vacuous `all(... if ...)` | Replaced with real assertions; this doc's hosted-run claim corrected | full suite |

`FEED_SCHEMA_VERSION` is now 4 (v3: deadline model; v4: label changes).
Older feeds are rejected by `validate_feed()` (FEED_SCHEMA_UNSUPPORTED).

## First review (earlier in PR #1) -- fixes kept

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
| Holiday calendar (25 countries, Gregorian + Islamic/Hebrew/Hindu/Chinese-lunisolar/Persian via the `holidays` library) | **VERIFIED_WORKING** -- offline, recomputed per year, no live network |
| UN international observances (25 curated, fixed-date) | **VERIFIED_WORKING** -- static, fixed annual dates; list last checked against the UN page on `UN_LIST_VERIFIED_ON` (2026-11-04), NOT re-verified per scan (events carry that date in `verified_at`, separate from `scan_date`) |
| Astronomical seasons (both hemispheres) | **VERIFIED_WORKING** -- computed, not fetched |
| Black Friday / Cyber Monday | **VERIFIED_WORKING** -- derived from Thanksgiving date |
| Early-warning scan (365-day horizon, 7/30/60/90/180/365-day windows, 120/90/60/30-day alerts with persistent history + catch-up, missed-opportunity detector) | **VERIFIED_LOCALLY** -- unit tests + local dry run/replay. Note: the first scan with an empty history alerts (catch-up) on every event already inside 120 days and reports every event already past its production start as missed -- a one-time burst (local replay: 446 alerts / 341 missed on run 1, 0 / 0 on run 2). |
| Opportunity scoring (explainable; demand/supply kept strictly separate; factors without data excluded, not faked) | **VERIFIED_LOCALLY**, with documented assumptions (market-size table, deadline durations). `historical_download_performance` = unavailable and `portfolio_coverage` = not_computed (no data); see `scoring.py`. |
| Production/submission deadline model (`deadlines.py`) | **VERIFIED_LOCALLY** -- defaults are documented assumptions (35-day review from PLATFORM_RULES, 21-day buyer lead, 14-day production, 2-day prep), overridable via `TI_*` env vars; not measured against real sales timing. |
| Creative briefs | PHOTO_JPG: **active** (consumed by `trends.py`). VECTOR_EPS: **planned_blocked** -- briefs are generated for planning only; nothing consumes them and creative vector generation is blocked (only procedural icons/patterns exist). |
| Feed -> `trends.py` queue integration, with source-independent dedup and shared validation | **VERIFIED_LOCALLY** (tests over the real selection path). |
| **Cloud feed handoff (`intelligence-feed` branch, fetch + verify in daily.yml)** | Producer side: **NOT VERIFIED on GitHub-hosted runners** (only local replays). Consumer side: **VERIFIED on a GitHub-hosted run** of `daily.yml` (dry-run) -- it fetched the real branch, rejected the stale-schema feed, and fell back safely. See below. |
| Adobe Stock Search API adapter (`catalog_supply` signal only) | **IMPLEMENTED_NOT_TESTED against the real API** -- gated on `ADOBE_STOCK_API_KEY`, not set in this repo/CI. Supply/demand separation itself is unit-tested with a fake adapter. |
| Google Trends via BigQuery public dataset (`verified_search_interest` signal -- search interest, NOT download demand) | **IMPLEMENTED_NOT_TESTED against real BigQuery** -- gated on `GOOGLE_CLOUD_PROJECT` + optional `google-cloud-bigquery`; NOT enabled in this repo. Query/freshness/status logic unit-tested against a fake BigQuery client only. See "Google Trends BigQuery: requirements and cost bound" below. |
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

### Google Trends BigQuery: requirements and cost bound (documented, not enabled)

- **Auth**: Application Default Credentials for a GCP project with the
  BigQuery API enabled (`GOOGLE_APPLICATION_CREDENTIALS` service-account
  key, `gcloud auth application-default login`, or workload identity),
  plus `GOOGLE_CLOUD_PROJECT`. Query bytes are billed to that project.
- **Optional dependency**: `google-cloud-bigquery` is deliberately *not* in
  `requirements.txt`; without it the adapter reports
  `configured=true, dependency_ready=false` and contributes nothing.
- **Cost bound**: one query per scan for all candidate terms, restricted to
  the last `GOOGLE_TRENDS_REFRESH_LOOKBACK_DAYS` (7) of the `refresh_date`
  partition, a hard `maximum_bytes_billed` cap (`GOOGLE_TRENDS_MAX_BYTES_BILLED`,
  default 2 GiB -- BigQuery fails the job instead of billing more) and
  `LIMIT GOOGLE_TRENDS_MAX_ROWS` (1000). Not run in CI; no paid source is
  enabled by this PR.
- **Semantics**: the value is a weekly top-rising *search-interest* rank for
  US DMAs. Each signal keeps `observation_date` (the source's week) separate
  from `fetched_at`; observations older than
  `GOOGLE_TRENDS_MAX_OBSERVATION_AGE_DAYS` (14) are `fresh=false` and are not
  scored as current interest.

### Adapter status fields

`feed.json`'s `adapter_status.<platform>` reports, separately: `configured`,
`dependency_ready`, `auth_ready` (null = not checkable before a real call),
`fetch_attempted`, `fetch_succeeded`, `fresh`, `signal_count`, `error`, and a
derived `available` (true only if all of those are good). A caught adapter
exception is reported as `available=false` with `error` set -- never as a
silent success. The Magnific manual-snapshot adapter applies the existing
`config.TREND_STALE_AFTER_DAYS` policy (the same one `trends.py` uses via
`trend_import.snapshot_is_fresh`): a stale snapshot is `fresh=false` and
contributes no signal.

## Cloud feed handoff -- evidence, labeled by kind

`trend_intelligence.yml`'s "Publish feed to intelligence-feed branch" step
commits `state/intelligence/feed.json`, `feed.sha256` and (new)
`alert_history.json` to the `intelligence-feed` branch whenever they
change; a new "Restore alert history" step restores `alert_history.json`
from that branch when the actions/cache entry is gone. `daily.yml`'s "Fetch
global-trend-intelligence feed" step pulls the feed from that branch, then
`verify_feed.py --fail-soft` runs the shared `validate_feed()` (structure,
schema version, types, dates, checksum, age, future-date skew,
provenance) and logs PASS or named failures; production never blocks on it,
and `trends.py` re-runs the same validator, so a rejected feed contributes
zero calendar candidates.

| Evidence | Kind | Result |
|---|---|---|
| Earlier in PR #1: `act` run of the scan job + **hand replay** of the publish/fetch shell steps against the real GitHub repo (created `intelligence-feed`, commit `c19effc`) | Local container + manual replay -- **NOT a GitHub-hosted Actions run** | Producer/consumer scripts worked; found and fixed the shallow-clone `FETCH_HEAD` bug. Caveat found in this review: the feed actually published at `c19effc` has an **empty** `provenance.git_sha`/`workflow_run_id`/`workflow` (and schema v2), so the earlier "verify_feed PASS with real provenance" claim cannot have been against that published file. |
| This review: verbatim replay of the producer steps (restore alert history, scan, guard, publish) twice and the consumer steps (fetch, verify) from `.github/workflows/*.yml`, against a **local bare repo** standing in for github.com | Local replay -- **NOT a GitHub-hosted run** | Run 1 published feed + alert history; run 2 restored alert history from the branch (0 re-alerts); consumer fetched 273 KB feed, `verify_feed` PASS (schema v4, checksum, provenance). |
| This review: `gh workflow run daily.yml --ref feature/global-trend-intelligence -f execute=false` -> run [41838777184](https://github.com/sefayamak/stock-factory/actions/runs/41838777184) | **GitHub-hosted** (consumer side only, dry run) | Fetched the real `intelligence-feed` branch (`c19effc`); shared validator rejected it (FEED_SCHEMA_UNSUPPORTED v2, missing deadline fields, FEED_SOURCE_UNIDENTIFIED); fail-soft continued; pipeline logged "feed rejected -- calendar candidates skipped". |
| GitHub-hosted run of `trend_intelligence.yml` (producer) | -- | **NOT VERIFIED.** GitHub only dispatches workflows that exist on the default branch; `gh workflow run trend_intelligence.yml` returns HTTP 404 because the file is not on `main`, and `main` is intentionally not touched by this PR. Its schedule only starts once merged. Until a hosted producer run publishes a schema-v4 feed, the hosted consumer will (correctly) keep rejecting the old v2 feed on the branch. |

## Known limitations / gaps (not closed in this PR)

1. **Not full worldwide coverage.** 25 countries chosen for calendar-system
   diversity and hemisphere balance -- a real subset, not a claim of
   covering every country with reliable data.
2. **Season/retail/school/tourism calendars beyond what's listed above**
   need per-country sources with no uniform free/official API; not
   attempted here rather than guessed at.
3. **Download performance is not tracked anywhere in this repo**, per topic
   or otherwise -- `historical_download_performance` is reported as
   `unavailable` and excluded from scores. The Magnific acceptance rate is
   reported separately as `portfolio_acceptance_rate` (portfolio-wide
   review acceptance, not downloads). `portfolio_coverage` is
   `not_computed` (no topic inventory wired in).
4. **Religious/cultural movable-date precision**: the `holidays` library's
   Islamic-calendar dates carry a documented ±1 day uncertainty.
5. Non-photo formats beyond PHOTO_JPG/VECTOR_EPS stay unactivated by
   design -- no working production/QC path exists for them yet.
6. The `intelligence-feed` branch grows by one commit per changed scan
   (not squashed/rotated). With `alert_history.json` (~1.4k tracked events,
   pruned 30 days after each event) the per-commit size is larger than
   before; a future iteration may want to prune branch history.
7. **Production status is not tracked automatically.** Alert history keeps
   `production_status`, but nothing in the pipeline sets it yet
   (`alert_history.set_production_status()` is the hook), so it is always
   reported as `unknown` -- never as "not produced".
8. **Hosted producer run not verified** (see "Cloud feed handoff").
9. The Adobe adapter would issue one Search API call per candidate term
   (~1.4k/scan) if a key were configured -- not rate-limited/batched yet.

## Dry run (this review, local, 2026-11-04, 92 countries)

```
$ PYTHONPATH=src python -m stock_factory.trend_intelligence.scan   # first run, empty alert history
[trend-intelligence] events_indexed=1372 countries=92 duplicate_groups=71 alerts=446 missed_opportunities=341 briefs=50
[trend-intelligence] adapter[adobe] = {... 'configured': False, 'available': False, 'notes': 'ADOBE_STOCK_API_KEY not set'}
[trend-intelligence] adapter[google_trends] = {... 'configured': False, 'dependency_ready': False, 'available': False}
[trend-intelligence] adapter[magnific] = {... 'configured': False, 'available': False}
[trend-intelligence] integrity_check=PASS: ok
# second run, history restored: alerts=0 missed_opportunities=0
```

## Dry run (original PR, 2026-11-04 -- superseded numbers, kept for history)

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
-- ahead of the static topic bank. **Superseded by finding 2:** under the
shared deadline model, Black Friday/Cyber Monday/Thanksgiving scanned on
2026-11-04 are LATE (submission deadline passed: they need ~72 days of
lead time), so they are now bucketed in `late_opportunities` and are no
longer queued for production.
