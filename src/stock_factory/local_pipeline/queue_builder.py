"""Daily queue construction: 150 photo + 50 illustration items by default,
sourced from the existing trend-intelligence/calendar/static-topic-bank
concept selector (stock_factory.trends.select_concepts_detailed) -- reused
rather than duplicated, per the existing-architecture-first directive.
"""
from __future__ import annotations
import re

from .. import config
from ..trends import select_concepts_detailed
from .models import ProductionItem

ILLUSTRATION_STYLE_SUFFIX = (
    ', flat vector-style illustration, clean geometric shapes, limited commercial-stock '
    'color palette, no photorealism, no text, no logos'
)


def _keyword_seed(category: str, scene: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]+", f"{category} {scene}".lower())
    seen: list[str] = []
    for w in words:
        if len(w) > 2 and w not in seen:
            seen.append(w)
    return seen[:12]


def _title_seed(category: str, scene: str) -> str:
    return scene.split(',')[0][:145] or category


def _build_lane(day: str, count: int, content_type: str, provider: str, id_prefix: str) -> list[ProductionItem]:
    if count <= 0:
        return []
    concepts = select_concepts_detailed(day, count)
    items = []
    for i, c in enumerate(concepts, 1):
        scene = c.scene if content_type == 'photo' else c.scene + ILLUSTRATION_STYLE_SUFFIX
        items.append(ProductionItem(
            item_id=f'{id_prefix}-{day.replace("-", "")}-{i:04d}',
            date=day,
            content_type=content_type,
            category=c.category,
            prompt=scene,
            title_seed=_title_seed(c.category, c.scene),
            keyword_seed=_keyword_seed(c.category, c.scene),
            target_marketplace='magnific',
            provider_preference=provider,
        ))
    return items


def build_daily_queue(
    day: str,
    photo_target: int | None = None,
    illustration_target: int | None = None,
) -> list[ProductionItem]:
    """Builds today's full production queue. Deterministic per day (same
    underlying concept selector as the existing pipeline), so re-running
    this for the same day without persisted state reproduces the same
    queue -- state_store is what actually prevents re-generating completed
    items, not queue non-determinism.

    Targets default to config.DAILY_PHOTO_TARGET/DAILY_ILLUSTRATION_TARGET
    read at CALL time (not as Python default-argument values, which would
    bind at import time and ignore any later config override/monkeypatch).
    """
    if photo_target is None:
        photo_target = config.DAILY_PHOTO_TARGET
    if illustration_target is None:
        illustration_target = config.DAILY_ILLUSTRATION_TARGET
    photo_items = _build_lane(day, photo_target, 'photo', 'google_flow', 'PHOTO')
    illustration_items = _build_lane(day, illustration_target, 'illustration', 'midjourney', 'ILLU')
    return photo_items + illustration_items
