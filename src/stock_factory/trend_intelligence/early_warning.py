"""Rolling early-warning scan over the global event calendar.

Scans a 365-day rolling horizon across 7/30/60/90/180/365-day windows and
raises alerts at 120/90/60/30 days out, adjusted for a platform's realistic
review lead time (Magnific review SLA is documented at <=25 working days,
~35 calendar days -- see docs/PLATFORM_RULES.md -- so an alert inside that
margin is flagged URGENT rather than just NOTICE)."""
from __future__ import annotations
import datetime as _dt
from dataclasses import dataclass

from .events import Event
from . import deadlines

# The scan looks exactly HORIZON_DAYS ahead of the scan date, across every
# calendar year that range touches (an Aug 1 scan must see Jan-Jul of the
# following year). Events before the scan date or after the horizon end
# are never indexed, scored, alerted on, or briefed.
HORIZON_DAYS = 365
SCAN_WINDOWS_DAYS = (7, 30, 60, 90, 180, HORIZON_DAYS)
ALERT_THRESHOLDS_DAYS = (120, 90, 60, 30)

# Lead times come from the single shared date model in deadlines.py
# (buyer lead + platform review + submission prep + production). Kept as
# module names for backward compatibility; do not redefine them here.
PLATFORM_REVIEW_LEAD_DAYS = deadlines.PLATFORM_REVIEW_DAYS
PRODUCTION_BUFFER_DAYS = deadlines.PRODUCTION_DAYS
TOTAL_LEAD_DAYS = deadlines.total_lead_days()


@dataclass
class Alert:
    event: Event
    days_out: int
    threshold_days: int
    urgency: str  # 'ok' | 'notice' | 'urgent' | 'late'

    def to_dict(self) -> dict:
        d = self.event.to_dict()
        d.update(days_out=self.days_out, threshold_days=self.threshold_days, urgency=self.urgency)
        return d


def windowed_events(events: list[Event], today: _dt.date) -> dict[int, list[Event]]:
    """Buckets events into each rolling window (7/30/60/.../365 days from
    `today`); an event appears in every window it fits, not just the
    smallest, since callers scan all windows independently."""
    buckets: dict[int, list[Event]] = {w: [] for w in SCAN_WINDOWS_DAYS}
    for e in events:
        delta = (e.event_date - today).days
        for w in SCAN_WINDOWS_DAYS:
            if 0 <= delta <= w:
                buckets[w].append(e)
    return buckets


def alerts_for(events: list[Event], today: _dt.date) -> list[Alert]:
    """One alert per event whose days-out matches (or has just passed) one
    of ALERT_THRESHOLDS_DAYS, i.e. the day the production team should be
    told 'you have N days left, lead time needed is ~TOTAL_LEAD_DAYS'."""
    alerts = []
    for e in events:
        days_out = (e.event_date - today).days
        if days_out < 0:
            continue
        for threshold in ALERT_THRESHOLDS_DAYS:
            if days_out == threshold:
                # Plenty of margin if the threshold itself clears the total
                # lead time needed; otherwise this is already tight.
                status = deadlines.schedule_for(e.event_date).status(today)
                urgency = {deadlines.ON_TIME: 'ok', deadlines.COMPRESSED: 'urgent', deadlines.LATE: 'late'}[status]
                alerts.append(Alert(event=e, days_out=days_out, threshold_days=threshold, urgency=urgency))
    return alerts


def missed_opportunity_check(events: list[Event], today: _dt.date) -> list[dict]:
    """For every event within the next TOTAL_LEAD_DAYS that has NOT yet
    crossed a 120/90/60/30-day alert threshold from `today`'s vantage point
    in the *past* (i.e. today is already inside the lead-time window but no
    prior alert would have fired), flags it as a missed opportunity -- the
    scenario the brief's Thanksgiving example describes. In a system run
    daily from >=120 days out this list should normally be empty; a
    non-empty result means today is the first time this event has been
    seen with fewer than TOTAL_LEAD_DAYS remaining."""
    missed = []
    for e in events:
        days_out = (e.event_date - today).days
        # Any threshold larger than days_out has already elapsed (its alert
        # day was earlier than today) -- if we're only seeing this event
        # now, that alert was effectively missed.
        if 0 <= days_out < TOTAL_LEAD_DAYS and any(t > days_out for t in ALERT_THRESHOLDS_DAYS):
            missed.append({
                'event': e.to_dict(),
                'days_out': days_out,
                'lead_time_needed_days': TOTAL_LEAD_DAYS,
                'shortfall_days': TOTAL_LEAD_DAYS - days_out,
                'reason': 'event is inside the required production+review lead time '
                          'with no earlier 120/90/60/30-day alert on record for it',
            })
    return missed
