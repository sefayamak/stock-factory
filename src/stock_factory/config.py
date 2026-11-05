"""Central configuration. All production targets and safety caps live here."""
from __future__ import annotations
import os
from pathlib import Path

# Production targets (requirement: 100-150 images/day; 100 is the floor, 150 the stretch).
DAILY_TARGET_MIN = int(os.getenv('DAILY_TARGET_MIN', '100'))
DAILY_TARGET_STRETCH = int(os.getenv('DAILY_TARGET_STRETCH', '150'))

# Hard safety ceiling so a misconfigured env var can never silently explode spend/volume.
DAILY_TARGET_CEILING = int(os.getenv('DAILY_TARGET_CEILING', '200'))

# Paid Gemini API generation stays off unless both are explicitly set.
ALLOW_PAID_GENERATION = os.getenv('ALLOW_PAID_GENERATION', 'false').lower() == 'true'
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

# Adapter selection: which source(s) supply raw images for this run.
# 'manual_inbox' = human-downloaded Flow (or any other) images dropped in INBOX_DIR.
# 'gemini' = paid Gemini API (requires ALLOW_PAID_GENERATION=true).
# 'cloudflare_flux' = free tier Cloudflare Workers AI (@cf/black-forest-labs/flux-1-schnell).
# 'flow' = BLOCKED, see adapters/flow_adapter.py and docs/ADAPTERS.md.
ENABLED_ADAPTERS = [a.strip() for a in os.getenv('ENABLED_ADAPTERS', 'manual_inbox').split(',') if a.strip()]

# Cloudflare Workers AI (free tier only).
CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN', '')
CLOUDFLARE_ACCOUNT_ID = os.getenv('CLOUDFLARE_ACCOUNT_ID', '')
CLOUDFLARE_TIMEOUT = int(os.getenv('CLOUDFLARE_TIMEOUT', '60'))
CLOUDFLARE_MAX_RETRIES = int(os.getenv('CLOUDFLARE_MAX_RETRIES', '3'))
CLOUDFLARE_RETRY_DELAY = float(os.getenv('CLOUDFLARE_RETRY_DELAY', '2'))
CLOUDFLARE_DAILY_GENERATION_CAP = int(os.getenv('CLOUDFLARE_DAILY_GENERATION_CAP', '50'))

INBOX_DIR = Path(os.getenv('INBOX_DIR', 'inbox'))
STATE_DIR = Path(os.getenv('STATE_DIR', 'state'))
OUT_DIR = Path(os.getenv('OUT_DIR', 'output'))

# Manual-import snapshots of Magnific Search Trends (login-gated SPA, no
# official export API -- see docs/PLATFORM_RULES.md and trend_import.py).
TREND_SNAPSHOT_DIR = Path(os.getenv('TREND_SNAPSHOT_DIR', 'trend_inbox'))
# A snapshot older than this is treated as stale and ignored by concept
# selection, which falls back to the static topic bank instead.
TREND_STALE_AFTER_DAYS = int(os.getenv('TREND_STALE_AFTER_DAYS', '14'))
# At most this many queue slots per day are filled from trending terms;
# the rest always comes from the deterministic static topic bank.
TREND_PRIORITY_SLOTS_MAX = int(os.getenv('TREND_PRIORITY_SLOTS_MAX', '20'))

# At most this many queue slots per day are filled from the global
# trend-intelligence feed's calendar-backed opportunities (see
# trend_intelligence/feed.py), after trend-snapshot slots and before the
# static topic bank. A missing/stale feed (same staleness policy as the
# trend snapshot above) contributes zero slots.
CALENDAR_OPPORTUNITY_SLOTS_MAX = int(os.getenv('CALENDAR_OPPORTUNITY_SLOTS_MAX', '15'))

# Google Drive archival (requirement 6). The target Drive folder is in a
# personal My Drive account -- a service account cannot own/write files
# there even with folder Editor access, so OAuth 2.0 user credentials
# (the owner's own account) are the primary, supported path. See
# docs/ADAPTERS.md and scripts/setup_drive_oauth.py for the one-time
# interactive consent flow that produces these three values.
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
GOOGLE_OAUTH_REFRESH_TOKEN = os.getenv('GOOGLE_OAUTH_REFRESH_TOKEN', '')

# Legacy/alternate path: a service account only works if the target folder
# lives on a Shared Drive (service accounts cannot own files in personal
# My Drive). Kept for that future architecture; OAuth above is preferred
# for the current personal-My-Drive setup. See docs/ADAPTERS.md.
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', '')

DRIVE_ADOBE_FOLDER_ID = os.getenv('DRIVE_ADOBE_FOLDER_ID', '')
DRIVE_MAGNIFIC_FOLDER_ID = os.getenv('DRIVE_MAGNIFIC_FOLDER_ID', '')

# Adobe production dispatch is paused; Magnific is the sole active production queue.
# Flip to '1'/'true' to resume the alternating adobe/magnific split.
ADOBE_MARKETPLACE_ACTIVE = os.getenv('ADOBE_MARKETPLACE_ACTIVE', '0').lower() in ('1', 'true', 'yes')

JPEG_QUALITY = int(os.getenv('JPEG_QUALITY', '96'))
MIN_BYTES = 1_500_000
MIN_SHORT_EDGE = 2048
MAX_LONG_EDGE = 10000
MIN_MEGAPIXELS = 4_000_000

# Local-PC-driven production pipeline (stock_factory/local_pipeline/).
# Separate from DAILY_TARGET_* above, which govern the older GitHub-Actions
# manual-inbox pipeline. 200/150/50 is the explicit business target, not
# derived from DAILY_TARGET_STRETCH.
DAILY_TOTAL_TARGET = int(os.getenv('DAILY_TOTAL_TARGET', '200'))
DAILY_PHOTO_TARGET = int(os.getenv('DAILY_PHOTO_TARGET', '150'))
DAILY_ILLUSTRATION_TARGET = int(os.getenv('DAILY_ILLUSTRATION_TARGET', '50'))

# Provider routing. Browser-automation providers only function when this
# process runs on a machine with an authenticated browser session for
# that provider -- see local_pipeline/providers/*.py docstrings.
PROVIDER_PHOTO_PRIMARY = os.getenv('PROVIDER_PHOTO_PRIMARY', 'google_flow')
PROVIDER_ILLUSTRATION_PRIMARY = os.getenv('PROVIDER_ILLUSTRATION_PRIMARY', 'midjourney')
PROVIDER_FALLBACK = os.getenv('PROVIDER_FALLBACK', 'manual_inbox')

LOCAL_PIPELINE_MAX_RETRIES = int(os.getenv('LOCAL_PIPELINE_MAX_RETRIES', '2'))
LOCAL_PIPELINE_STATE_DIR = Path(os.getenv('LOCAL_PIPELINE_STATE_DIR', 'state'))
LOCAL_PIPELINE_OUTPUT_DIR = Path(os.getenv('LOCAL_PIPELINE_OUTPUT_DIR', 'output'))
