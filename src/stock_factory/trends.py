"""Stage 1: daily stock trend research and concept selection.

No external trend API is wired up yet (would need a paid/authenticated
source, e.g. Adobe Stock trends, Shutterstock keyword data, or a search
API). Until one is configured, concept selection is deterministic per day
from a curated topic bank, which keeps runs reproducible and auditable.
"""
from __future__ import annotations
import random

TOPICS = [
    ('artisan craft', 'A craftsperson carefully weaving natural fibers at a sunlit workbench, tactile texture, no writing or logo'),
    ('active aging', 'Two active older adult friends enjoying a relaxed walk on a quiet woodland path, candid documentary framing'),
    ('food craftsmanship', 'Baker preparing fresh handmade bread in a small authentic kitchen, natural window light, simple hands'),
    ('home wellbeing', 'Mature adult tending indoor plants in a quiet lived-in apartment, natural candid moment'),
    ('skincare', 'Adult applying skincare cream in a simple real bathroom, realistic natural skin texture and believable hands'),
    ('small business', 'Independent maker arranging handmade pottery for a local delivery, thoughtful natural light, no brand packaging'),
    ('human connection', 'Two generations sharing a warm conversation in a cozy home, subtle authentic emotion'),
    ('sustainable lifestyle', 'Person repairing a well worn piece of clothing at a home sewing desk, natural textile detail'),
    ('remote work', 'Freelancer working from a sunlit kitchen table with a laptop and coffee, authentic unposed home office'),
    ('urban commute', 'Commuter waiting calmly at a quiet morning train platform, natural city light, candid framing'),
    ('fitness routine', 'Adult stretching on a yoga mat in a simple sunlit living room, realistic effort and natural sweat'),
    ('family cooking', 'Parent and child chopping vegetables together at a home kitchen counter, warm candid moment'),
]


def select_concepts(day: str, n: int) -> list[tuple[str, str]]:
    """Deterministic per-day shuffle so a rerun of the same day is reproducible."""
    rng = random.Random(day)
    pool = TOPICS.copy()
    rng.shuffle(pool)
    return [pool[i % len(pool)] for i in range(n)]
