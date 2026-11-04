"""Stage 8: daily reporting and alerts.

No email/Slack/webhook credentials are configured yet, so alerting is
limited to: (1) a human-readable report file written alongside run state,
and (2) a non-zero process exit when the run fell materially short of
DAILY_TARGET_MIN, which a scheduler (GitHub Actions) surfaces as a failed
run/notification without any extra integration.
"""
from __future__ import annotations
from pathlib import Path
from . import config


def render_report(summary: dict) -> str:
    c = summary['counts']
    lines = [
        f"Stock Factory daily report - {summary['day']}",
        f"Target: {config.DAILY_TARGET_MIN}-{config.DAILY_TARGET_STRETCH} images/day",
        f"Fetched:            {c.get('fetched', 0)}",
        f"QC passed:          {c.get('qc_passed', 0)}",
        f"QC rejected:        {c.get('qc_rejected', 0)}",
        f"Duplicate rejected: {c.get('duplicate_rejected', 0)}",
        f"Archived to Drive:  {c.get('archived', 0)}",
        f"Archive skipped:    {c.get('archive_skipped', 0)} (drive_not_configured unless noted otherwise)",
    ]
    if c.get('qc_passed', 0) < config.DAILY_TARGET_MIN:
        lines.append(f"ALERT: qc_passed below DAILY_TARGET_MIN ({config.DAILY_TARGET_MIN}).")
    return '\n'.join(lines)


def write_report(summary: dict, state_dir: Path) -> Path:
    report = render_report(summary)
    path = state_dir / f"report-{summary['day']}.txt"
    path.write_text(report + '\n')
    return path


def shortfall(summary: dict) -> bool:
    return summary['counts'].get('qc_passed', 0) < config.DAILY_TARGET_MIN
