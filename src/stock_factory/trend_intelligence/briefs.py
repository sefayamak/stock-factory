"""Creative briefs for qualifying opportunities, scoped to formats this
repo already has a working production pipeline for."""
from __future__ import annotations
from dataclasses import dataclass, asdict

from .scoring import Score
from . import deadlines

# This repo's pipeline (prompts.py / processing.py / vector/) only has a
# working path for PHOTO_JPG today, plus an experimental vector module.
# ICON_PACK / PATTERN / DESIGN_BACKGROUND / ILLUSTRATION have no production
# pipeline wired yet -- do not activate them here (see
# docs/GLOBAL_TREND_INTELLIGENCE.md for the gap list).
SUPPORTED_FORMATS = ('PHOTO_JPG', 'VECTOR_EPS')

# What actually happens to a brief of each format. Only PHOTO_JPG briefs
# are consumed by trends.py and turned into production jobs. VECTOR_EPS
# briefs are planning output only: creative vector illustration is BLOCKED
# (vector/procedural_vector.BLOCKED_CREATIVE_VECTOR_REASON -- only
# procedural geometric icons/patterns produce real vectors, and nothing
# consumes VECTOR_EPS briefs), so they must never be read as a working EPS
# production pipeline.
FORMAT_PIPELINE_STATUS = {'PHOTO_JPG': 'active', 'VECTOR_EPS': 'planned_blocked'}
FORMAT_PIPELINE_NOTE = {
    'PHOTO_JPG': 'consumed by trends.py -> photo generation pipeline',
    'VECTOR_EPS': 'planning only: no pipeline consumes VECTOR_EPS briefs; creative vector '
                  'generation is blocked (procedural icons/patterns only)',
}


@dataclass
class CreativeBrief:
    event_country: str
    event_name: str
    event_date: str
    format: str
    demand_evidence: str
    demand_source: str
    # Shared date model (deadlines.py) -- identical to the Score's schedule.
    buyer_ready_date: str
    submission_deadline: str
    production_start: str
    production_deadline: str
    schedule_status: str
    creative_concept: str
    differentiation_strategy: str
    quantity_recommendation: int
    qc_ip_risk_notes: str
    title: str
    keywords: list[str]
    target_platform: str
    opportunity_score: float
    production_pipeline_status: str = 'active'   # FORMAT_PIPELINE_STATUS[format]
    production_pipeline_note: str = ''
    def to_dict(self) -> dict:
        return asdict(self)


def _quantity(score: Score) -> int:
    if score.total >= 0.75:
        return 12
    if score.total >= 0.6:
        return 6
    if score.total >= 0.45:
        return 3
    return 1


def build_brief(score: Score, fmt: str) -> CreativeBrief:
    e = score.event
    sched = score.schedule or deadlines.schedule_for(e.event_date)
    risk_notes = []
    if e.category == 'religious_cultural':
        risk_notes.append('Religious/cultural symbolism must be verified against the specific tradition '
                           '(country/region) before generation -- generic depictions risk both rejection '
                           'and cultural inaccuracy.')
    if score.factors.get('cultural_accuracy_risk', 1.0) < 0.5:
        risk_notes.append('No recognizable logos, trademarks, or identifiable people without release.')
    if not risk_notes:
        risk_notes.append('Standard IP/QC checklist applies (no logos/text/brand references).')

    keywords = [w.strip().lower() for w in e.english_name.replace('(', '').replace(')', '').split() if len(w) > 2][:8]
    keywords = list(dict.fromkeys(keywords + [e.category.replace('_', ' ')]))[:10]

    return CreativeBrief(
        event_country=e.country,
        event_name=e.english_name,
        event_date=e.event_date.isoformat(),
        format=fmt,
        demand_evidence=f'{score.demand_label} (score {score.total:.2f}/1.0, see factors)',
        demand_source=e.source,
        buyer_ready_date=sched.buyer_ready_date.isoformat(),
        submission_deadline=sched.submission_deadline.isoformat(),
        production_start=sched.production_start.isoformat(),
        production_deadline=sched.production_deadline.isoformat(),
        schedule_status=score.schedule_status,
        creative_concept=_concept_for(e, fmt),
        differentiation_strategy='Specific, culturally-accurate scene (named local custom/detail) rather than '
                                  'a generic/stock-looking holiday scene; avoid duplicating the static topic bank.',
        quantity_recommendation=_quantity(score),
        qc_ip_risk_notes=' '.join(risk_notes),
        title=f'{e.english_name} themed {"photograph" if fmt == "PHOTO_JPG" else "vector illustration"}',
        keywords=keywords,
        target_platform='adobe_and_magnific',
        opportunity_score=round(score.total, 4),
        production_pipeline_status=FORMAT_PIPELINE_STATUS.get(fmt, 'planned_blocked'),
        production_pipeline_note=FORMAT_PIPELINE_NOTE.get(fmt, 'no production pipeline for this format'),
    )


def _concept_for(event, fmt: str) -> str:
    base = event.cultural_context or f'Scene built around {event.english_name}.'
    if fmt == 'VECTOR_EPS':
        return f'Flat/vector illustration capturing: {base} Clean editable paths, no raster embeds, no live-traced photo.'
    return f'Documentary-style photograph capturing: {base} Natural light, authentic unposed moment, no readable text/logos.'


def qualifying_briefs(scores: list[Score], min_score: float = 0.45, top_n: int = 25) -> list[CreativeBrief]:
    """LATE opportunities (submission deadline passed) never get a brief:
    they cannot reach buyers in time, so producing them would only burn
    generation budget."""
    briefs = []
    on_time = [s for s in scores if s.schedule_status != deadlines.LATE]
    for score in [s for s in on_time if s.total >= min_score][:top_n]:
        for fmt in SUPPORTED_FORMATS:
            briefs.append(build_brief(score, fmt))
    return briefs
