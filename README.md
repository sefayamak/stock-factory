# Stock Factory

Scheduled, cloud-run stock-asset production pipeline. Target: **100-150
QC-approved images/day** (hard ceiling 200). Human visual/IP review is still
required before any asset reaches a real submission queue -- this pipeline
only gets images to `PENDING_HUMAN_VISUAL_QC`.

## Pipeline stages
1. **Trends & concept selection** -- `stock_factory/trends.py` (deterministic topic bank today; swap in a real trend source later)
2. **Prompt generation & queue** -- `stock_factory/prompts.py`
3. **Image ingestion** -- `stock_factory/adapters/` (see below -- this is where Flow fits in, and where it's explicitly blocked)
4. **Automated technical QC** -- `stock_factory/qc.py`
5. **JPEG prep, metadata, dedup** -- `stock_factory/processing.py`
6. **Google Drive archival (Adobe/Magnific queues)** -- `stock_factory/drive_archive.py`
7. **Acceptance/rejection tracking** -- `stock_factory/tracking.py`
8. **Daily reporting/alerts** -- `stock_factory/reporting.py`

All orchestrated by `stock_factory/pipeline.py`.

## Image sources (adapters) -- see [docs/ADAPTERS.md](docs/ADAPTERS.md)
- `manual_inbox` (default, implemented): human downloads Flow-generated images into `INBOX_DIR`; pipeline ingests them.
- `gemini` (implemented, off by default): paid Gemini API. Requires `ALLOW_PAID_GENERATION=true` + `GEMINI_API_KEY`. Separate billing from any Flow/AI Pro subscription.
- `flow` (**BLOCKED, not implemented**): no official unattended Flow API exists as of 2026-11-04. See docs/ADAPTERS.md for the verification and the supported alternative.

## Run locally
```
python -m pip install -r requirements.txt
python -m pytest -q
PYTHONPATH=src python -m stock_factory.pipeline --target 100            # dry run: builds the queue only
PYTHONPATH=src python -m stock_factory.pipeline --target 100 --execute  # ingests inbox/, QCs, dedups, archives
```

## Cloud deployment status (actual, not just local)
- Code is pushed to `github.com/sefayamak/stock-factory` (public), default branch `main`.
- `.github/workflows/daily.yml` is committed on `main` and scheduled daily at 07:23 UTC, plus manual `workflow_dispatch`.
- **Currently runs safely with nothing configured**: no `GEMINI_API_KEY`, no `ALLOW_PAID_GENERATION`, no Drive service account/folder IDs, no `inbox/` contents in the repo. A scheduled run today produces an empty-but-valid dry run (queue built, nothing fetched) -- it will not spend money, upload anywhere, or fabricate output.
- To actually hit 100-150/day: the account owner needs to (a) generate in Flow's web UI and sync files into `INBOX_DIR` before each run (e.g. via a synced Drive folder or a repo-external upload step), and/or (b) authorize paid Gemini generation, and (c) create a Google service account + share the Adobe/Magnific Drive folders with it for stage 6 to actually upload.

## Design / safety
- Daily target 100-150, hard ceiling 200 (`DAILY_TARGET_CEILING`) so a bad config can't silently run away.
- Paid generation stays off until `ALLOW_PAID_GENERATION=true` + `GEMINI_API_KEY` are both set.
- No Flow automation/scraping. See docs/ADAPTERS.md.
- Dedup via a persistent sha256 ledger (`state/seen_hashes.json`) checked across runs, not just within one.
- Drive archival fails safe (no-op, clearly reported) without real service-account credentials.
- Daily report + non-zero exit on shortfall vs. `DAILY_TARGET_MIN` gives GitHub Actions something to alert on without extra integrations.

## Gaps before this is a full 24/7 production line
1. No real trend-research source wired up yet (stage 1 is a static topic bank).
2. Flow generation is still a manual human step (no official API to automate it).
3. Drive service account + folder sharing not yet created/configured.
4. No email/Slack alerting wired up; alerting today is "run report + non-zero exit on shortfall."
5. Magnific is documented as eligible for FTP automation at 500 published assets; current published count is below that, so do not automate Magnific upload even once Drive archival is live.
