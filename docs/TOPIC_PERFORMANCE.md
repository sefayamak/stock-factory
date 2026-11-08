# Topic download performance — optional, measured input

The intelligence feed can now incorporate **actual topic-specific downloads** in
opportunity scoring. This is *not* a trend API, a revenue forecast, or automatic
Magnific sales retrieval.

Place `state/intelligence/topic_performance.json` on the scan runner, with:

```json
{
  "source": "owner_verified_platform_export",
  "observed_on": "2026-11-08",
  "topics": [
    {"topic": "Christmas Day", "downloads": 12, "published_asset_days": 1200}
  ]
}
```

- `downloads` must be a verified nonnegative integer.
- `published_asset_days` is exposure, e.g. 40 published files observed
  for 30 days = 1200 asset-days. Do not use impressions or page views.
- The observation must not be future-dated or older than 45 days.
- At least 100 asset-days per topic is required, to avoid exaggerated
  scores from tiny samples.
- Scoring uses a capped download rate (downloads / published asset-days)
  for **relative** prioritization, never a projected payout.
- Topics match event names exactly after casefolding; unmapped topics
  remain unknown, not zero-performing.
- Without this JSON, the existing scoring behavior is unchanged.
- The existing feed's integrity and freshness checks remain mandatory.
- Do **not** fabricate asset-days from portfolio-wide counts such as 125
  approved assets and 6 total downloads. Those numbers are not topic-level
  observations.

**Remaining work**: Connect authenticated platform exports, associate
individual assets with topics, measure acceptance and payout separately,
and test with real data. No live upload, paid generation, or model training
is enabled by this change.
