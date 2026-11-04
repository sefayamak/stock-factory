# Stock Factory (safe pilot)

Remote-ready scheduled AI stock generator prototype. It **does not** upload files to Magnific, and it never auto-submits content. Generated assets require human visual and IP/AI disclosure review.

## Design
- GitHub Actions daily at 07:23 UTC; cron may be delayed or skipped by GitHub.
- Off by default: scheduled jobs produce a three-row metadata manifest only.
- To enable spending, configure `GEMINI_API_KEY` repository secret and set repository variable `ALLOW_PAID_GENERATION=true`. Manual `workflow_dispatch` with `execute=false` remains safe dry run when no key/flag present.
- Daily budget ceiling by request count: 3 image requests/run (model provider pricing applies). Gemini may bill failed responses or text tokens; monitor provider bills directly.
- Gemini output model default `gemini-3.1-flash-image` at 4K. Change `GEMINI_IMAGE_MODEL` only after validating model size capabilities.
- No low-resolution upscaling to meet marketplace requirements; technical fails are quarantined in CSV.
- Daily run artifacts retained 30 days: JPEGs, metadata CSV, SHA256, run.json. Download and store to durable cloud storage before expiration.
- Existing accepted/rejected Magnific files are **not imported**. No proprietary rejection model is trained or claimed.

## Run locally
```
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.factory --count 3
# only when API key is present and you're willing to spend:
python -m src.factory --count 3 --execute
```

## Gaps before unattended production
1. Connect durable object storage + database for persistent state, deduplication, cost tracking, retry, spend caps, and audit logs.
2. Confirm the image provider account is enabled and its model responds to 4K requests.
3. Add visual QC (human review) and metadata writer, licenses, provenance, and cross-platform duplicate matching.
4. Magnific FTP is documented as eligible at 500 published assets. Current account 125 published, so do not automate Magnific upload.
5. Monitor scheduled runs and stop automatically on duplicate, API error, unexpected spending or image QC failures.

This is a deliberately limited **pilot**, not a 24/7 daemon or an end-to-end publishing service.
