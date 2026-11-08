"""Strict, optional, owner-imported topic-level download evidence.

Input is state/intelligence/topic_performance.json, with an explicit dated
observation and per-topic downloads / total published asset-days. No sales or
search-interest figures are inferred, and absent/stale data stays unavailable.
"""
from __future__ import annotations
import json
import math
from datetime import date, timedelta
from pathlib import Path
from .. import config

MIN_ASSET_DAYS = 100
MAX_AGE_DAYS = 45


def load_topic_performance(today: date, path: Path | None = None) -> tuple[dict[str, float], dict]:
    path = path or config.STATE_DIR / "intelligence" / "topic_performance.json"
    if not path.exists():
        return {}, {"status": "unavailable", "reason": "topic_performance.json missing"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("source") != "owner_verified_platform_export":
            raise ValueError("source must be owner_verified_platform_export")
        observed = date.fromisoformat(data["observed_on"])
        if observed > today or (today - observed) > timedelta(days=MAX_AGE_DAYS):
            raise ValueError("observation stale or future-dated")
        rows = data["topics"]
        if not isinstance(rows, list):
            raise ValueError("topics must be a list")
        scores: dict[str, float] = {}
        used = 0
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("topic record must be an object")
            name = row["topic"].strip().casefold()
            downloads, asset_days = row["downloads"], row["published_asset_days"]
            if (not name or isinstance(downloads, bool) or isinstance(asset_days, bool)
                    or not isinstance(downloads, int) or downloads < 0
                    or not isinstance(asset_days, (int, float)) or not math.isfinite(asset_days)
                    or asset_days < 0 or name in scores):
                raise ValueError("invalid or duplicate topic metrics")
            if asset_days < MIN_ASSET_DAYS:
                continue
            # Smoothed downloads per 100 published asset-days, capped to [0, 1].
            # This is a relative prioritization heuristic, NOT expected earnings.
            rate = 100.0 * downloads / asset_days
            scores[name] = min(1.0, rate / 1.0)
            used += 1
        return scores, {"status": "measured", "source": data["source"],
                        "observed_on": observed.isoformat(), "eligible_topics": used,
                        "minimum_published_asset_days": MIN_ASSET_DAYS}
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {}, {"status": "invalid", "reason": str(exc)}
