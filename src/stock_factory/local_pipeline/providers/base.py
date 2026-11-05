"""Provider interface for browser-driven image generation.

IMPORTANT -- execution location: every concrete provider in this package
drives a real, already-authenticated browser session (Google Flow,
Midjourney) on whatever machine the orchestrator process is running on.
It cannot be exercised from a cloud CI/agent session that has no access
to the operator's logged-in browser -- there is nothing to fix in the
code for that; it is a property of where the process runs. Run the
orchestrator with python directly on the always-on machine (or from a
Claude Code session attached to that machine via Remote Control), not
from a cloud-hosted session.
"""
from __future__ import annotations
from dataclasses import dataclass


class ProviderUnavailable(Exception):
    """Raised when a provider cannot currently service a request --
    e.g. not logged in, rate-limited, or (for browser providers invoked
    from an environment with no attached browser) structurally unable to
    run here. Orchestrator catches this and tries config.PROVIDER_FALLBACK."""


@dataclass
class GeneratedAsset:
    data: bytes
    provider: str
    provider_ref: str | None  # provider-side job/message id, for audit trail
    prompt_used: str


class ProviderAdapter:
    name: str = 'base'

    def generate(self, prompt: str, content_type: str) -> GeneratedAsset:
        raise NotImplementedError
