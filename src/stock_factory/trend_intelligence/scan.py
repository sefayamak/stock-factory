"""CLI entrypoint for the daily global-trend-intelligence scan.

    PYTHONPATH=src python -m stock_factory.trend_intelligence.scan

Writes state/intelligence/feed.json (consumed by trends.py) and prints a
short human-readable summary. No paid API calls, no asset generation, no
auto-submission -- this only produces the intelligence feed.
"""
from __future__ import annotations
import sys

from . import feed as feed_mod


def main() -> int:
    feed = feed_mod.run_scan()
    path = feed_mod.write_feed(feed)
    print(f'[trend-intelligence] wrote {path}')
    print(f'[trend-intelligence] events_indexed={feed["events_indexed"]} '
          f'countries={len(feed["countries_covered"])} '
          f'duplicate_groups={feed["duplicate_event_groups"]} '
          f'alerts={len(feed["alerts"])} missed_opportunities={len(feed["missed_opportunities"])} '
          f'briefs={len(feed["creative_briefs"])}')
    for platform, status in feed['adapter_status'].items():
        print(f'[trend-intelligence] adapter[{platform}] = {status}')
    if feed['missed_opportunities']:
        print(f'[trend-intelligence] WARNING: {len(feed["missed_opportunities"])} event(s) inside '
              f'lead time with no prior alert -- see missed_opportunities in the feed.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
