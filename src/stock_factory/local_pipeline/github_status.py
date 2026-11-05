"""Session-end / lane-end status reporting.

Writes a status snapshot to state/daily_summary/<day>_status.md (always,
local, reversible). Posting that content to GitHub (an issue comment, a
commit) is a distinct, visible-to-others action -- per operating policy
this needs the operator's explicit go-ahead each time it's turned on, so
post_to_github() is provided but never called automatically by the
orchestrator. Wire it into a script invocation only after the operator
says to.
"""
from __future__ import annotations
import subprocess
from pathlib import Path

from .. import config


def build_status_markdown(day: str, summary: dict, branch: str, next_step: str, blockers: list[str]) -> str:
    lines = [
        f'# Stock Factory local pipeline -- status for {day}',
        '',
        f'- branch/worktree: `{branch}`',
        f'- target: {summary["target"]["total"]} '
        f'({summary["target"]["photo"]} photo / {summary["target"]["illustration"]} illustration)',
        f'- queued: {summary["queued"]}',
        f'- archived: {summary["archived"]}',
        f'- uploaded to Magnific: {summary["uploaded"]}',
        f'- failed/blocked: {summary["failed"]}',
        '',
        '## By status',
        *(f'- {k}: {v}' for k, v in sorted(summary['by_status'].items())),
        '',
        '## By provider',
        *(f'- {k}: {v}' for k, v in sorted(summary['by_provider'].items())),
        '',
        '## Blockers',
        *([f'- {b}' for b in blockers] if blockers else ['- none']),
        '',
        '## Next step',
        next_step,
    ]
    return '\n'.join(lines)


def write_status_file(day: str, markdown: str) -> Path:
    out_dir = config.LOCAL_PIPELINE_STATE_DIR / 'daily_summary'
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'{day}_status.md'
    path.write_text(markdown)
    return path


def post_to_github(markdown: str, repo: str, issue_number: int) -> None:
    """Not called by the orchestrator automatically -- see module
    docstring. Requires `gh` to be authenticated on this machine."""
    subprocess.run(
        ['gh', 'issue', 'comment', str(issue_number), '--repo', repo, '--body-stdin'],
        input=markdown, text=True, check=True,
    )
