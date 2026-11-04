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
from . import deadlines, alert_history

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
    threshold_days: int                 # tightest threshold crossed by this alert
    urgency: str                        # 'ok' | 'urgent' | 'late' (from deadlines.Schedule.status)
    thresholds_crossed: tuple = ()      # every not-yet-alerted threshold this alert covers
    catch_up: bool = False              # True if the exact threshold day was missed (scan gap / first sight)

    def to_dict(self) -> dict:
        d = self.event.to_dict()
        d.update(days_out=self.days_out, threshold_days=self.threshold_days, urgency=self.urgency,
                 thresholds_crossed=list(self.thresholds_crossed), catch_up=self.catch_up)
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


_URGENCY = {deadlines.ON_TIME: 'ok', deadlines.COMPRESSED: 'urgent', deadlines.LATE: 'late'}


def evaluate(events: list[Event], today: _dt.date, history: dict) -> tuple[list[Alert], list[dict]]:
    """Stateful early-warning pass over `events`, reading and UPDATING
    `history` (see alert_history.py; caller persists it).

    Alerts: a threshold counts as crossed once days_out <= threshold, not
    only on the exact day -- so a scan gap that skips the threshold day
    still alerts. Each threshold alerts exactly once per event: thresholds
    already in history are never re-alerted, and several thresholds
    crossed during one gap produce ONE alert (catch_up=True) listing them.

    Missed opportunities: an event whose production_start has passed
    (schedule status COMPRESSED or LATE) with NO alert recorded before
    this scan and no active production status. Reported once (the first
    scan that detects it). production_status is reported as recorded --
    'unknown' unless something set it, never a false "not produced".
    Missed is computed BEFORE this scan's alerts are recorded, so a
    first-sight catch-up alert does not hide that the window was missed."""
    alerts: list[Alert] = []
    missed: list[dict] = []
    for e in events:
        days_out = (e.event_date - today).days
        if days_out < 0:
            continue
        rec = alert_history.record_for(history, e, today)
        schedule = deadlines.schedule_for(e.event_date)
        status = schedule.status(today)
        prior_alerts = [a for a in rec['alerts'] if a.get('date', '') < today.isoformat()]
        production_status = rec.get('production_status') or 'unknown'

        if (status != deadlines.ON_TIME and not prior_alerts and not rec['alerted_thresholds']
                and production_status not in alert_history.ACTIVE_PRODUCTION_STATUSES
                and not rec.get('missed_reported_on')):
            rec['missed_reported_on'] = today.isoformat()
            missed.append({
                'event': e.to_dict(),
                'days_out': days_out,
                'schedule': schedule.to_dict(today),
                'lead_time_needed_days': TOTAL_LEAD_DAYS,
                'shortfall_days': TOTAL_LEAD_DAYS - days_out,
                'production_status': production_status,
                'first_seen': rec['first_seen'],
                'reason': 'production start date has passed and no earlier lead-time alert is on '
                          'record for this event (production status: ' + production_status + ')',
            })

        pending = sorted((t for t in ALERT_THRESHOLDS_DAYS
                          if days_out <= t and t not in rec['alerted_thresholds']), reverse=True)
        if pending:
            tightest = pending[-1]
            alert = Alert(event=e, days_out=days_out, threshold_days=tightest, urgency=_URGENCY[status],
                          thresholds_crossed=tuple(pending), catch_up=days_out != tightest)
            alerts.append(alert)
            rec['alerted_thresholds'] = sorted(set(rec['alerted_thresholds']) | set(pending), reverse=True)
            rec['alerts'].append({'date': today.isoformat(), 'thresholds': pending, 'catch_up': alert.catch_up})
    return alerts, missed


def alerts_for(events: list[Event], today: _dt.date, history: dict | None = None) -> list[Alert]:
    """Alerts for this scan. Without `history`, behaves as a first-ever
    scan (empty history). Mutates `history` when one is passed."""
    history = history if history is not None else alert_history._empty('ephemeral')
    return evaluate(events, today, history)[0]


def missed_opportunity_check(events: list[Event], today: _dt.date, history: dict | None = None) -> list[dict]:
    """Missed opportunities as of `today` (see evaluate). Without
    `history`, behaves as a first-ever scan. Does NOT mutate a passed
    history (works on a copy) -- use evaluate() in the real scan."""
    import copy
    history = copy.deepcopy(history) if history is not None else alert_history._empty('ephemeral')
    return evaluate(events, today, history)[1]
