"""Stage 2: prompt generation and the daily production queue."""
from __future__ import annotations
from dataclasses import dataclass
from .trends import select_concepts_detailed


@dataclass
class QueueItem:
    job_id: str
    category: str
    scene: str
    prompt: str
    source: str = 'static_topic_bank'  # 'trend_snapshot' | 'static_topic_bank' -- provenance
    trend_term: str | None = None
    trend_status: str | None = None
    trend_snapshot_imported_at: str | None = None
    opportunity_score: float | None = None
    market_source_url: str | None = None
    event_country: str | None = None


def make_prompt(scene: str) -> str:
    return (
        "Generate one original premium commercial stock PHOTO, not an illustration or CGI. "
        + scene + ". Professional documentary editorial photography with honest natural imperfect detail, "
        "believable skin pores, correct anatomy and fingers, physically plausible lighting, coherent environment, "
        "accurate material texture, strong focal subject, commercially versatile composition. "
        "No logos, text, watermarks, readable screens, signage, celebrity likeness, or brand references. "
        "Avoid duplicated or distorted faces, extra limbs, plastic skin, over-sharpening, artificial bokeh. "
        "One cohesive photograph, no collage. 4K output preferred."
    )


def build_queue(day: str, count: int) -> list[QueueItem]:
    concepts = select_concepts_detailed(day, count)
    queue = []
    for i, c in enumerate(concepts, 1):
        job_id = f'STK-{day.replace("-", "")}-{i:04d}'
        queue.append(QueueItem(
            job_id=job_id, category=c.category, scene=c.scene, prompt=make_prompt(c.scene),
            source=c.source, trend_term=c.trend_term, trend_status=c.trend_status,
            trend_snapshot_imported_at=c.trend_snapshot_imported_at,
            opportunity_score=c.opportunity_score, event_country=c.event_country,
            market_source_url=c.market_source_url,
        ))
    return queue
