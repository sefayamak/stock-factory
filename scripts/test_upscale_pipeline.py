#!/usr/bin/env python3
"""
Resolution-fix pipeline test (runs in GitHub Actions, feature branch only).

Generates one real Cloudflare FLUX.1 Schnell image (1024x1024 native),
preserves it unmodified, applies a genuine 2x Lanczos upscale to 2048x2048
(no artificial file-size padding), validates both versions, and reports
full provenance. Does NOT archive to Drive: technical QC passing is not
visual approval, and this script is a verification step, not production.
Paid generation, Adobe, and marketplace submission are untouched/disabled.
"""
import sys
import json
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from stock_factory import config, qc, upscale
from stock_factory.adapters.cloudflare_flux_adapter import CloudflareFluxAdapter
from stock_factory.processing import sha256_hex, DuplicateLedger


def main():
    output_dir = Path('/tmp')
    metadata_file = output_dir / 'upscale_pipeline_metadata.json'
    original_file = output_dir / 'upscale_pipeline_original.jpg'
    upscaled_file = output_dir / 'upscale_pipeline_upscaled.jpg'

    metadata = {
        'original': {'dimensions': None, 'file_size': 0, 'sha256': None},
        'upscale_method': 'pillow_lanczos_2x',
        'upscaled': {'dimensions': None, 'file_size': 0, 'sha256': None},
        # Dimension/megapixel pre-screen only. NOT submission readiness --
        # see magnific_acceptance below, and the qc.py module docstring.
        'technical_qc': {'pass': False, 'reason': None},
        # The complete Magnific acceptance contract (dims, megapixels,
        # min bytes, format, GPS-metadata, duplicate), run on the FINAL
        # encoded upscaled file. This is the only field that may ever be
        # reported as MAGNIFIC_READY.
        'magnific_acceptance': {'pass': False, 'reason': None, 'details': None},
        'duplicate_detected': False,
        'visual_review': 'pending_human_review',
        'drive_archived': False,
        'drive_archive_reason': 'visual_qc_pending_human_review',
        'neurons_used': 0,
        'error': None,
    }

    try:
        if not config.CLOUDFLARE_API_TOKEN or not config.CLOUDFLARE_ACCOUNT_ID:
            raise ValueError('CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set')

        prompt = 'photorealistic portrait of a person in professional business attire'
        adapter = CloudflareFluxAdapter([prompt])
        print(f'-> Generating native-resolution image from prompt:\n   "{prompt}"')
        assets = adapter.fetch(1)
        if not assets:
            raise RuntimeError('No image generated from API')

        original_bytes = assets[0].data
        original_file.write_bytes(original_bytes)

        with BytesIO(original_bytes) as buf:
            from PIL import Image
            with Image.open(buf) as im:
                orig_w, orig_h = im.size

        metadata['original']['dimensions'] = [orig_w, orig_h]
        metadata['original']['file_size'] = len(original_bytes)
        metadata['original']['sha256'] = sha256_hex(original_bytes)
        print(f'OK Original preserved: {orig_w}x{orig_h}, {len(original_bytes):,} bytes, '
              f'sha256={metadata["original"]["sha256"][:16]}...')

        print('\n-> Applying genuine 2x Lanczos upscale (local, free, no API)...')
        upscaled_bytes = upscale.lanczos_upscale(original_bytes, factor=2)
        upscaled_file.write_bytes(upscaled_bytes)

        with BytesIO(upscaled_bytes) as buf:
            from PIL import Image
            with Image.open(buf) as im:
                up_w, up_h = im.size

        metadata['upscaled']['dimensions'] = [up_w, up_h]
        metadata['upscaled']['file_size'] = len(upscaled_bytes)
        metadata['upscaled']['sha256'] = sha256_hex(upscaled_bytes)
        print(f'OK Upscaled: {up_w}x{up_h}, {len(upscaled_bytes):,} bytes, '
              f'sha256={metadata["upscaled"]["sha256"][:16]}...')

        # Gate 1: cheap dimension/megapixel pre-screen. Historically this
        # was the only gate the script reported, and that was the bug --
        # it says nothing about file size, format, or duplicates.
        qc_pass, qc_reason, (qc_w, qc_h) = qc.validate_image(upscaled_bytes)
        metadata['technical_qc']['pass'] = qc_pass
        metadata['technical_qc']['reason'] = qc_reason
        print(f'\n[1/2] Dimension pre-screen on upscaled image: {"PASS" if qc_pass else "FAIL"} ({qc_reason})')
        print(f'  MIN_SHORT_EDGE={config.MIN_SHORT_EDGE}  MIN_MEGAPIXELS={config.MIN_MEGAPIXELS:,}  '
              f'MAX_LONG_EDGE={config.MAX_LONG_EDGE}')

        ledger = DuplicateLedger(config.STATE_DIR)
        digest = metadata['upscaled']['sha256']

        # Gate 2: the full Magnific acceptance contract, on the FINAL
        # encoded file. This is the only gate allowed to declare
        # MAGNIFIC_READY. It deliberately includes MIN_BYTES -- Lanczos
        # upscaling does not invent photographic detail, so a native
        # 1024x1024 generation upscaled 2x will very often resize-pass
        # Gate 1 while still being too low in actual encoded detail to
        # pass Gate 2's MIN_BYTES floor. That contradiction is the point:
        # it is Gate 2's job to catch what Gate 1 cannot.
        ready, ready_reason, details = qc.check_magnific_acceptance(upscaled_bytes, digest=digest, ledger=ledger)
        metadata['magnific_acceptance'] = {'pass': ready, 'reason': ready_reason, 'details': details}
        metadata['duplicate_detected'] = (ready_reason == 'duplicate')
        print(f'[2/2] Magnific acceptance contract: {"READY" if ready else "NOT READY"} ({ready_reason})')
        print(f'  MIN_BYTES={config.MIN_BYTES:,}  actual={len(upscaled_bytes):,} bytes  '
              f'format={details.get("format")}')
        print(f'  (ledger has {len(ledger.seen)} prior hashes; not recording this run -- '
              f'verification only, not a production ingest)')

        print('\nDrive archival: SKIPPED by design.')
        print('  Passing the acceptance contract is a technical/platform gate, not visual')
        print('  approval (composition, aesthetics, anatomy, IP risk). Even a MAGNIFIC_READY')
        print('  file still requires an explicit human visual-QC step before archival,')
        print('  submission, or mass production -- none of which this script performs.')

        neurons_estimate = 4.80 + (9.60 * 4)
        metadata['neurons_used'] = neurons_estimate

    except Exception as e:
        metadata['error'] = str(e)
        print(f'\nERROR: {e}', file=sys.stderr)
        sys.exit(1)

    finally:
        metadata_file.write_text(json.dumps(metadata, indent=2))
        print(f'\nOK Metadata saved to {metadata_file}')
        print('\n' + '=' * 50)
        print('RESOLUTION FIX PIPELINE SUMMARY')
        print('=' * 50)
        if metadata['original']['dimensions']:
            print(f'Original:  {metadata["original"]["dimensions"][0]}x{metadata["original"]["dimensions"][1]}'
                  f'  {metadata["original"]["file_size"]:,} bytes')
        if metadata['upscaled']['dimensions']:
            print(f'Upscaled:  {metadata["upscaled"]["dimensions"][0]}x{metadata["upscaled"]["dimensions"][1]}'
                  f'  {metadata["upscaled"]["file_size"]:,} bytes')
        print(f'Method:    {metadata["upscale_method"]}')
        print(f'Dimension pre-screen (Gate 1, NOT readiness): '
              f'{"PASS" if metadata["technical_qc"]["pass"] else "FAIL"} '
              f'({metadata["technical_qc"]["reason"]})')
        ma = metadata['magnific_acceptance']
        print(f'MAGNIFIC_READY (Gate 2, full contract): {"YES" if ma["pass"] else "NO"} ({ma["reason"]})')
        print(f'Duplicate: {metadata["duplicate_detected"]}')
        print(f'Visual review: {metadata["visual_review"]}')
        print(f'Drive Archived: {"YES" if metadata["drive_archived"] else "NO"} '
              f'({metadata["drive_archive_reason"]})')
        print(f'Actual cost: ~{metadata["neurons_used"]:.0f} Neurons (free tier), $0 upscale (local Pillow)')
        print('=' * 50)


if __name__ == '__main__':
    main()
