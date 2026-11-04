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
# 'flow' = BLOCKED, see adapters/flow_adapter.py and docs/ADAPTERS.md.
ENABLED_ADAPTERS = [a.strip() for a in os.getenv('ENABLED_ADAPTERS', 'manual_inbox').split(',') if a.strip()]

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

# Google Drive archival (requirement 6). Needs a service account; see docs/ADAPTERS.md.
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', '')
DRIVE_ADOBE_FOLDER_ID = os.getenv('DRIVE_ADOBE_FOLDER_ID', '')
DRIVE_MAGNIFIC_FOLDER_ID = os.getenv('DRIVE_MAGNIFIC_FOLDER_ID', '')

JPEG_QUALITY = int(os.getenv('JPEG_QUALITY', '96'))
MIN_BYTES = 1_500_000
MIN_SHORT_EDGE = 2048
MAX_LONG_EDGE = 10000
MIN_MEGAPIXELS = 4_000_000
