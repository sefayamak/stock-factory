"""Optional evidence-backed sector briefs for the daily creative queue.

A scout or human curator may write state/intelligence/market_briefs.json.
This module NEVER scrapes, creates invented market data, or treats a
keyword suggestion as observed stock sales. Stale/invalid briefs are skipped.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from .. import config

MAX_AGE_DAYS = 14
VALID_PLATFORMS = {"magnific", "adobe", "123rf", "vecteezy", "motion_elements"}
VALID_MEDIA = {"photo", "vector", "illustration", "video"}
VALID_SIGNALS = {"verified_search_interest", "catalog_supply_gap", "observed_downloads", "editorial_hypothesis"}


def load_market_briefs(day: str, platform: str = "magnific", media: str = "photo",
                       path: Path | None = None) -> tuple[list[dict], dict]:
    """Return approved, dated, unique briefs; never use unknown/stale signals."""
    # A checked-in research snapshot is available only while fresh; it is
    # not a live market feed and must never override a real scout export.
    if path is None:
        live_path = config.STATE_DIR / "intelligence" / "market_briefs.json"
        path = live_path if live_path.exists() else Path(__file__).with_name("public_market_seed.json")
    if platform not in VALID_PLATFORMS or media not in VALID_MEDIA:
        raise ValueError("unknown platform or media")
    if not path.exists():
        return [], {"status": "unavailable", "reason": "market_briefs.json missing"}
    try:
        today = date.fromisoformat(day)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("schema_version must be 1")
        items = data["briefs"]
        if not isinstance(items, list):
            raise ValueError("briefs must be a list")
        selected, seen = [], set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("brief must be object")
            category, scene = item["category"], item["scene"]
            source, observed = item["source_url"], date.fromisoformat(item["observed_on"])
            signal, target, medium = item["signal_type"], item["platform"], item["media"]
            if (not all(isinstance(v, str) and v.strip() for v in
                        (category, scene, source, signal, target, medium))
                    or not source.startswith(("https://", "http://"))
                    or signal not in VALID_SIGNALS or target not in VALID_PLATFORMS
                    or medium not in VALID_MEDIA):
                raise ValueError("invalid brief fields")
            if observed > today or (today - observed).days > MAX_AGE_DAYS:
                continue
            if target != platform or medium != media:
                continue
            identity = (category.casefold().strip(), scene.casefold().strip())
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(item)
        return selected, {"status": "loaded", "eligible": len(selected),
                          "skipped_or_out_of_scope": len(items) - len(selected)}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return [], {"status": "invalid", "reason": str(exc)}
