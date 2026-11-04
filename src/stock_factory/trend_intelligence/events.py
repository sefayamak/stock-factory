"""Shared Event type for the global trend intelligence calendar."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import date


@dataclass
class Event:
    country: str              # ISO 3166-1 alpha-2, or 'GLOBAL' for worldwide observances
    event_date: date
    local_name: str
    english_name: str
    category: str             # 'national_holiday' | 'religious_cultural' | 'un_observance' |
                               # 'season' | 'retail_campaign' | 'regional_festival'
    source: str                # where the date came from (library/dataset + citation)
    verified_at: str           # ISO date the underlying SOURCE was last actually verified
                               # ('' = computed/derived, not independently verified). This is
                               # NOT the scan date -- see feed.source_verification.
    region: str = ''           # subdivision, if any; '' = whole country
    timezone: str = ''         # IANA tz, best-effort, '' if not resolvable
    cultural_context: str = ''
    commercial_relevance: str = ''  # short human-readable note, not a numeric claim
    hemisphere: str = ''       # 'N' | 'S' | '' -- relevant for season events

    def key(self) -> str:
        return f'{self.country}:{self.event_date.isoformat()}:{self.english_name.strip().lower()}'

    def to_dict(self) -> dict:
        d = asdict(self)
        d['event_date'] = self.event_date.isoformat()
        return d

    @staticmethod
    def from_dict(d: dict) -> 'Event':
        d = dict(d)
        d['event_date'] = date.fromisoformat(d['event_date'])
        return Event(**d)
