#!/usr/bin/env python3
"""Entrypoint for the local-PC-driven production pipeline. Run this on
the always-on operator machine (see local_pipeline/providers/base.py for
why it cannot generate images when run from a cloud session)."""
import sys
from datetime import date, timezone, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from stock_factory.local_pipeline.orchestrator import run_daily
from stock_factory.local_pipeline import github_status


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).date().isoformat()
    summary = run_daily(day)

    blockers = []
    if summary['by_status'].get('blocked_provider_not_implemented'):
        blockers.append(
            f"{summary['by_status']['blocked_provider_not_implemented']} items blocked: "
            "google_flow/midjourney browser providers not yet implemented (Phase 2/5)."
        )

    markdown = github_status.build_status_markdown(
        day, summary, branch='feature/local-production-pipeline',
        next_step='Implement Phase 2 (Google Flow browser provider) on the operator machine.',
        blockers=blockers,
    )
    path = github_status.write_status_file(day, markdown)
    print(f'Status written to {path}')
    print(markdown)


if __name__ == '__main__':
    main()
