"""Explainable, deterministic commercial-opportunity score for one Event.

Every factor is a 0-1 heuristic derived from data this repo actually has
(the event calendar, the Magnific baseline acceptance rate) or from
documented, named assumptions -- never a fabricated "observed sales"
number. `Score.explain()` lists each factor's value and weight so a human
can audit why an event ranked where it did.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .events import Event
from .. import acceptance_learning

# Weights sum to 1.0. Chosen to prioritize evidence-backed and
# high-urgency opportunities over broad-but-generic ones.
WEIGHTS = {
    'market_size': 0.15,
    'demand_evidence': 0.25,
    'seasonal_urgency': 0.15,
    'competition_gap': 0.10,
    'buyer_intent': 0.15,
    'cultural_accuracy_risk': 0.10,   # inverted: higher risk -> lower score
    'portfolio_coverage': 0.10,       # inverted: already well-covered -> lower score
}

# Rough relative market-size weighting by country (population/commercial
# stock-buyer-base proxy, coarse 0-1 scale) -- an explicit, documented
# assumption, not a licensed market-research figure.
_MARKET_SIZE_BY_COUNTRY = {
    'US': 1.0, 'GB': 0.55, 'DE': 0.55, 'FR': 0.5, 'CN': 0.9, 'IN': 0.85,
    'JP': 0.55, 'BR': 0.55, 'CA': 0.4, 'AU': 0.35, 'MX': 0.4, 'ES': 0.35,
    'IT': 0.35, 'KR': 0.35, 'ID': 0.4, 'TR': 0.35, 'SA': 0.3, 'ZA': 0.25,
    'EG': 0.3, 'NG': 0.3, 'AR': 0.25, 'TH': 0.3, 'NZ': 0.2, 'IL': 0.2, 'IR': 0.2,
    'GLOBAL': 0.6,
}

_HIGH_DEMAND_MARKERS = (
    'christmas', 'thanksgiving', 'diwali', 'eid', 'lunar new year', 'hanukkah',
    'black friday', 'cyber monday', "women's day", 'halloween', 'valentine',
)


@dataclass
class Score:
    event: Event
    total: float
    factors: dict[str, float] = field(default_factory=dict)
    demand_label: str = 'calendar_based_predicted_demand'  # vs 'verified_search_demand'

    def explain(self) -> list[str]:
        lines = [f'{k}: value={v:.2f} weight={WEIGHTS[k]:.2f} contrib={v * WEIGHTS[k]:.3f}'
                  for k, v in self.factors.items()]
        lines.append(f'TOTAL = {self.total:.3f} (demand basis: {self.demand_label})')
        return lines

    def to_dict(self) -> dict:
        return {
            'event': self.event.to_dict(),
            'total_score': round(self.total, 4),
            'demand_basis': self.demand_label,
            'factors': {k: round(v, 4) for k, v in self.factors.items()},
            'explanation': self.explain(),
        }


def _demand_evidence(event: Event, verified_terms: set[str] | None) -> tuple[float, str]:
    """Returns (value, label). If a fresh verified-trend snapshot term
    matches this event's name, use that (still heuristic, but backed by a
    real imported snapshot) and label it verified; otherwise fall back to
    a calendar-based heuristic and label it predicted. Never claims a
    predicted value is observed/verified demand."""
    if verified_terms:
        name_low = event.english_name.lower()
        if any(t in name_low or name_low in t for t in verified_terms):
            return 0.9, 'verified_search_demand'
    name_low = event.english_name.lower()
    if any(m in name_low for m in _HIGH_DEMAND_MARKERS):
        return 0.8, 'calendar_based_predicted_demand'
    if event.category == 'national_holiday':
        return 0.6, 'calendar_based_predicted_demand'
    if event.category == 'religious_cultural':
        return 0.65, 'calendar_based_predicted_demand'
    if event.category == 'retail_campaign':
        return 0.85, 'calendar_based_predicted_demand'
    if event.category == 'un_observance':
        return 0.4, 'calendar_based_predicted_demand'
    if event.category == 'season':
        return 0.5, 'calendar_based_predicted_demand'
    return 0.3, 'calendar_based_predicted_demand'


def _seasonal_urgency(days_out: int) -> float:
    if days_out < 0:
        return 0.0
    if days_out <= 30:
        return 1.0
    if days_out <= 60:
        return 0.8
    if days_out <= 90:
        return 0.6
    if days_out <= 120:
        return 0.4
    return 0.2


def _cultural_accuracy_risk(event: Event) -> float:
    """0 = low risk (safe to generalize), 1 = high risk (requires careful,
    specific research -- e.g. religious/regional symbolism mistakes are a
    real rejection and brand-harm risk)."""
    if event.category == 'religious_cultural':
        return 0.8
    if event.category == 'un_observance' and 'violence' in event.english_name.lower():
        return 0.9
    if event.category == 'regional_festival':
        return 0.6
    return 0.3


def _portfolio_coverage(event: Event, existing_topics: set[str] | None) -> float:
    """0 = not covered yet (good, room for differentiated new content),
    1 = already heavily covered by the static topic bank / prior runs."""
    if not existing_topics:
        return 0.0
    name_low = event.english_name.lower()
    return 1.0 if any(t in name_low or name_low in t for t in existing_topics) else 0.0


def score_event(
    event: Event,
    today,
    verified_trend_terms: set[str] | None = None,
    existing_topics: set[str] | None = None,
) -> Score:
    days_out = (event.event_date - today).days
    market_size = _MARKET_SIZE_BY_COUNTRY.get(event.country, 0.3)
    demand, demand_label = _demand_evidence(event, verified_trend_terms)
    seasonal_urgency = _seasonal_urgency(days_out)
    # Competition/gap: no licensed competitive-intelligence feed exists, so
    # this uses the one real signal the repo has -- the Magnific baseline
    # acceptance rate -- as a portfolio-quality-bar proxy: a lower
    # historical acceptance rate implies a higher bar as a mild caution,
    # not a competition measurement. Documented limitation, see docs.
    competition_gap = round(acceptance_learning.MAGNIFIC_BASELINE['acceptance_rate'], 2)
    buyer_intent = 0.9 if event.category == 'retail_campaign' else (
        0.7 if event.category in ('national_holiday', 'religious_cultural') else 0.4
    )
    cultural_risk = _cultural_accuracy_risk(event)
    portfolio_coverage = _portfolio_coverage(event, existing_topics)

    factors = {
        'market_size': market_size,
        'demand_evidence': demand,
        'seasonal_urgency': seasonal_urgency,
        'competition_gap': competition_gap,
        'buyer_intent': buyer_intent,
        'cultural_accuracy_risk': 1.0 - cultural_risk,
        'portfolio_coverage': 1.0 - portfolio_coverage,
    }
    total = sum(factors[k] * WEIGHTS[k] for k in WEIGHTS)
    return Score(event=event, total=total, factors=factors, demand_label=demand_label)


def score_events(
    events: list[Event],
    today,
    verified_trend_terms: set[str] | None = None,
    existing_topics: set[str] | None = None,
) -> list[Score]:
    scored = [score_event(e, today, verified_trend_terms, existing_topics) for e in events]
    return sorted(scored, key=lambda s: s.total, reverse=True)
