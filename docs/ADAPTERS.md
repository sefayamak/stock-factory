# Image-source adapters: status

## Google Flow -- BLOCKED (not implemented, by design)

Checked 2026-11-04. Findings:

- Google Flow (flow.google.com) has **no official public API, SDK, or
  batch/export mechanism**. It is documented only as a consumer web product
  bundled with Google AI Pro/Ultra plans.
- The only "Flow API" integrations found publicly (`gflow-cli`, a
  third-party `useapi.net` wrapper) are unofficial, reverse-engineered
  against Flow's private backend, or drive it via headless-browser
  automation of the authenticated web session. Their own docs warn the
  endpoints/auth can break without notice. Automating a consumer web app
  this way (bypassing normal login flows, scripting around CAPTCHA/rate
  limits) is the kind of automated access most platforms' Terms of Service
  prohibit, and no Google statement sanctions it for Flow.
- **AI Pro/Ultra's Flow credit allowance is a separate system from Gemini
  API / Vertex AI billing.** Google's own developer forum confirms
  image/video model calls through the Gemini API require billing enabled
  in AI Studio/Cloud independent of any Flow subscription; Flow credits are
  not spendable through the API.

Given this, `adapters/flow_adapter.py` raises `NotImplementedError` with
this explanation instead of containing a scraper. **Do not replace it with
browser automation or a reverse-engineered client** -- that would silently
put the account's Google session, and the pipeline's "unattended" claim, at
risk.

### Supported alternative: `manual_inbox_adapter.py`

The account owner already has Google AI Pro and generates in the real Flow
web UI with their own authenticated session -- no bypass of anything.
After generating, they download the files and place them in `INBOX_DIR`
(default `inbox/`). The pipeline's `manual_inbox` adapter picks them up from
there on the next run and moves processed files to `INBOX_DIR/_claimed`.
This is legitimate, uses the existing subscription, and is implemented and
tested today.

This means the 100-150/day *generation* step is still a human action in the
Flow UI for now; the *pipeline* (ingestion -> QC -> processing -> dedup ->
archival -> tracking -> reporting) is what runs unattended in the cloud.
If Google ships an official Flow API later, add a new adapter next to this
one -- do not repurpose the blocked `flow_adapter.py`.

## Gemini API (paid) -- implemented, off by default

`adapters/gemini_adapter.py` calls the Gemini API directly for images, at
4K. This is proper developer-API billing, separate from any Flow
subscription (see above). It only runs when **both** `GEMINI_API_KEY` and
`ALLOW_PAID_GENERATION=true` are set; per this project's instructions it
stays disabled until separately authorized.

## Google Drive archival -- implemented, inactive until configured

Unattended GitHub Actions runs cannot reuse an interactive Google sign-in;
they need a **service account** with access granted on the target Drive
folders. Until `GOOGLE_SERVICE_ACCOUNT_JSON` (secret) and
`DRIVE_ADOBE_FOLDER_ID` / `DRIVE_MAGNIFIC_FOLDER_ID` (variables) are set,
`drive_archive.archive()` is a documented no-op: it reports
`drive_not_configured` per file instead of uploading, so nothing is
fabricated as working. Once those three are configured it uploads for
real via the Drive v3 API.
