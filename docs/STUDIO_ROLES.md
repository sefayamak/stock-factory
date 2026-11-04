# 20-role studio architecture -> code mapping

These are **logical responsibilities**, scheduled/batched as part of the
existing pipeline run -- not 20 permanently running LLM processes. Each row
says what code implements it today and its real status.

| # | Role | Implemented as | Status |
|---|------|-----------------|--------|
| 1 | Global Trend Researcher | `trends.py` (static topic bank) | IMPLEMENTED_NOT_TESTED against a real external source |
| 2 | Magnific Search Trends Analyst | `docs/PLATFORM_RULES.md` ingestion | see PLATFORM_RULES.md for fetch status |
| 3 | Adobe Stock Market Analyst | not built | BLOCKED (no permitted Adobe demand-data source identified yet) |
| 4 | Seasonal Demand Forecaster | `trends.py` concept rotation (date-seeded) | IMPLEMENTED_NOT_TESTED (no real seasonal signal yet, just rotation) |
| 5 | Competitor and Content Gap Analyst | `scoring.py` (`competition` input) | IMPLEMENTED_NOT_TESTED (field exists, no data feed) |
| 6 | Creative Director | `prompts.make_prompt` + `scoring.score` gate | VERIFIED_WORKING (tested) |
| 7 | Commercial Stock Art Director | same as above, photo pipeline | VERIFIED_WORKING (tested) |
| 8 | Photography Prompt Specialist | `prompts.py` | VERIFIED_WORKING (tested) |
| 9 | Vector Design Specialist | `vector/procedural_vector.py` | VERIFIED_WORKING for procedural geometric templates only; creative vector BLOCKED (see module docstring) |
| 10 | Cultural Accuracy Researcher | not built | BLOCKED (needs a defined ruleset/source, not yet specified) |
| 11 | Image Generation Orchestrator | `pipeline.py` + `adapters/` | VERIFIED_WORKING for manual_inbox; gemini adapter IMPLEMENTED_NOT_TESTED (never run live, stays off) |
| 12 | Vector Production Engineer | `vector/procedural_vector.py` | VERIFIED_WORKING (tested) for its limited scope |
| 13 | Retouch and Image Optimization Specialist | `processing.convert_jpeg` | VERIFIED_WORKING (tested) |
| 14 | Technical Quality Inspector | `qc.validate_image` | VERIFIED_WORKING (tested) |
| 15 | Visual and Anatomical QC Inspector | not built | BLOCKED (needs human review or a vision-QC model; not wired up -- directive requires human review when automated confidence is insufficient, and today there is no automated confidence signal at all for this check) |
| 16 | Metadata and SEO Specialist | `prompts.py` title/keywords fields | IMPLEMENTED_NOT_TESTED against real platform metadata schemas (see PLATFORM_RULES.md) |
| 17 | Copyright and Platform Compliance Inspector | `acceptance_learning.py` categories | IMPLEMENTED_NOT_TESTED (categories defined, no automated detector) |
| 18 | Adobe Submission Manager | not built | BLOCKED (no verified authorized Adobe upload API/credentials) |
| 19 | Magnific Submission Manager | not built | BLOCKED (per README: account below the 500-published FTP-eligibility threshold; do not automate) |
| 20 | Performance and Revenue Analyst | `acceptance_learning.LearningStore.summary` | VERIFIED_WORKING (tested) for logged data; no live downloads/revenue feed connected |

## Why this isn't 20 live agents

Each "role" above is a pure function or small module invoked once per
pipeline run, in the existing single scheduled job (`pipeline.py` via
GitHub Actions). Adding 20 separately-scheduled processes would multiply
operational cost and failure surface for no capacity gain -- the
bottleneck is data/credentials/legitimate-integration availability, not
compute parallelism.
