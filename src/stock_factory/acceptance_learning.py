"""Acceptance/rejection learning records (Quality & Learning system).

Imports the real known Magnific baseline as a starting point. Platform
rejection reasons that are only ever reported as a generic "Quality
standards" are recorded as such -- we do not invent a specific cause the
platform never gave.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path

# Verified baseline supplied by the account owner (not fetched from an API).
MAGNIFIC_BASELINE = {
    'submitted': 179,
    'published': 125,
    'rejected': 54,
    'acceptance_rate': 0.698,
    'source': 'owner-reported account totals',
}

# Rejection categories this pipeline can actually detect automatically today.
# Anything not in this set (e.g. a bare "Quality standards" platform message)
# stays UNSPECIFIED_PLATFORM_REASON rather than being guessed at.
KNOWN_REJECTION_CATEGORIES = [
    'weak_anatomy',
    'ai_artifacts',
    'unnatural_texture',
    'unusable_composition',
    'incorrect_or_fake_text',
    'copyright_trademark_risk',
    'duplicate_or_near_duplicate',
    'technically_invalid_file',
    'low_value_variation',
    'unspecified_platform_reason',
]


@dataclass
class RejectionRecord:
    asset_id: str
    platform: str                 # 'adobe' | 'magnific'
    category: str                 # one of KNOWN_REJECTION_CATEGORIES
    platform_message: str | None  # verbatim reason text from the platform, if any
    detected_automatically: bool


class LearningStore:
    """Append-only JSONL ledger of accept/reject outcomes, for later analysis.
    Does not train or claim any model -- it is a record, not a classifier."""

    def __init__(self, state_dir: Path):
        self.path = state_dir / 'acceptance_learning.jsonl'
        state_dir.mkdir(parents=True, exist_ok=True)

    def record_rejection(self, rec: RejectionRecord) -> None:
        if rec.category not in KNOWN_REJECTION_CATEGORIES:
            raise ValueError(f'unknown rejection category: {rec.category}')
        with self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(rec)) + '\n')

    def record_acceptance(self, asset_id: str, platform: str) -> None:
        with self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'asset_id': asset_id, 'platform': platform, 'outcome': 'accepted'}) + '\n')

    def load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def summary(self) -> dict:
        rows = self.load_all()
        accepted = sum(1 for r in rows if r.get('outcome') == 'accepted')
        rejected = [r for r in rows if 'category' in r]
        by_category: dict[str, int] = {}
        for r in rejected:
            by_category[r['category']] = by_category.get(r['category'], 0) + 1
        return {
            'baseline': MAGNIFIC_BASELINE,
            'logged_accepted': accepted,
            'logged_rejected': len(rejected),
            'logged_rejection_by_category': by_category,
        }
