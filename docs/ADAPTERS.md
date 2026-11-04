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

**Corrected architecture (2026-11-04):** the target Drive folders live in a
**personal Google My Drive account**, not a Workspace Shared Drive. A
Google Cloud service account cannot own or write files there even when
granted folder "Editor" access -- Google enforces this regardless of
sharing settings, so the service-account path proposed earlier would
silently fail against these specific folders. It has been corrected to a
secondary/legacy path (kept only for a possible future Shared Drive; see
"Shared Drive evaluation" below).

**Supported path: OAuth 2.0 user credentials for the owner's own account.**
One-time, interactive, run locally by the owner:

1. In the existing `pam-cloud-508907` GCP project (no new project): APIs &
   Services -> OAuth consent screen (configure once) -> Credentials ->
   Create OAuth client ID -> type **Desktop app**.
2. Owner runs `python3 scripts/setup_drive_oauth.py --client-id ... --client-secret ...`
   (or `--client-secrets-file client_secret.json`) on their own machine.
   This opens a real Google sign-in/consent screen in their browser,
   scoped to the single minimum permission `drive.file` (the app can only
   see/manage files *it* creates -- never the owner's whole Drive).
3. The script exchanges consent for a refresh token and prints the three
   values to set as GitHub secrets. Nothing is written to this repo or to
   Drive.
4. Owner runs:
   ```
   gh secret set GOOGLE_OAUTH_CLIENT_ID --body "..."
   gh secret set GOOGLE_OAUTH_CLIENT_SECRET --body "..."
   gh secret set GOOGLE_OAUTH_REFRESH_TOKEN --body "..."
   gh variable set DRIVE_ADOBE_FOLDER_ID --body "..."
   gh variable set DRIVE_MAGNIFIC_FOLDER_ID --body "..."
   ```

Every unattended run then builds `google.oauth2.credentials.Credentials`
from the stored refresh token and calls `.refresh()` immediately
(`drive_archive._build_oauth_credentials()`), so an unattended cloud run
always starts with a valid access token -- no further owner interaction is
needed unless the refresh token is revoked. The owner never has to sign in
again after the one-time setup.

Until the three `GOOGLE_OAUTH_*` secrets (or, for a future Shared Drive,
`GOOGLE_SERVICE_ACCOUNT_JSON`) and both `DRIVE_ADOBE_FOLDER_ID` /
`DRIVE_MAGNIFIC_FOLDER_ID` are set, `drive_archive.archive()` is a
documented no-op: it reports `drive_not_configured` instead of uploading.
Once configured it uploads for real via the Drive v3 API, with:

- SHA256 integrity verification (local hash recorded as a Drive file
  property, compared against a read-back hash after upload).
- Retry with exponential backoff (4 attempts) on transient API errors.
- Duplicate protection -- a file with the same name *and* recorded sha256
  already in the target folder is skipped, not re-uploaded.
- A persistent archive log at `STATE_DIR/drive_archive_log.jsonl` (one
  record per archived file: name, Drive file id, sha256, queue, duplicate
  flag).
- `drive_archive.verify_with_test_artifact()` -- uploads a small harmless
  text file, reads it back, checks its sha256, then deletes it. Use this to
  confirm credentials/folder IDs are wired correctly without touching any
  real production asset.

This code path is implemented and unit-tested (`tests/test_drive_archive.py`,
against a fake Drive service and fake OAuth credentials object -- no real
credentials or network access needed for tests, 44 tests total, all
passing). It has not yet been exercised against the real Drive folders:
that requires the owner to complete the one-time OAuth consent above (see
the final report's BLOCKERS).

### Shared Drive evaluation (no migration performed)

A dedicated Google Workspace Shared Drive would let a service account own
files directly (Shared Drives, unlike personal My Drive, support
service-account ownership), which would remove the refresh-token lifecycle
entirely and make multi-user access/auditing cleaner. Trade-offs:

- **Requires a paid Google Workspace plan** (Shared Drives are a Workspace
  feature, not available to a plain personal Google account) -- a real
  cost, not just a config change.
- Would mean moving `production/`, `production_assets/`, `intelligence/`,
  and `docs/` into a new Shared Drive, which changes every existing
  sharing link and permission currently pointing at the personal-account
  folders.
- The OAuth path above has no such cost and no migration risk, and the
  `drive.file` scope already keeps the service's reach minimal.

**Recommendation: keep OAuth on the existing personal My Drive for now.**
Revisit a Shared Drive only if/when there's an actual Workspace plan in
place and a concrete need for service-account ownership or multi-user
write access -- not before. No files were moved or restructured as part of
this evaluation.

## Magnific Search Trends -- manual-import adapter (`trend_import.py`)

`contributor.magnific.com/search-trends` is a JS-rendered SPA, likely
login-gated, with no static fetch or officially supported export (see
`docs/PLATFORM_RULES.md`). Scraping an authenticated session is not
attempted -- same rationale as Flow above.

`trend_import.py` is the supported alternative: the account owner opens the
page in their own authenticated browser and drops a small JSON/CSV
snapshot of the visible terms into `TREND_SNAPSHOT_DIR` (default
`trend_inbox/`). `import_pending_snapshots()` ingests new files (claiming
them into `_claimed/`, same pattern as `manual_inbox_adapter`), keeps every
snapshot in `STATE_DIR/trend_history/index.jsonl` (never overwritten),
de-duplicates a byte-identical re-import, and `latest_trend_report()`
scores what changed between the two most recent snapshots (new / rising /
falling / dropped terms, by rank and volume delta).

This is explicitly **not** live trend monitoring -- it is only as fresh as
the most recent human-provided snapshot.

**Prioritization wiring (2026-11-04):** `trends.select_concepts_detailed()`
uses a snapshot only if it is younger than `config.TREND_STALE_AFTER_DAYS`
(default 14 days); a stale or missing snapshot falls back to the
deterministic static topic bank with no trend influence at all. When a
fresh snapshot exists, its terms are ranked new/rising-first (via
`trend_import.score_trend_changes` against the prior snapshot, or by rank
alone with only one snapshot on file) and fill up to
`config.TREND_PRIORITY_SLOTS_MAX` queue slots; remaining slots are always
static-bank concepts. Provenance (`source`, `trend_term`, `trend_status`,
`trend_snapshot_imported_at`) is carried on every `Concept`/`QueueItem` and
into the dry-run CSV, so a report always shows whether and why a given
day's queue was trend-influenced. Do not represent the static topic bank,
or a stale snapshot, as current trend data.
