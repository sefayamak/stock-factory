"""Stage 2: prompt generation and the daily production queue."""
from __future__ import annotations
from dataclasses import dataclass
from .trends import select_concepts


@dataclass
class QueueItem:
    job_id: str
    category: str
    scene: str
    prompt: str


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
    concepts = select_concepts(day, count)
    queue = []
    for i, (cat, scene) in enumerate(concepts, 1):
        job_id = f'STK-{day.replace("-", "")}-{i:04d}'
        queue.append(QueueItem(job_id=job_id, category=cat, scene=scene, prompt=make_prompt(scene)))
    return queue
