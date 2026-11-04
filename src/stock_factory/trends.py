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
what gets produced, not just a report nobody reads. A missing, stale
(feed.is_feed_stale, default >2 days old), or integrity-check-failed feed
contributes nothing (fail-safe fallback to the static topic bank), never
a crash -- same stale-data philosophy as the Magnific snapshot above.
"""
from __future__ import annotations
import random
import re
from dataclasses import dataclass, field
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
    event_date: str | None = None      # ISO date of the calendar event (identity, with country + topic)
    topic: str | None = None           # normalize_topic() of the trend term / event name
    merged_sources: list[str] = field(default_factory=list)  # every source tier that proposed this candidate

    def __post_init__(self):
        if not self.merged_sources:
            self.merged_sources = [self.source]
        if self.topic is None:
            raw = self.trend_term if self.trend_term is not None else (
                self.category.split(':', 1)[1] if self.category.startswith('calendar:') else None)
            if raw is not None:
                self.topic = normalize_topic(raw)


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


def normalize_topic(text: str) -> str:
    """Source-independent topic identity: case-, punctuation- and
    whitespace-insensitive ("Black  Friday!" == "black friday")."""
    return ' '.join(re.sub(r"[^\w]+", ' ', text.lower(), flags=re.UNICODE).split())


def _topic_of(concept: Concept) -> str | None:
    return concept.topic


def _dedup_key(concept: Concept) -> str:
    """Source-independent identity of a production candidate.

    Calendar-backed candidates are identified by (normalized topic,
    country/region, event date) -- so the same holiday in two countries,
    on two dates, or in two different years stays distinct. A trend term
    with no event attached is identified by its normalized topic alone.
    The source tier is deliberately NOT part of the key (previously
    'trend:black friday' vs 'event:us:calendar:black friday' never
    collided, so one topic was double-booked). Concepts with neither fall
    back to their scene text."""
    if concept.topic and concept.event_country is not None and concept.event_date:
        return f'event:{concept.topic}|{concept.event_country.lower()}|{concept.event_date}'
    if concept.topic:
        return f'topic:{concept.topic}'
    return f'scene:{concept.scene}'.strip().lower()


def select_concepts_detailed(day: str, n: int) -> list[Concept]:
    snapshot = _latest_fresh_snapshot()
    concepts: list[Concept] = []
    seen: set[str] = set()

    def _add(c: Concept) -> bool:
        key = _dedup_key(c)
        if key in seen:
            return False
        seen.add(key)
        concepts.append(c)
        return True

    if snapshot is not None:
        ordered_terms, status_by_term = _trend_priority_terms(snapshot)
        slots = min(n, config.TREND_PRIORITY_SLOTS_MAX)
        trend_added = 0
        for term in ordered_terms:
            if trend_added >= slots:
                break
            key = term.key()
            candidate = Concept(
                category=term.category or 'trending',
                scene=_scene_for_trend_term(term),
                source='trend_snapshot',
                trend_term=term.term,
                trend_status=status_by_term.get(key, 'stable'),
                trend_snapshot_imported_at=snapshot.imported_at,
            )
            if _add(candidate):
                trend_added += 1

    # Calendar tier. A calendar candidate whose topic equals a trend-tier
    # concept's topic is the SAME production candidate seen by two
    # sources -- but only when that attribution is unambiguous: exactly one
    # calendar candidate (one country, one date) carries that topic today.
    # If several do (e.g. Mother's Day GB vs US), the bare trend term can't
    # be attributed to either, so nothing is merged (err toward separate).
    calendar = _calendar_opportunity_concepts(day)
    calendar_topic_counts: dict[str, int] = {}
    for c in calendar:
        if c.topic:
            calendar_topic_counts[c.topic] = calendar_topic_counts.get(c.topic, 0) + 1
    trend_by_topic = {c.topic: c for c in concepts if c.source == 'trend_snapshot' and c.topic}
    calendar_slots = min(max(n - len(concepts), 0), config.CALENDAR_OPPORTUNITY_SLOTS_MAX)
    calendar_added = 0
    for candidate in calendar:
        if len(concepts) >= n or calendar_added >= calendar_slots:
            break
        trend_twin = trend_by_topic.get(candidate.topic)
        if (trend_twin is not None and calendar_topic_counts.get(candidate.topic) == 1
                and trend_twin.event_country is None):
            seen.discard(_dedup_key(trend_twin))
            trend_twin.event_country = candidate.event_country
            trend_twin.event_date = candidate.event_date
            trend_twin.opportunity_score = candidate.opportunity_score
            trend_twin.merged_sources = trend_twin.merged_sources + ['calendar_opportunity']
            seen.add(_dedup_key(trend_twin))
            continue
        if _add(candidate):
            calendar_added += 1

    # The static topic bank deliberately repeats its ~12 topics to fill the
    # remaining daily volume (target is 100-150/day; the bank is much
    # smaller) -- that repetition is pre-existing, intended behavior, not
    # a "duplicate production candidate". The dedup guard above only
    # applies to named trend/calendar opportunities, where the same event
    # or trending term appearing twice in one day's queue would be a real
    # defect (same concept double-booked).
    pool = _static_pool(day)
    i = 0
    while len(concepts) < n and pool:
        cat, scene = pool[i % len(pool)]
        concepts.append(Concept(category=cat, scene=scene, source='static_topic_bank'))
        i += 1

    return concepts[:n]


def _calendar_opportunity_concepts(day: str) -> list[Concept]:
    """All feed briefs whose production window covers `day`, one per
    (topic, country, event date), highest opportunity_score first. The
    caller applies config.CALENDAR_OPPORTUNITY_SLOTS_MAX after cross-tier
    dedup. Import is local/lazy so this module (and the rest of the
    pipeline) still works if the trend_intelligence package or its feed is
    absent."""
    try:
        from .trend_intelligence import feed as feed_mod
    except ImportError:
        return []

    feed = feed_mod.load_feed()
    if feed_mod.is_feed_stale(feed):
        return []  # fail-safe fallback: missing/stale feed contributes nothing, never a crash
    integrity_ok, _ = feed_mod.verify_integrity()
    if not integrity_ok:
        return []  # fail-safe fallback: a corrupt/tampered feed is treated as absent

    try:
        day_date = date.fromisoformat(day)
    except ValueError:
        return []

    candidates = []
    for b in feed.get('creative_briefs', []):
        if b.get('format') != 'PHOTO_JPG':
            continue  # this pipeline's active generation path is photo today
        # Shared date model (trend_intelligence/deadlines.py): only queue a
        # brief on a day inside [production_start, production_deadline]; a
        # brief past its production deadline (e.g. from a 2-day-old feed)
        # or already late is never produced.
        if b.get('schedule_status') == 'late':
            continue
        start = b.get('production_start')
        end = b.get('production_deadline')
        if not (start and end and start <= day <= end):
            continue
        candidates.append(b)
    candidates.sort(key=lambda b: b.get('opportunity_score', 0), reverse=True)

    seen_events: set[str] = set()
    concepts = []
    for b in candidates:
        c = Concept(
            category=f'calendar:{b.get("event_name", "")}',
            scene=b.get('creative_concept', b.get('event_name', '')),
            source='calendar_opportunity',
            opportunity_score=b.get('opportunity_score'),
            event_country=b.get('event_country'),
            event_date=b.get('event_date'),
        )
        key = _dedup_key(c)  # same identity as cross-tier dedup: topic + country + date
        if key in seen_events:
            continue
        seen_events.add(key)
        concepts.append(c)
    return concepts
