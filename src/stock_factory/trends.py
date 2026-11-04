"""Stage 1: daily stock trend research and concept selection.

No external trend API is wired up yet (would need a paid/authenticated
source, e.g. Adobe Stock trends, Shutterstock keyword data, or a search
API). Concept selection is deterministic per day from a curated topic
bank by default, which keeps runs reproducible and auditable.

If a fresh, human-provided Magnific trend snapshot exists (see
trend_import.py), its highest-priority terms (new/rising, by rank) are
given the first queue slots, with provenance retained per concept so a
report can show whether a given day's queue was trend-informed or not.
A snapshot older than config.TREND_STALE_AFTER_DAYS is treated as stale
and ignored -- this module never represents stale or absent snapshot
data as live trend monitoring.

After that, the global trend-intelligence feed (see
trend_intelligence/feed.py, written by `python -m
stock_factory.trend_intelligence.scan`) fills further slots with
calendar-backed opportunities (holidays/observances/seasons/retail
campaigns) whose production window covers `day`, ranked by the
explainable opportunity score -- so the scan's scoring actually changes
what gets produced, not just a report nobody reads. A missing or stale
(> config.TREND_STALE_AFTER_DAYS old) feed is skipped silently, same
stale-data policy as the Magnific snapshot above.
"""
from __future__ import annotations
import random
from dataclasses import dataclass
from datetime import date, datetime, timezone

from . import config, trend_import

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


@dataclass
class Concept:
    category: str
    scene: str
    source: str  # 'trend_snapshot' | 'static_topic_bank'
    trend_term: str | None = None
    trend_status: str | None = None
    trend_snapshot_imported_at: str | None = None
    opportunity_score: float | None = None
    event_country: str | None = None


def select_concepts(day: str, n: int) -> list[tuple[str, str]]:
    """Deterministic per-day shuffle so a rerun of the same day is
    reproducible. Backward-compatible (category, scene) view -- callers
    that need provenance should use select_concepts_detailed instead."""
    return [(c.category, c.scene) for c in select_concepts_detailed(day, n)]


def _static_pool(day: str) -> list[tuple[str, str]]:
    rng = random.Random(day)
    pool = TOPICS.copy()
    rng.shuffle(pool)
    return pool


def _latest_fresh_snapshot() -> trend_import.Snapshot | None:
    history = trend_import.load_history()
    if not history:
        return None
    latest = history[-1]
    imported_at = datetime.fromisoformat(latest.imported_at)
    age_days = (datetime.now(timezone.utc) - imported_at).total_seconds() / 86400
    if age_days > config.TREND_STALE_AFTER_DAYS:
        return None
    return latest


def _trend_priority_terms(snapshot: trend_import.Snapshot) -> list[trend_import.TrendTerm]:
    """Orders a snapshot's terms by priority: new/rising first (per the
    trend-change report vs. the prior snapshot, if one exists), then by
    rank ascending. Falls back to rank-only ordering with no prior
    snapshot to diff against."""
    history = trend_import.load_history()
    status_by_term: dict[str, str] = {}
    if len(history) >= 2:
        report = trend_import.score_trend_changes(history[-2], history[-1])
        status_by_term = {c['term'].strip().lower(): c['status'] for c in report}

    order = {'new': 0, 'rising': 1, 'stable': 2, 'falling': 3, 'dropped': 4}

    def sort_key(t: trend_import.TrendTerm):
        status = status_by_term.get(t.key(), 'stable')
        return (order.get(status, 2), t.rank if t.rank is not None else 999)

    return sorted(snapshot.terms, key=sort_key), status_by_term


def _scene_for_trend_term(term: trend_import.TrendTerm) -> str:
    return (
        f"A premium commercial stock photograph built around the trending theme "
        f"'{term.term}', realistic documentary composition, natural lighting, "
        f"no readable text or logos"
    )


def select_concepts_detailed(day: str, n: int) -> list[Concept]:
    snapshot = _latest_fresh_snapshot()
    concepts: list[Concept] = []

    if snapshot is not None:
        ordered_terms, status_by_term = _trend_priority_terms(snapshot)
        slots = min(n, config.TREND_PRIORITY_SLOTS_MAX)
        seen_terms: set[str] = set()
        for term in ordered_terms:
            if len(concepts) >= slots:
                break
            key = term.key()
            if key in seen_terms:
                continue
            seen_terms.add(key)
            concepts.append(Concept(
                category=term.category or 'trending',
                scene=_scene_for_trend_term(term),
                source='trend_snapshot',
                trend_term=term.term,
                trend_status=status_by_term.get(key, 'stable'),
                trend_snapshot_imported_at=snapshot.imported_at,
            ))

    concepts.extend(_calendar_opportunity_concepts(day, n - len(concepts)))

    pool = _static_pool(day)
    i = 0
    while len(concepts) < n and pool:
        cat, scene = pool[i % len(pool)]
        concepts.append(Concept(category=cat, scene=scene, source='static_topic_bank'))
        i += 1

    return concepts[:n]


def _calendar_opportunity_concepts(day: str, remaining_slots: int) -> list[Concept]:
    """Pulls briefs from the trend_intelligence feed whose production
    window covers `day`, highest opportunity_score first, up to
    config.CALENDAR_OPPORTUNITY_SLOTS_MAX. Import is local/lazy so this
    module (and the rest of the pipeline) still works if the
    trend_intelligence package or its feed is absent."""
    if remaining_slots <= 0:
        return []
    try:
        from .trend_intelligence import feed as feed_mod
    except ImportError:
        return []

    feed = feed_mod.load_feed()
    if feed_mod.is_feed_stale(feed):
        return []

    try:
        day_date = date.fromisoformat(day)
    except ValueError:
        return []

    candidates = []
    for b in feed.get('creative_briefs', []):
        if b.get('format') != 'PHOTO_JPG':
            continue  # this pipeline's active generation path is photo today
        start = b.get('production_window_start')
        end = b.get('production_window_end')
        if not (start and end and start <= day <= end):
            continue
        candidates.append(b)
    candidates.sort(key=lambda b: b.get('opportunity_score', 0), reverse=True)

    slots = min(remaining_slots, config.CALENDAR_OPPORTUNITY_SLOTS_MAX)
    seen_events: set[str] = set()
    concepts = []
    for b in candidates:
        if len(concepts) >= slots:
            break
        ev_key = f'{b.get("event_country")}:{b.get("event_name")}'
        if ev_key in seen_events:
            continue
        seen_events.add(ev_key)
        concepts.append(Concept(
            category=f'calendar:{b.get("event_name", "")}',
            scene=b.get('creative_concept', b.get('event_name', '')),
            source='calendar_opportunity',
            opportunity_score=b.get('opportunity_score'),
            event_country=b.get('event_country'),
        ))
    return concepts
