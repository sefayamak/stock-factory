"""Creative briefs for qualifying opportunities, scoped to formats this
repo already has a working production pipeline for."""
from __future__ import annotations
from dataclasses import dataclass, asdict

from .scoring import Score

# This repo's pipeline (prompts.py / processing.py / vector/) only has a
# working path for PHOTO_JPG today, plus an experimental vector module.
# ICON_PACK / PATTERN / DESIGN_BACKGROUND / ILLUSTRATION have no production
# pipeline wired yet -- do not activate them here (see
# docs/GLOBAL_TREND_INTELLIGENCE.md for the gap list).
SUPPORTED_FORMATS = ('PHOTO_JPG', 'VECTOR_EPS')


@dataclass
class CreativeBrief:
    event_country: str
    event_name: str
    format: str
    demand_evidence: str
    demand_source: str
    production_window_start: str
    production_window_end: str
    creative_concept: str
    differentiation_strategy: str
    quantity_recommendation: int
    qc_ip_risk_notes: str
    title: str
    keywords: list[str]
    target_platform: str
    opportunity_score: float

    def to_dict(self) -> dict:
        return asdict(self)


def _window(score: Score, lead_days: int) -> tuple[str, str]:
    end = score.event.event_date
    import datetime as _dt
    start = end - _dt.timedelta(days=lead_days)
    return start.isoformat(), end.isoformat()


def _quantity(score: Score) -> int:
    if score.total >= 0.75:
        return 12
    if score.total >= 0.6:
        return 6
    if score.total >= 0.45:
        return 3
    return 1


def build_brief(score: Score, fmt: str, lead_days: int = 49) -> CreativeBrief:
    e = score.event
    start, end = _window(score, lead_days)
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
        format=fmt,
        demand_evidence=f'{score.demand_label} (score {score.total:.2f}/1.0, see factors)',
        demand_source=e.source,
        production_window_start=start,
        production_window_end=end,
        creative_concept=_concept_for(e, fmt),
        differentiation_strategy='Specific, culturally-accurate scene (named local custom/detail) rather than '
                                  'a generic/stock-looking holiday scene; avoid duplicating the static topic bank.',
        quantity_recommendation=_quantity(score),
        qc_ip_risk_notes=' '.join(risk_notes),
        title=f'{e.english_name} themed {"photograph" if fmt == "PHOTO_JPG" else "vector illustration"}',
        keywords=keywords,
        target_platform='adobe_and_magnific',
        opportunity_score=round(score.total, 4),
    )


def _concept_for(event, fmt: str) -> str:
    base = event.cultural_context or f'Scene built around {event.english_name}.'
    if fmt == 'VECTOR_EPS':
        return f'Flat/vector illustration capturing: {base} Clean editable paths, no raster embeds, no live-traced photo.'
    return f'Documentary-style photograph capturing: {base} Natural light, authentic unposed moment, no readable text/logos.'


def qualifying_briefs(scores: list[Score], min_score: float = 0.45, top_n: int = 25) -> list[CreativeBrief]:
    briefs = []
    for score in [s for s in scores if s.total >= min_score][:top_n]:
        for fmt in SUPPORTED_FORMATS:
            briefs.append(build_brief(score, fmt))
    return briefs
