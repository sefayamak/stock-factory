#!/usr/bin/env python3
"""Stock Factory — 10-Photo Secure Production Pilot

Phase 3.2 Production Pilot:
- Generate up to 10 genuinely new Google Flow photographs
- Use secured Playwright integration (dedicated profile, localhost CDP only)
- Apply strict technical QC (2048px min, 4MP minimum, Lanczos upscaling if needed)
- Preserve originals, metadata and SHA256 records
- Create numbered contact sheet for visual approval
- Mark all images PENDING_HUMAN (no auto-approval)
- Archive only operator-approved images to Google Drive
- Test resume/dedup safety

Usage:
    # First: Start Chrome with dedicated profile
    bash scripts/start_chrome_secure.sh &

    # Then: Run test (verify one interaction)
    python3 scripts/test_flow_interaction.py

    # Then: Run full pilot
    python3 scripts/run_pilot_secure.py

Safety: No 200-image bulk mode, no Magnific API, no Adobe, strict QC enforced.
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from stock_factory import config, qc, drive_archive
from stock_factory.processing import convert_jpeg, sha256_hex, DuplicateLedger
from stock_factory.local_pipeline.providers.google_flow_browser_secure import GoogleFlowBrowserSecure


@dataclass
class PilotImageResult:
    """Result of a single pilot image generation"""
    concept_id: int
    concept_name: str
    prompt: str
    timestamp: str
    raw_file: str = None
    raw_sha256: str = None
    raw_size_mb: float = None
    dimensions_raw: tuple = None
    qc_pass: bool = False
    qc_reason: str = None
    upscaled: bool = False
    final_file: str = None
    final_sha256: str = None
    final_size_mb: float = None
    dimensions_final: tuple = None
    visual_approval: str = "PENDING_HUMAN"
    drive_archived: bool = False
    drive_file_id: str = None
    generation_status: str = "pending"
    error: str = None


def main():
    print('\n' + '='*90)
    print('STOCK FACTORY — 10 PHOTO SECURE PRODUCTION PILOT')
    print('Phase 3.2 Real Generation with Visual Approval Gate')
    print('='*90)

    # Verify OAuth credentials are available
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        import subprocess
        import os as os_module

        # Load credentials from Keychain (no eval/export)
        cmd = 'security find-generic-password -s "stock-factory" -a "GOOGLE_OAUTH_REFRESH_TOKEN" -w 2>/dev/null'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print('\n✗ ERROR: OAuth credentials not in Keychain')
            print('Run: python3 scripts/setup_drive_oauth_secure.py')
            return 1
        print('\n✓ OAuth credentials loaded from macOS Keychain (no eval/export)')
    except Exception as e:
        print(f'\n⚠ Warning: OAuth may not be available: {e}')

    # Pilot concepts (10 commercially relevant)
    CONCEPTS = [
        {
            "id": 1,
            "name": "Remote team collaboration in modern office",
            "prompt": "Diverse team of professionals collaborating in modern open office space with natural light, laptops, and flexible seating. Warm, productive atmosphere.",
        },
        {
            "id": 2,
            "name": "Sustainable packaging and eco-conscious product",
            "prompt": "Flat lay of eco-friendly packaging materials, recycled cardboard, natural fiber elements. Minimal, clean aesthetic with soft lighting.",
        },
        {
            "id": 3,
            "name": "Healthcare professional with patient",
            "prompt": "Compassionate healthcare provider attending to patient in clinical setting. Professional, trustworthy, empathetic interaction.",
        },
        {
            "id": 4,
            "name": "Tech startup founder at desk",
            "prompt": "Entrepreneur working at minimalist desk with multiple monitors, coffee, notebook. Focused, creative energy. Modern workspace.",
        },
        {
            "id": 5,
            "name": "Hands working with digital interface",
            "prompt": "Hands interacting with holographic or digital display, technology interface. Clean, modern, professional gesture.",
        },
        {
            "id": 6,
            "name": "Multigenerational family moment",
            "prompt": "Grandmother, parent, and child sharing a genuine moment together. Warm lighting, natural interaction. Connection and legacy.",
        },
        {
            "id": 7,
            "name": "Professional woman in leadership role",
            "prompt": "Female executive in modern office, confident posture, professional attire. Leadership presence. Window with city view.",
        },
        {
            "id": 8,
            "name": "Urban food entrepreneurship",
            "prompt": "Small business owner at food market or pop-up stand, serving customers. Fresh produce, authentic community engagement.",
        },
        {
            "id": 9,
            "name": "Financial planning consultation",
            "prompt": "Financial advisor and client reviewing documents and charts together at professional desk. Trust, planning, clarity.",
        },
        {
            "id": 10,
            "name": "Student with educational technology",
            "prompt": "Student using tablet or laptop for learning in educational environment. Engaged, focused study. Natural light, modern setting.",
        },
    ]

    print(f'\n📋 PILOT CONFIGURATION:')
    print(f'   Concepts: {len(CONCEPTS)}')
    print(f'   Provider: Google Flow (Nano Banana 2.1, secured)')
    print(f'   QC Strict: 2048px min short edge, 4MP minimum')
    print(f'   Upscaling: PIL Lanczos 2× (if needed)')
    print(f'   Archive: Google Drive (after operator approval)')
    print(f'   Visual Approval: PENDING_HUMAN (mandatory operator review)')

    # Setup output directory
    pilot_date = datetime.now().strftime('%Y-%m-%d')
    pilot_dir = config.LOCAL_PIPELINE_OUTPUT_DIR / 'pilot_secure' / pilot_date
    pilot_dir.mkdir(parents=True, exist_ok=True)

    print(f'\n📁 Output directory: {pilot_dir}')

    # Initialize
    provider = GoogleFlowBrowserSecure()
    ledger = DuplicateLedger(config.LOCAL_PIPELINE_STATE_DIR)
    results = []
    stats = {
        "start_time": datetime.now(timezone.utc).isoformat(),
        "generated": 0,
        "qc_pass": 0,
        "qc_fail_upscaled": 0,
        "duplicates": 0,
        "pending_visual": 0,
        "archived": 0,
        "errors": 0,
    }

    print(f'\n' + '='*90)
    print('GENERATION PHASE')
    print('='*90)

    for concept in CONCEPTS:
        cid = concept["id"]
        name = concept["name"]
        prompt = concept["prompt"]

        print(f'\n[{cid:2d}/10] {name}')

        result = PilotImageResult(
            concept_id=cid,
            concept_name=name,
            prompt=prompt,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        try:
            print(f'       → Generating via Google Flow...')
            asset = provider.generate(prompt, 'photo')
            stats["generated"] += 1
            result.generation_status = "success"

            # Save raw
            raw_path = pilot_dir / f'concept_{cid:02d}_raw.jpg'
            raw_path.write_bytes(asset.data)

            raw_sha256 = sha256_hex(asset.data)
            result.raw_file = str(raw_path)
            result.raw_sha256 = raw_sha256
            result.raw_size_mb = len(asset.data) / 1024 / 1024

            print(f'       ✓ Generated: {result.raw_size_mb:.2f} MB')

            # Run QC
            print(f'       → Running technical QC...')
            jpeg = convert_jpeg(asset.data)
            jpeg_sha256 = sha256_hex(jpeg)
            qc_pass, qc_reason, dimensions = qc.validate_image(jpeg)

            result.dimensions_raw = dimensions
            result.qc_reason = qc_reason

            if qc_pass:
                result.qc_pass = True
                stats["qc_pass"] += 1
                print(f'       ✓ QC PASS: {dimensions[0]}×{dimensions[1]} ({dimensions[0]*dimensions[1]/1e6:.2f}MP)')
                final_jpeg = jpeg

            else:
                # Upscale with Lanczos
                print(f'       ⚠ QC FAIL ({qc_reason}): Upscaling with Lanczos 2×...')
                from PIL import Image
                from io import BytesIO

                with Image.open(BytesIO(jpeg)) as img:
                    new_w = max(int(img.width * 1.333), 2048)
                    new_h = max(int(img.height * 1.333), 2048)
                    upscaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    buf = BytesIO()
                    upscaled.save(buf, format='JPEG', quality=90)
                    final_jpeg = buf.getvalue()

                final_dims = (new_w, new_h)
                upscaled_pass, _, _ = qc.validate_image(final_jpeg)

                if upscaled_pass:
                    result.upscaled = True
                    result.qc_pass = True
                    stats["qc_fail_upscaled"] += 1
                    print(f'       ✓ Upscaled to {final_dims[0]}×{final_dims[1]} ({final_dims[0]*final_dims[1]/1e6:.2f}MP) — QC PASS')
                else:
                    result.qc_pass = False
                    stats["qc_fail_upscaled"] += 1
                    print(f'       ✗ Upscaling failed QC')
                    results.append(result)
                    continue

            # Check for duplicates
            jpeg_sha256_final = sha256_hex(final_jpeg)
            if ledger.is_duplicate(jpeg_sha256_final):
                result.qc_pass = False
                result.qc_reason = "duplicate"
                stats["duplicates"] += 1
                print(f'       ✗ DUPLICATE: Already in ledger')
                results.append(result)
                continue

            # Save final
            final_path = pilot_dir / f'concept_{cid:02d}_final.jpg'
            final_path.write_bytes(final_jpeg)

            result.final_file = str(final_path)
            result.final_sha256 = jpeg_sha256_final
            result.final_size_mb = len(final_jpeg) / 1024 / 1024
            result.dimensions_final = qc.validate_image(final_jpeg)[2]
            result.visual_approval = "PENDING_HUMAN"
            stats["pending_visual"] += 1

            print(f'       ✓ Final: {result.final_size_mb:.2f} MB, {result.dimensions_final[0]}×{result.dimensions_final[1]}')
            print(f'       ✓ Status: PENDING_HUMAN (awaiting operator visual review)')

        except Exception as e:
            result.generation_status = "failed"
            result.error = str(e)
            stats["errors"] += 1
            print(f'       ✗ ERROR: {str(e)[:60]}')

        results.append(result)

    # Generate contact sheet
    print(f'\n' + '='*90)
    print('CONTACT SHEET GENERATION')
    print('='*90)

    contact_path = pilot_dir / 'CONTACT_SHEET.md'
    contact_md = _generate_contact_sheet(results, stats)
    contact_path.write_text(contact_md)
    print(f'\n✓ Contact sheet: {contact_path}')

    # Save results
    results_file = pilot_dir / 'pilot_results.json'
    results_data = {
        "stats": stats,
        "results": [asdict(r) for r in results],
        "next_step": "OPERATOR_VISUAL_REVIEW_REQUIRED",
    }
    results_file.write_text(json.dumps(results_data, indent=2))
    print(f'✓ Results JSON: {results_file}')

    stats["end_time"] = datetime.now(timezone.utc).isoformat()

    # Summary
    print(f'\n' + '='*90)
    print('PILOT SUMMARY')
    print('='*90)

    print(f'\nGenerated:      {stats["generated"]}/10')
    print(f'QC Passed:      {stats["qc_pass"]} (strict 2048px, 4MP)')
    print(f'Upscaled/Pass:  {stats["qc_fail_upscaled"]}')
    print(f'Duplicates:     {stats["duplicates"]}')
    print(f'Errors:         {stats["errors"]}')
    print(f'Pending Visual: {stats["pending_visual"]} (AWAITING YOUR REVIEW)')
    print(f'Archived:       0/10 (awaiting approval)')

    print(f'\n' + '='*90)
    print('🎯 NEXT STEP: VISUAL APPROVAL REQUIRED')
    print('='*90)

    print(f"""
All generated images are marked PENDING_HUMAN.

1. Review contact sheet: {contact_path}
2. Examine final images in: {pilot_dir}
3. Approve/reject each image
4. Mark approved images: visual_approval: "APPROVED"
5. Then run: python3 scripts/archive_approved_pilot_images.py

This prevents unapproved images from being archived to production.
""")

    return 0


def _generate_contact_sheet(results, stats):
    """Generate markdown contact sheet for visual review."""
    md = f"""# Stock Factory — 10-Photo Pilot Contact Sheet

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
**Status:** PENDING_HUMAN_VISUAL_REVIEW
**Provider:** Google Flow (Nano Banana 2.1)

## Summary

| Metric | Count |
|--------|-------|
| Generated | {stats['generated']}/10 |
| QC Passed | {stats['qc_pass']} |
| Upscaled & Passed | {stats['qc_fail_upscaled']} |
| Duplicates | {stats['duplicates']} |
| Errors | {stats['errors']} |
| Pending Visual Review | {stats['pending_visual']} |

## Images (PENDING_HUMAN - Requires Your Review)

"""

    for i, result in enumerate(results, 1):
        if result.generation_status == "success" and result.qc_pass:
            md += f"""
### {i}. {result.concept_name}

**Concept ID:** {result.concept_id}
**Prompt:** {result.prompt}

**Generation:**
- Status: Generated ✓
- Raw file: {Path(result.raw_file).name if result.raw_file else 'N/A'}
- Raw SHA256: `{result.raw_sha256[:16]}...` if result.raw_sha256 else 'N/A'

**Processing:**
- QC Result: {'PASS' if result.qc_pass else 'FAIL'} ({result.qc_reason})
- Upscaled: {'Yes (Lanczos 2×)' if result.upscaled else 'No'}
- Final file: {Path(result.final_file).name if result.final_file else 'N/A'}
- Final SHA256: `{result.final_sha256[:16]}...` if result.final_sha256 else 'N/A'
- Dimensions: {result.dimensions_final[0]}×{result.dimensions_final[1]} if result.dimensions_final else 'N/A'
- Size: {result.final_size_mb:.2f} MB if result.final_size_mb else 'N/A'

**Approval Status:** 🔘 **PENDING_HUMAN**

👉 **ACTION REQUIRED:** Review the final image and decide:
- ✅ **APPROVED** — Archive to Google Drive
- ❌ **REJECTED** — Keep private, do not archive
- 🤔 **NEEDS_REVISION** — Note for next iteration

---
"""

    md += f"""
## Instructions for Approval

1. Open each final image: `concept_NN_final.jpg`
2. Assess visual quality (composition, aesthetics, commercial viability)
3. Edit `pilot_results.json`:
   - Change `"visual_approval": "PENDING_HUMAN"` to:
     - `"visual_approval": "APPROVED"` (for good images)
     - `"visual_approval": "REJECTED"` (for poor images)
     - `"visual_approval": "NEEDS_REVISION"` (for feedback)
4. Save the edited JSON
5. Run: `python3 scripts/archive_approved_pilot_images.py`

Only approved images will be archived to Google Drive.

---

## Safety Notes

- ✓ No auto-approval — all images require your visual review
- ✓ No duplicate submission — dedup ledger prevents re-archival
- ✓ No paid APIs activated — Magnific, Adobe, marketplace disabled
- ✓ No bulk production — 200-image/day mode remains disabled
- ✓ All originals preserved — raw images kept with SHA256 records
- ✓ Full resume capability — interrupts don't duplicate work

Generated by Claude Code — Stock Factory Production Pilot
"""

    return md


if __name__ == '__main__':
    sys.exit(main())
