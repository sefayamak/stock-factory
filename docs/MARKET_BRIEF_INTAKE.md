# Source-backed opportunity briefs (Magnific photo pilot)

Stock Factory can now read `state/intelligence/market_briefs.json` on the scan/production runner to select fresh, distinct sector concepts before falling back to twelve evergreen topics. This does **not** create a live market data source: the research scout/human must supply dated briefs with credible provenance.

Example:

```json
{
  "schema_version": 1,
  "briefs": [
    {
      "category": "urban cooling",
      "scene": "Documentary stock photograph of workers installing high-reflectance roof coating on a commercial building",
      "platform": "magnific",
      "media": "photo",
      "signal_type": "editorial_hypothesis",
      "observed_on": "2026-11-08",
      "source_url": "https://example.org/replace-with-actual-source"
    }
  ]
}
```

A source URL is mandatory but **not independently verified by this module**. Editorial hypotheses do not constitute proven sales demand. Inputs older than 14 days, future dated, wrong platform/media, duplicate, or malformed are excluded. The current production selector reads only Magnific **photo** briefs; vectors, illustrations, video and other platform brains remain blocked until their own production/QC adapters are tested.

To make this autonomous, next connect a permitted, timestamped market-data provider and verify source URLs, implement archive-wide semantic diversity, and test a 20-file visual/QC/Drive run. No generation or uploads are enabled by this change.
