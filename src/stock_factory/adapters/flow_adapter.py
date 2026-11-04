"""Google Flow adapter -- BLOCKED. Do not implement unattended Flow automation.

Verified (2026-11-04): Google Flow (flow.google.com) has no official public
API, SDK, or batch/export mechanism for unattended image generation. The
only "integrations" found are unofficial reverse-engineered clients and
headless-browser automation against Flow's private backend; both require
replaying Google session auth and risk breaking without notice or violating
Google's Terms of Service (automated access / bypassing login or CAPTCHA).

Also verified: a Google AI Pro/Ultra subscription's in-product Flow credit
allowance is a separate system from Gemini API / Vertex AI billing. Flow
credits cannot be spent through the API, and Flow being available on a plan
does not mean the Gemini API is pre-funded or pre-authorized by that plan.

Because of this, Stock Factory does NOT call Flow programmatically. This
module exists only to make that decision explicit and discoverable.

Supported alternative (implemented): `manual_inbox_adapter.py`. The account
owner generates images by hand in the Flow web UI (their own authenticated
session, no automation), downloads them, and drops the files into
`INBOX_DIR`. The pipeline picks them up from there -- this uses the existing
subscription legitimately, with no bypass of auth, CAPTCHA, or rate limits.

See docs/ADAPTERS.md for the full rationale and status.
"""
from __future__ import annotations
from .base import Adapter, RawAsset

BLOCKED_REASON = (
    "Google Flow has no officially supported unattended API as of 2026-11-04. "
    "Automating it would require reverse-engineered/unofficial access or "
    "headless-browser scraping against an authenticated Google session, which "
    "risks violating Google's Terms of Service and can break without notice. "
    "Use manual_inbox_adapter instead: generate in the Flow UI by hand, drop "
    "files into INBOX_DIR. See docs/ADAPTERS.md."
)


class FlowAdapter(Adapter):
    name = 'flow'

    def fetch(self, n: int) -> list[RawAsset]:
        raise NotImplementedError(BLOCKED_REASON)
