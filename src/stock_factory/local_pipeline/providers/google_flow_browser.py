"""Phase 2 target, NOT YET IMPLEMENTED.

Google Flow / "Nano Banana"-style browser-driven generation. This will
use Playwright against the operator's own already-authenticated browser
profile (no credentials handled or stored by this code -- see
local_pipeline/providers/base.py module docstring on why this must run
on the operator's own machine).

Planned shape, once implemented:
- launch persistent browser context pointed at the operator's Chrome
  profile directory (so the existing Google sign-in is reused, never a
  fresh login this code performs itself)
- navigate to Flow, submit the prompt, wait for render completion with
  bounded retries
- download the resulting image, return it as a GeneratedAsset
- on any detected failure (selector not found, logged out, rate-limited,
  CAPTCHA-like challenge), raise ProviderUnavailable with a specific
  reason and save a screenshot to output/_debug/ for troubleshooting --
  never retry through a challenge automatically

Left unimplemented here deliberately: a believable implementation needs
to be built and iterated against the real Flow UI on the operator's
machine, where it can actually be run and observed. A version written
blind, without ever running against the live page, would be fiction
dressed as working code.
"""
from __future__ import annotations
from .base import ProviderAdapter, ProviderUnavailable, GeneratedAsset


class GoogleFlowBrowserProvider(ProviderAdapter):
    name = 'google_flow'

    def generate(self, prompt: str, content_type: str) -> GeneratedAsset:
        raise ProviderUnavailable(
            'google_flow_browser provider is not yet implemented (Phase 2). '
            'Run this orchestrator on the operator machine and implement '
            'the Playwright flow against the live Flow UI there.'
        )
