"""Single production/submission date model for every calendar opportunity.

Scoring, briefs, early-warning alerts and the trends.py consumer all derive
their dates from `schedule_for()` -- no module computes its own
"event_date - N" window any more.

Working backwards from the event date:

    event_date
      - BUYER_LEAD_DAYS        -> buyer_ready_date     (content must be live
                                                        and searchable by then;
                                                        buyers license seasonal
                                                        content weeks ahead)
      - PLATFORM_REVIEW_DAYS   -> submission_deadline  (last day to submit so
                                                        review completes by
                                                        buyer_ready_date)
      - SUBMISSION_PREP_DAYS   -> production_deadline  (generation + QC +
                                                        processing done)
      - PRODUCTION_DAYS        -> production_start

All four durations are module constants, overridable via environment
variables, so operators can tune them without code changes. Defaults are
documented assumptions, not measured platform data:
  - PLATFORM_REVIEW_DAYS=35: Magnific review SLA <=25 working days ~= 35
    calendar days (docs/PLATFORM_RULES.md).
  - BUYER_LEAD_DAYS=21: assumption -- buyers search seasonal content
    weeks before the event; not measured for this account.
  - PRODUCTION_DAYS=14, SUBMISSION_PREP_DAYS=2: assumption for this
    pipeline's generate/QC/process/upload cycle.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import date, timedelta

BUYER_LEAD_DAYS = int(os.getenv('TI_BUYER_LEAD_DAYS', '21'))
PLATFORM_REVIEW_DAYS = int(os.getenv('TI_PLATFORM_REVIEW_DAYS', '35'))
SUBMISSION_PREP_DAYS = int(os.getenv('TI_SUBMISSION_PREP_DAYS', '2'))
PRODUCTION_DAYS = int(os.getenv('TI_PRODUCTION_DAYS', '14'))

ON_TIME = 'on_time'        # today <= production_start: full production time available
COMPRESSED = 'compressed'  # production_start < today <= submission_deadline: still submittable, less time
LATE = 'late'              # today > submission_deadline: cannot reach buyers in time -> blocked


def total_lead_days() -> int:
    return BUYER_LEAD_DAYS + PLATFORM_REVIEW_DAYS + SUBMISSION_PREP_DAYS + PRODUCTION_DAYS


@dataclass(frozen=True)
class Schedule:
    event_date: date
    buyer_ready_date: date
    submission_deadline: date
    production_deadline: date
    production_start: date

    def status(self, today: date) -> str:
        if today > self.submission_deadline:
            return LATE
        if today > self.production_start:
            return COMPRESSED
        return ON_TIME

    def to_dict(self, today: date | None = None) -> dict:
        d = {
            'event_date': self.event_date.isoformat(),
            'buyer_ready_date': self.buyer_ready_date.isoformat(),
            'submission_deadline': self.submission_deadline.isoformat(),
            'production_deadline': self.production_deadline.isoformat(),
            'production_start': self.production_start.isoformat(),
        }
        if today is not None:
            d['status'] = self.status(today)
        return d


def schedule_for(event_date: date) -> Schedule:
    # Read the module constants at call time so tests/operators can override them.
    buyer_ready = event_date - timedelta(days=BUYER_LEAD_DAYS)
    submission_deadline = buyer_ready - timedelta(days=PLATFORM_REVIEW_DAYS)
    production_deadline = submission_deadline - timedelta(days=SUBMISSION_PREP_DAYS)
    production_start = production_deadline - timedelta(days=PRODUCTION_DAYS)
    return Schedule(
        event_date=event_date,
        buyer_ready_date=buyer_ready,
        submission_deadline=submission_deadline,
        production_deadline=production_deadline,
        production_start=production_start,
    )


def config_dict() -> dict:
    return {
        'buyer_lead_days': BUYER_LEAD_DAYS,
        'platform_review_days': PLATFORM_REVIEW_DAYS,
        'submission_prep_days': SUBMISSION_PREP_DAYS,
        'production_days': PRODUCTION_DAYS,
        'total_lead_days': total_lead_days(),
        'note': 'Defaults are documented assumptions (see deadlines.py), overridable via TI_* env vars.',
    }
