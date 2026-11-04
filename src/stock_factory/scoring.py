"""Production priority scoring (Intelligence department).

A simple, auditable weighted score over signals named in the directive.
Every input defaults to 0 (neutral/unknown) so a missing signal never
silently dominates the score, and every call tags whether each input was
an observed data point or a stand-in assumption -- the directive requires
distinguishing observed trends from predictions.
"""
from __future__ import annotations
from dataclasses import dataclass, field

WEIGHTS = {
    'demand_evidence': 0.20,
    'competition': -0.10,       # higher competition lowers score
    'commercial_applicability': 0.15,
    'timeliness': 0.10,
    'visual_differentiation': 0.10,
    'production_cost': -0.10,   # higher cost lowers score
    'compliance_risk': -0.15,   # higher risk lowers score
    'historical_acceptance_rate': 0.15,
    'revenue_signal': 0.15,
}


@dataclass
class ScoreInput:
    demand_evidence: float = 0.0
    competition: float = 0.0
    commercial_applicability: float = 0.0
    timeliness: float = 0.0
    visual_differentiation: float = 0.0
    production_cost: float = 0.0
    compliance_risk: float = 0.0
    historical_acceptance_rate: float = 0.0
    revenue_signal: float = 0.0
    observed_fields: set[str] = field(default_factory=set)  # which of the above are real data, not placeholders

    def is_observed(self, field_name: str) -> bool:
        return field_name in self.observed_fields


def score(inputs: ScoreInput) -> dict:
    total = 0.0
    breakdown = {}
    for key, weight in WEIGHTS.items():
        value = getattr(inputs, key)
        contribution = weight * value
        total += contribution
        breakdown[key] = {
            'value': value,
            'weight': weight,
            'contribution': round(contribution, 4),
            'observed': inputs.is_observed(key),
        }
    observed_count = len(inputs.observed_fields)
    return {
        'priority_score': round(total, 4),
        'breakdown': breakdown,
        'observed_signal_count': observed_count,
        'total_signal_count': len(WEIGHTS),
        'confidence': 'observed' if observed_count >= 5 else 'low_confidence_mostly_assumed',
    }
