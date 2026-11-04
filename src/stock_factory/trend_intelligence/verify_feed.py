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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--fail-soft', action='store_true',
                         help='Always exit 0 (log-only); use when the caller wants to '
                              'continue the pipeline without the feed rather than abort.')
    parser.add_argument('--max-age-days', type=int, default=2)
    args = parser.parse_args()

    feed = feed_mod.load_feed()
    problems: list[str] = []

    if feed is None:
        problems.append('FEED_MISSING: no state/intelligence/feed.json present after fetch')
    else:
        integrity_ok, integrity_msg = feed_mod.verify_integrity()
        if not integrity_ok:
            problems.append(f'FEED_INTEGRITY_FAILED: {integrity_msg}')
        if feed_mod.is_feed_stale(feed, max_age_days=args.max_age_days):
            problems.append(f'FEED_STALE: scan_date={feed.get("scan_date")} '
                             f'(older than {args.max_age_days} day(s))')
        provenance = feed.get('provenance', {})
        if not provenance.get('git_sha'):
            problems.append('FEED_SOURCE_UNIDENTIFIED: provenance.git_sha is empty -- '
                             'feed was not produced by a traceable workflow run')
        else:
            print(f'[feed-verify] source identified: git_sha={provenance.get("git_sha")} '
                  f'run_id={provenance.get("workflow_run_id")} workflow={provenance.get("workflow")}')

    if problems:
        for p in problems:
            print(f'::warning::[feed-verify] {p}', file=sys.stderr)
        print('[feed-verify] FAIL-SAFE FALLBACK: production will proceed using the static '
              'topic bank / any fresh trend_snapshot only -- calendar-based opportunity '
              'concepts are skipped for this run.', file=sys.stderr)
        return 0 if args.fail_soft else 1

    print(f'[feed-verify] PASS: feed is fresh (scan_date={feed["scan_date"]}), '
          f'integrity-verified, and source-identified. '
          f'events_indexed={feed["events_indexed"]} briefs={len(feed["creative_briefs"])}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
