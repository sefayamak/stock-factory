# Public Stock Market Scan — 2026-11-08

## Evidence and limits

Public marketplace demand is **not** the same as contributor download revenue.

- [Shutterstock Image Search Trends](https://www.shutterstock.com/trends): publicly displays search-term demand labels, percentage growth and competing result counts. Observed examples on 2026-11-08: **data center cooling** +197%, 7,772 results, Low demand; **social media stress** +163%, 30,851 results, Low demand; **damaged package** +113%, 49,438 results, Low demand; **christmas 2026** +353%, 80,665 results, Low demand. These are site-defined search indicators, **not downloads or expected earnings**. Source terms with trademarks and public figures must never be copied into commercial assets.
- [Adobe Stock 2026 collections](https://stock.adobe.com/collections) and [Adobe 2026 Creative Trends](https://business.adobe.com/resources/creative-trends-report.html): curated themes (All the Feels, Connectioneering, Surreal Silliness, Local Flavor; women's midlife wellness, accessibility, analog activities, multigenerational messaging). **Editorial themes, not measured purchase volume.**
- [123RF public explore index](https://www.123rf.com/explore/): longstanding popular-search categories (background textures, graphic arts, medical etc.). No current search volume or growth figures published there.
- [Vecteezy Contributor](https://www.vecteezy.com/contributors): accepts photo, vector and video submissions, with emphasis on original quality. Its public contributor marketing page is **not a demand feed**.
- [Motion Elements contributor guide](https://help.motionelements.com/en/contributor/docs/guide-for-selling-stock-video): describes preferred video formats (vertical, effects, technology topics); a category preference, **not evidence of downloads**.
- [Magnific Contributor FAQ](https://www.magnific.com/ai/docs/faqs-for-contributors): monthly search-trend briefing behind contributor access; seasonal content recommended >=1 month before the event; repeated near-identical files rejected. This public FAQ does not expose machine-readable download data.

## Marketplace policy gates

- [Shutterstock](https://submit.shutterstock.com/help/en/articles/10594622-content-policy-updates-ai-generated-content) does **not** accept contributor-submitted AI-generated media as of review date. Research only; **never route these images there**.
- [Motion Elements AI policy](https://help.motionelements.com/en/contributor/docs/policy-on-ai-generated-content-and-contributor-accounts) requires a **separate AI-generated contributor account**, AI disclosure and appropriate licensing; do not activate uploads unless account type verified.
- Magnific requires original content and correct format; photographs are JPG; EPS vectors must have matching JPG preview, and uploading an AI-produced raster image does **not** make it editable vector artwork.

## Implementation

`public_market_seed.json` contains **10 original Magnific-only photographic concept briefs** derived from the public signals above. It is an observed, expiring snapshot, **not a live scanner**. The loader prioritizes `state/intelligence/market_briefs.json` if a separate scout supply exists, and otherwise reads the packaged snapshot. Missing/invalid/stale input reverts safely to calendar/unique evergreen candidates. The snapshot is never used past 14 days after 2026-11-08. It does not assert revenue, and does not activate paid generation, Drive uploads or contributor submissions.

Next: create a permitted, authenticated or publicly documented source refresh mechanism, record real fetch metadata and source trust level; test on the schedule runner without bypassing site restrictions, and connect real generation + QC + archiving separately.
