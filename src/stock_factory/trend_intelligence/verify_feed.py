"""CLI used by the main daily production workflow to verify a feed it just
fetched from the persistent `intelligence-feed` branch, BEFORE running the
pipeline. Checks freshness, integrity (checksum), and source identification
(provenance block); on any failure, reports it explicitly and exits
non-zero/zero per --fail-soft, so the caller can choose fail-safe
fallback (proceed without the feed -- `trends.py` already degrades
gracefully to the static topic bank when `load_feed()` returns None/stale)
rather than crashing the whole production run over a stale feed.

    PYTHONPATH=src python -m stock_factory.trend_intelligence.verify_feed [--fail-soft]
"""
from __future__ import annotations
import argparse
import sys

from . import feed as feed_mod

MAX_PROBLEMS_PRINTED = 20


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--fail-soft', action='store_true',
                         help='Always exit 0 (log-only); use when the caller wants to '
                              'continue the pipeline without the feed rather than abort.')
    parser.add_argument('--max-age-days', type=int, default=feed_mod.FEED_MAX_AGE_DAYS)
    args = parser.parse_args()

    # The SAME validator trends.py uses before consuming the feed -- a feed
    # rejected here can never contribute calendar candidates downstream.
    result = feed_mod.validate_feed(max_age_days=args.max_age_days)

    if not result.ok:
        for p in result.problems[:MAX_PROBLEMS_PRINTED]:
            print(f'::warning::[feed-verify] {p}', file=sys.stderr)
        if len(result.problems) > MAX_PROBLEMS_PRINTED:
            print(f'::warning::[feed-verify] ... and {len(result.problems) - MAX_PROBLEMS_PRINTED} more problem(s)',
                  file=sys.stderr)
        print('[feed-verify] FAIL-SAFE FALLBACK: production will proceed using the static '
              'topic bank / any fresh trend_snapshot only -- calendar-based opportunity '
              'concepts are skipped for this run.', file=sys.stderr)
        return 0 if args.fail_soft else 1

    feed = result.feed
    provenance = feed['provenance']
    print(f'[feed-verify] source identified: git_sha={provenance.get("git_sha")} '
          f'run_id={provenance.get("workflow_run_id")} workflow={provenance.get("workflow")}')
    print(f'[feed-verify] PASS: feed is fresh (scan_date={feed["scan_date"]}), '
          f'schema-valid (v{feed["schema_version"]}), integrity-verified, and source-identified. '
          f'events_indexed={feed["events_indexed"]} briefs={len(feed["creative_briefs"])}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
