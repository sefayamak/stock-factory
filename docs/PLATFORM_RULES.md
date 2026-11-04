# PLATFORM_RULES v1 (2026-11-04)

Status of each mandated source:

## Magnific Search Trends (contributor.magnific.com/search-trends)
**BLOCKED for programmatic/automated access.** It is a JS-rendered SPA
dashboard; a static fetch returns an empty body, and it is a
contributor-portal page likely behind login. No trend terms/categories
were retrievable without authenticated browser automation, which was not
attempted (would bypass login and is not something this project does).

**Manual-import path implemented 2026-11-04** (`trend_import.py`, see
`docs/ADAPTERS.md`): the owner exports/copies visible terms from their own
authenticated session into a JSON/CSV snapshot, which the pipeline ingests
with historical snapshots, de-duplication, and rank/volume trend-change
scoring. `trends.py` still defaults to its deterministic static topic bank
-- the manual-import history is not yet wired into concept selection, and
is never to be described as live trend monitoring since it is only as
fresh as the last human-provided snapshot.

## Magnific Contributor Guidelines (Google Slides deck, full deck fetched via export)
**VERIFIED**, retrieved in full ("FAQs for Magnific Contributors").

- **Upload**: first batch 150-200 files, same format; 200 files/month/account cap; FTP only at Level 3 (500 published to reach Level 3; account is below this -- matches README's existing "don't automate Magnific upload" rule); review <=25 working days; 10 days to fix missing metadata/auto-rejects.
- **Photos**: JPG, RGB (sRGB/Adobe RGB/ProPhoto RGB/Display P3), 1.5-80MB, 2000-10000px, 4-100MP, lowest JPEG compression, no watermarks/logos, minimal upscaling, single clear concept.
- **Releases**: model release for every recognizable person; property release for private property/trademarks/pets.
- **AI-generated**: accepted for photos/vectors/PSDs, but must be tagged -- "Created with artificial intelligence" / `_ai_generated` in the metadata CSV. Pipeline CSV emits this column (`_ai_generated: yes` on every accepted row) as of 2026-11-04 -- see `pipeline.run` and `tests/test_factory.py::test_submission_csv_has_ai_disclosure_column`.
- **Vectors/EPS**: Illustrator CC, RGB, 0.5-80MB, real named paths/groups; rasterized text and "image embedded in EPS" / live-traced flat illustrations are explicit rejection reasons. Matches this codebase's `vector/procedural_vector.py` anti-raster-wrapper check.
- **Metadata**: title = one clear who/what/when/where sentence; 5-20 specific English keywords; CSV semicolon/comma separated.
- **Explicit rejection reasons** (general): unauthorized attribution, trademark/copyright, plagiarism, sensitive content, duplicate/similar content, outdated content, wrong dimensions, file errors, generic "quality standards" (platform gives no further detail -- do not invent a specific cause when this is the stated reason), missing metadata, low-quality preview, composition/distortion/typography/spelling issues.
- **Format-specific rejections**: Photo (over-editing, blurriness, lighting, missing release); Vector (raster embedded in EPS, image-traced, ungrouped, bad color palette, non-editable text); PSD (embedded raster, bad layer organization, bad cut).
- **Note**: the source deck itself has an internal inconsistency (PSD mockup section says CMYK/FOGRA27 150-300ppi vs. RGB stated elsewhere) -- flagged, not resolved, since it is the platform's own contradiction.

## Gaps vs. this codebase (tracked, not yet closed)
1. ~~CSV output (`pipeline.run`) has no AI-disclosure column~~ -- closed 2026-11-04: `_ai_generated` field added.
2. `config.MIN_BYTES`/`MIN_SHORT_EDGE`/`MAX_LONG_EDGE`/`MIN_MEGAPIXELS` already sit inside the verified 1.5-80MB / 2000-10000px / 4-100MP ranges -- no code change needed there, just noting the match is now evidence-based, not a guess.
3. `acceptance_learning.KNOWN_REJECTION_CATEGORIES` maps to the directive's list; `unspecified_platform_reason` is used whenever Magnific's own message is the generic "Quality standards" catch-all, per this document.
