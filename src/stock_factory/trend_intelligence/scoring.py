"""Explainable, deterministic commercial-opportunity score for one Event.

Every factor is a 0-1 heuristic derived from data this repo actually has
(the event calendar, adapter signals, the Magnific baseline acceptance
rate) or from documented, named assumptions -- never a fabricated
"observed sales" number. `Score.explain()` lists each factor's value and
weight so a human can audit why an event ranked where it did.

Four distinct evidence categories feed this module (see
adapters/base.py's SIGNAL_* constants) and must stay distinct:
  - verified_search_interest        -- real search-interest signal (Google/Magnific
                                       search ranks): NOT download/purchase demand
  - catalog_supply                  -- existing-content/competition count
  - calendar_predicted_demand       -- calendar heuristic, no live signal
  - historical_download_performance -- past acceptance/download record
A catalog-supply number is NEVER promoted into the demand factor, and a
demand number is never used as the competition factor -- that conflation
is exactly what earlier produced an incorrect score basis.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math

from .events import Event
from . import deadlines
from .. import acceptance_learning
from .adapters.base import (
    SIGNAL_SEARCH_INTEREST, SIGNAL_CATALOG_SUPPLY,
    SIGNAL_CALENDAR_PREDICTED_DEMAND, SIGNAL_HISTORICAL_DOWNLOAD_PERFORMANCE,
)

# Weights sum to 1.0. Chosen to prioritize evidence-backed and
# high-urgency opportunities over broad-but-generic ones. A factor whose
# input data does not exist is NOT given a stand-in value: it is recorded
# as None ("not_computed" / "unavailable") and excluded, and the total is
# the weighted mean over the factors that WERE computed.
WEIGHTS = {
    'market_size': 0.12,
    'demand_evidence': 0.25,
    'seasonal_urgency': 0.15,
    'competition_gap': 0.13,
    'buyer_intent': 0.12,
    'cultural_accuracy_risk': 0.08,    # inverted: higher risk -> lower score
    'portfolio_coverage': 0.07,        # inverted: already well-covered -> lower score
    'historical_download_performance': 0.08,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, 'WEIGHTS must sum to 1.0'

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


# Factors that are None for lack of data, and how to label them.
_MISSING_LABEL = {
    'historical_download_performance': 'unavailable',  # no download data exists in this repo
    'portfolio_coverage': 'not_computed',               # no portfolio/topic inventory supplied
}


@dataclass
class Score:
    event: Event
    total: float
    factors: dict[str, float] = field(default_factory=dict)
    demand_label: str = SIGNAL_CALENDAR_PREDICTED_DEMAND  # one of the four SIGNAL_* constants
    competition_label: str = 'no_supply_data_available'   # SIGNAL_CATALOG_SUPPLY or this default
    schedule: deadlines.Schedule | None = None  # the shared date model (deadlines.py)
    schedule_status: str = deadlines.ON_TIME     # ON_TIME | COMPRESSED | LATE as of the scan date

    def explain(self) -> list[str]:
        lines = []
        for k, v in self.factors.items():
            if v is None:
                lines.append(f'{k}: {_MISSING_LABEL.get(k, "not_computed")} (excluded from total)')
            else:
                lines.append(f'{k}: value={v:.2f} weight={WEIGHTS[k]:.2f}')
        lines.append(f'TOTAL = {self.total:.3f} (demand basis: {self.demand_label})')
        return lines

    def to_dict(self) -> dict:
        return {
            'event': self.event.to_dict(),
            'total_score': round(self.total, 4),
            'demand_basis': self.demand_label,
            'competition_basis': self.competition_label,
            'schedule': {**(self.schedule.to_dict() if self.schedule else {}), 'status': self.schedule_status},
            'factors': {k: (round(v, 4) if v is not None else _MISSING_LABEL.get(k, 'not_computed'))
                        for k, v in self.factors.items()},
            'explanation': self.explain(),
        }


def _demand_evidence(event: Event, verified_demand_terms: set[str] | None) -> tuple[float, str]:
    """Returns (value, label). `verified_demand_terms` must already be
    filtered to fresh SIGNAL_SEARCH_INTEREST-only terms by the caller (feed.py) --
    this function has no way to re-check that itself, so it trusts the
    contract and never treats a catalog-supply or historical-performance
    term as demand. Falls back to a calendar-based heuristic, clearly
    labeled as predicted, never claimed as observed/verified."""
    if verified_demand_terms:
        name_low = event.english_name.lower()
        if any(t in name_low or name_low in t for t in verified_demand_terms):
            return 0.9, SIGNAL_SEARCH_INTEREST
    name_low = event.english_name.lower()
    if any(m in name_low for m in _HIGH_DEMAND_MARKERS):
        return 0.8, SIGNAL_CALENDAR_PREDICTED_DEMAND
    if event.category == 'national_holiday':
        return 0.6, SIGNAL_CALENDAR_PREDICTED_DEMAND
    if event.category == 'religious_cultural':
        return 0.65, SIGNAL_CALENDAR_PREDICTED_DEMAND
    if event.category == 'retail_campaign':
        return 0.85, SIGNAL_CALENDAR_PREDICTED_DEMAND
    if event.category == 'un_observance':
        return 0.4, SIGNAL_CALENDAR_PREDICTED_DEMAND
    if event.category == 'season':
        return 0.5, SIGNAL_CALENDAR_PREDICTED_DEMAND
    return 0.3, SIGNAL_CALENDAR_PREDICTED_DEMAND


def _competition_gap(event: Event, catalog_supply_by_term: dict[str, float] | None) -> tuple[float, str]:
    """Returns (value, label). value is 0-1, HIGHER meaning LESS
    competition (a gap worth filling). Uses a real catalog_supply count
    (e.g. Adobe Stock nb_results) when available for this event, via a
    log-scale normalization since result counts span orders of magnitude;
    otherwise falls back to a neutral default and labels it explicitly as
    having no supply data, rather than silently reusing an unrelated
    number."""
    if catalog_supply_by_term:
        name_low = event.english_name.lower()
        nb_results = None
        for term, value in catalog_supply_by_term.items():
            if term in name_low or name_low in term:
                nb_results = value
                break
        if nb_results is not None:
            # log10(1)=0 -> gap 1.0 (no existing supply); log10(1e6)=6 -> gap ~0.14.
            gap = 1.0 / (1.0 + math.log10(max(nb_results, 1.0) + 1.0))
            return max(0.0, min(1.0, gap)), SIGNAL_CATALOG_SUPPLY
    return 0.5, 'no_supply_data_available'


def _seasonal_urgency(schedule: deadlines.Schedule, today) -> float:
    """Urgency from the SAME date model briefs use: how soon production
    has to start (not how soon the event is). A LATE opportunity
    (submission deadline passed) has no urgency at all -- it is bucketed
    separately by the feed, never ranked as an on-time candidate."""
    status = schedule.status(today)
    if status == deadlines.LATE:
        return 0.0
    if status == deadlines.COMPRESSED:
        return 1.0
    days_to_start = (schedule.production_start - today).days
    if days_to_start <= 30:
        return 0.8
    if days_to_start <= 60:
        return 0.6
    if days_to_start <= 90:
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


def _portfolio_coverage(event: Event, existing_topics: set[str] | None) -> float | None:
    """0 = not covered yet (good, room for differentiated new content),
    1 = already heavily covered by the static topic bank / prior runs.
    None = not computed: no topic inventory was supplied, so coverage is
    unknown (previously this returned 0.0, i.e. a fake "not covered")."""
    if existing_topics is None:
        return None
    name_low = event.english_name.lower()
    return 1.0 if any(t in name_low or name_low in t for t in existing_topics) else 0.0


def score_event(
    event: Event,
    today,
    verified_demand_terms: set[str] | None = None,
    existing_topics: set[str] | None = None,
    catalog_supply_by_term: dict[str, float] | None = None,
) -> Score:
    schedule = deadlines.schedule_for(event.event_date)
    schedule_status = schedule.status(today)
    market_size = _MARKET_SIZE_BY_COUNTRY.get(event.country, 0.3)
    demand, demand_label = _demand_evidence(event, verified_demand_terms)
    seasonal_urgency = _seasonal_urgency(schedule, today)
    competition_gap, competition_label = _competition_gap(event, catalog_supply_by_term)
    buyer_intent = 0.9 if event.category == 'retail_campaign' else (
        0.7 if event.category in ('national_holiday', 'religious_cultural') else 0.4
    )
    cultural_risk = _cultural_accuracy_risk(event)
    portfolio_coverage = _portfolio_coverage(event, existing_topics)
    # Historical DOWNLOAD performance: no download data exists anywhere in
    # this repo, so this factor is unavailable (None) -- NOT filled with the
    # portfolio-wide Magnific acceptance rate, which measures review
    # acceptance, not downloads, and is identical for every event. That
    # rate is reported separately in the feed as portfolio_acceptance_rate.
    historical_performance = None

    factors = {
        'market_size': market_size,
        'demand_evidence': demand,
        'seasonal_urgency': seasonal_urgency,
        'competition_gap': competition_gap,
        'buyer_intent': buyer_intent,
        'cultural_accuracy_risk': 1.0 - cultural_risk,
        'portfolio_coverage': None if portfolio_coverage is None else 1.0 - portfolio_coverage,
        'historical_download_performance': historical_performance,
    }
    computed = [k for k in WEIGHTS if factors[k] is not None]
    total = sum(factors[k] * WEIGHTS[k] for k in computed) / sum(WEIGHTS[k] for k in computed)
    return Score(event=event, total=total, factors=factors,
                 demand_label=demand_label, competition_label=competition_label,
                 schedule=schedule, schedule_status=schedule_status)


def score_events(
    events: list[Event],
    today,
    verified_demand_terms: set[str] | None = None,
    existing_topics: set[str] | None = None,
    catalog_supply_by_term: dict[str, float] | None = None,
) -> list[Score]:
    scored = [
        score_event(e, today, verified_demand_terms, existing_topics, catalog_supply_by_term)
        for e in events
    ]
    return sorted(scored, key=lambda s: s.total, reverse=True)
