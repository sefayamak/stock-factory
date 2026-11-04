#!/usr/bin/env python3
"""
Real Cloudflare Workers AI FLUX.1 Schnell test.
Runs in GitHub Actions: generates ONE real image, validates QC, archives to Drive.
"""
import os
import sys
import json
from pathlib import Path
from io import BytesIO

# For this script to work, we need src in the path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from stock_factory import config, qc
from stock_factory.adapters.cloudflare_flux_adapter import CloudflareFluxAdapter
from stock_factory.processing import sha256_hex
from stock_factory import drive_archive


def main():
    output_dir = Path('/tmp')
    metadata_file = output_dir / 'cloudflare_flux_metadata.json'
    image_file = output_dir / 'cloudflare_flux_test_output.jpg'

    # Initialize metadata
    metadata = {
        'api_connected': False,
        'model': '@cf/black-forest-labs/flux-1-schnell',
        'image_generated': False,
        'qc_pass': False,
        'qc_reason': None,
        'dimensions': None,
        'file_size': 0,
        'sha256': None,
        'drive_archived': False,
        'drive_file_id': None,
        'neurons_used': 0,
        'error': None,
    }

    try:
        # Step 1: Verify free-tier eligibility
        if not config.CLOUDFLARE_API_TOKEN or not config.CLOUDFLARE_ACCOUNT_ID:
            raise ValueError(
                'ERROR: CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set. '
                'These must be configured in GitHub Secrets/Variables.'
            )

        print('✓ Credentials present')
        print(f'  Account ID: {config.CLOUDFLARE_ACCOUNT_ID[:16]}...')
        print(f'  API Token: ***hidden***')

        # Step 2: Create adapter and generate one real image
        prompt = 'photorealistic portrait of a person in professional business attire'
        adapter = CloudflareFluxAdapter([prompt])

        print(f'\n→ Generating real image from prompt:\n  "{prompt}"')
        assets = adapter.fetch(1)

        if not assets:
            raise RuntimeError('No image generated from API')

        asset = assets[0]
        metadata['api_connected'] = True
        metadata['image_generated'] = True

        print('✓ Image generated successfully')

        # Step 3: Record metadata and save image
        img_bytes = asset.data
        file_size = len(img_bytes)
        sha256_hash = sha256_hex(img_bytes)

        metadata['file_size'] = file_size
        metadata['sha256'] = sha256_hash

        print(f'\nImage metadata:')
        print(f'  File size: {file_size:,} bytes ({file_size / 1_000_000:.2f} MB)')
        print(f'  SHA256: {sha256_hash}')

        # Step 4: Test QC validation
        from PIL import Image
        img = Image.open(BytesIO(img_bytes))
        w, h = img.size
        format_name = img.format

        metadata['dimensions'] = [w, h]

        print(f'  Format: {format_name}')
        print(f'  Dimensions: {w}×{h}')
        print(f'  Megapixels: {w * h / 1_000_000:.2f}MP')

        # Run QC
        qc_pass, qc_reason, (qc_w, qc_h) = qc.validate_image(img_bytes)

        metadata['qc_pass'] = qc_pass
        metadata['qc_reason'] = qc_reason

        print(f'\nMagnific QC validation:')
        print(f'  MIN_SHORT_EDGE: {config.MIN_SHORT_EDGE}')
        print(f'  MAX_LONG_EDGE: {config.MAX_LONG_EDGE}')
        print(f'  MIN_MEGAPIXELS: {config.MIN_MEGAPIXELS:,}')
        print(f'  MIN_BYTES: {config.MIN_BYTES:,}')
        print(f'\n  Result: {"✓ PASS" if qc_pass else "✗ FAIL"}')
        print(f'  Reason: {qc_reason}')

        # Save image file
        image_file.write_bytes(img_bytes)
        print(f'\n✓ Image saved to {image_file}')

        # Step 5: Archive to Drive if QC passes
        if qc_pass:
            print(f'\n→ QC passed. Archiving to Google Drive...')
            archive_result = drive_archive.archive(image_file, 'magnific')

            if archive_result.get('archived'):
                metadata['drive_archived'] = True
                metadata['drive_file_id'] = archive_result.get('file_id')
                print(f'✓ Archived to Drive')
                if metadata['drive_file_id']:
                    print(f'  File ID: {metadata["drive_file_id"]}')
            else:
                reason = archive_result.get('reason', 'unknown')
                print(f'✗ Drive archive failed: {reason}')
                if reason != 'drive_not_configured':
                    # Non-configuration errors are warnings
                    print(f'  (This may be expected if Drive OAuth is not available)')
        else:
            print(f'\n✗ QC failed. Skipping Drive archival.')

        # Neuron cost estimate (free tier: 4.80 per base tile + 9.60 per step × 4)
        neurons_estimate = 4.80 + (9.60 * 4)
        metadata['neurons_used'] = neurons_estimate

        print(f'\nEstimated Neuron cost (free tier):')
        print(f'  4.80 (base) + 9.60 × 4 (steps) = ~{neurons_estimate:.0f} Neurons')
        print(f'  Daily cap: {config.CLOUDFLARE_DAILY_GENERATION_CAP} images × {neurons_estimate:.0f} = '
              f'{config.CLOUDFLARE_DAILY_GENERATION_CAP * neurons_estimate:.0f} Neurons/day')
        print(f'  Free tier: 10,000 Neurons/day')
        capacity = 10_000 / (config.CLOUDFLARE_DAILY_GENERATION_CAP * neurons_estimate)
        print(f'  Can run {capacity:.1f}x the daily cap within free tier')

    except Exception as e:
        metadata['error'] = str(e)
        print(f'\n✗ ERROR: {e}', file=sys.stderr)
        sys.exit(1)

    finally:
        # Save metadata JSON
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f'\n✓ Metadata saved to {metadata_file}')

        # Print final summary
        print('\n' + '='*50)
        print('SUMMARY')
        print('='*50)
        print(f'API Connected: {"YES" if metadata["api_connected"] else "NO"}')
        print(f'Model: {metadata["model"]}')
        print(f'Image Generated: {"YES" if metadata["image_generated"] else "NO"}')
        if metadata['dimensions']:
            print(f'Dimensions: {metadata["dimensions"][0]}×{metadata["dimensions"][1]}')
        print(f'File Size: {metadata["file_size"]:,} bytes')
        print(f'Magnific QC: {"PASS" if metadata["qc_pass"] else "FAIL"} ({metadata["qc_reason"]})')
        print(f'Drive Archived: {"YES" if metadata["drive_archived"] else "NO"}')
        print(f'Free Quota Usage: {metadata["neurons_used"]:.0f} / 10000 Neurons ({metadata["neurons_used"] / 10_000 * 100:.1f}%)')
        print('='*50)


if __name__ == '__main__':
    main()
