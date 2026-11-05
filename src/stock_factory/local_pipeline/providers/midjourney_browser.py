"""Phase 5 target, NOT YET IMPLEMENTED. See google_flow_browser.py's
module docstring -- same constraints apply (must run on the operator's
machine against an already-authenticated session; here that is Discord,
since Midjourney is driven through a Discord bot/channel).

Midjourney outputs are illustration/vector-seed inputs, never true vector
exports -- callers must not label a Midjourney-sourced asset as a vector
file; see vector/procedural_vector.py for this repo's actual vector path.
"""
from __future__ import annotations
from .base import ProviderAdapter, ProviderUnavailable, GeneratedAsset


class MidjourneyBrowserProvider(ProviderAdapter):
    name = 'midjourney'

    def generate(self, prompt: str, content_type: str) -> GeneratedAsset:
        raise ProviderUnavailable(
            'midjourney_browser provider is not yet implemented (Phase 5). '
            'Run this orchestrator on the operator machine and implement '
            'the Discord-based Midjourney flow there.'
        )
