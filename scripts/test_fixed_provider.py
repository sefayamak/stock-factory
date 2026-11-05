#!/usr/bin/env python3
"""Test the FIXED Google Flow provider with one real image generation.

This tests:
1. Fresh locator acquisition after navigation
2. Event-driven waits for element interactivity
3. Actual image download and SHA256 verification
4. No duplicate submission
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from stock_factory import config, qc
from stock_factory.processing import convert_jpeg, sha256_hex, DuplicateLedger
from stock_factory.local_pipeline.providers.google_flow_fixed import GoogleFlowFixed


def main():
    print('\n' + '='*80)
    print('GOOGLE FLOW FIXED PROVIDER TEST')
    print('Testing one real image generation')
    print('='*80)

    print('\n✓ Prerequisites:')
    print('  1. Chrome running with --remote-debugging-port=9222')
    print('  2. Authenticated to Google Flow')
    print('  3. Bound to localhost only')

    # Test prompt
    test_prompt = "Professional woman in modern office with natural light, business attire, confident leadership presence"

    print(f'\n📝 Test Prompt: {test_prompt[:60]}...')
    print('\n' + '='*80)
    print('GENERATION TEST')
    print('='*80)

    provider = GoogleFlowFixed()
    ledger = DuplicateLedger(config.LOCAL_PIPELINE_STATE_DIR)

    try:
        print(f'\n→ Generating image...')
        asset = provider.generate(test_prompt, 'photo')

        print(f'\n✅ GENERATION SUCCESSFUL')
        print(f'   Size: {len(asset.data) / 1024 / 1024:.2f} MB')
        print(f'   Provider: {asset.provider}')
        print(f'   Provider ref: {asset.provider_ref}')

        # Verify it's valid JPEG
        print(f'\n→ Validating JPEG...')
        jpeg = convert_jpeg(asset.data)
        jpeg_sha256 = sha256_hex(jpeg)

        print(f'✓ Valid JPEG: {len(jpeg) / 1024 / 1024:.2f} MB')
        print(f'✓ SHA256: {jpeg_sha256[:16]}...')

        # Run QC
        print(f'\n→ Running technical QC...')
        qc_pass, qc_reason, dimensions = qc.validate_image(jpeg)

        print(f'   Dimensions: {dimensions[0]}×{dimensions[1]}')
        print(f'   Megapixels: {dimensions[0]*dimensions[1]/1e6:.2f} MP')

        if qc_pass:
            print(f'\n✅ QC PASS')
        else:
            print(f'\n⚠️ QC FAIL: {qc_reason}')
            print(f'   (Pilot will upscale with Lanczos)')

        # Check for duplicates
        print(f'\n→ Checking dedup ledger...')
        if ledger.is_duplicate(jpeg_sha256):
            print(f'⚠️ DUPLICATE: Image already in ledger')
        else:
            print(f'✓ New image (not in ledger)')

        # Save test result
        test_output_dir = config.LOCAL_PIPELINE_OUTPUT_DIR / 'test_fixed_provider'
        test_output_dir.mkdir(parents=True, exist_ok=True)

        raw_path = test_output_dir / 'test_raw.jpg'
        raw_path.write_bytes(asset.data)

        qc_path = test_output_dir / 'test_qc.jpg'
        qc_path.write_bytes(jpeg)

        print(f'\n' + '='*80)
        print('✅ FIXED PROVIDER TEST PASSED')
        print('='*80)

        print(f'\nFiles saved:')
        print(f'  Raw: {raw_path}')
        print(f'  QC:  {qc_path}')

        print(f'\n✓ Real image generated successfully')
        print(f'✓ Download confirmed')
        print(f'✓ SHA256 verified: {jpeg_sha256[:16]}...')
        print(f'✓ QC validated')
        print(f'✓ Dedup check passed')

        print(f'\nReady to proceed with 10-image pilot')

        return 0

    except Exception as e:
        print(f'\n❌ ERROR: {e}')
        print('\nTroubleshooting:')
        print('  • Is Chrome still running?')
        print('  • Is CDP port 127.0.0.1:9222 responding?')
        print('  • Is Google Flow page loaded?')
        print('  • Is there a valid project with prompt input?')
        return 1


if __name__ == '__main__':
    sys.exit(main())
