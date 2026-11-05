#!/usr/bin/env python3
"""Test one real Google Flow interaction to verify browser integration works.

Before running the full 10-photo pilot, test with a single concept.
This verifies:
1. Chrome CDP connection works
2. Google Flow UI is accessible
3. User is authenticated
4. Generation and download work
5. QC validation works

Usage:
    python3 scripts/test_flow_interaction.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from stock_factory import config, qc
from stock_factory.processing import convert_jpeg, sha256_hex
from stock_factory.local_pipeline.providers.google_flow_browser_secure import GoogleFlowBrowserSecure


def main():
    print('\n' + '='*80)
    print('GOOGLE FLOW INTEGRATION TEST')
    print('='*80)

    print('\n✓ Prerequisites:')
    print('  1. Chrome running with: --remote-debugging-port=9222')
    print('  2. Authenticated to Google Flow (https://flow.google.com)')
    print('  3. Connected to 127.0.0.1:9222 (localhost only)')

    print('\n' + '='*80)
    print('TEST 1: Browser Connection')
    print('='*80)

    provider = GoogleFlowBrowserSecure()

    # Test concept
    test_prompt = "Professional woman in business attire, modern office, natural light, confident expression, leadership presence"

    print(f'\nPrompt: {test_prompt[:70]}...')
    print('\nAttempting generation...\n')

    try:
        asset = provider.generate(test_prompt, 'photo')
        print(f'\n✓ Generation successful')
        print(f'  File size: {len(asset.data) / 1024 / 1024:.2f} MB')
        print(f'  Provider: {asset.provider}')
        print(f'  Provider ref: {asset.provider_ref}')

    except Exception as e:
        print(f'\n✗ Generation failed: {e}')
        print('\nTroubleshooting:')
        print('  • Is Chrome running with --remote-debugging-port=9222?')
        print('  • Is it bound to localhost (127.0.0.1)?')
        print('  • Are you authenticated to Google Flow?')
        print('  • Is Google Flow quota available?')
        return 1

    # Test QC validation
    print(f'\n' + '='*80)
    print('TEST 2: Technical QC Validation')
    print('='*80)

    jpeg = convert_jpeg(asset.data)
    jpeg_sha256 = sha256_hex(jpeg)
    qc_pass, qc_reason, dimensions = qc.validate_image(jpeg)

    print(f'\nDimensions: {dimensions[0]}×{dimensions[1]}')
    print(f'Megapixels: {dimensions[0]*dimensions[1]/1e6:.2f} MP')
    print(f'File size: {len(jpeg) / 1024 / 1024:.2f} MB')
    print(f'SHA256: {jpeg_sha256[:16]}...')

    if qc_pass:
        print(f'\n✓ QC PASS')
    else:
        print(f'\n✗ QC FAIL: {qc_reason}')
        print('\nNote: Test image may be undersized.')
        print('Full pilot includes Lanczos 2× upscaling for QC-failed images.')

    # Save test result
    test_output_dir = config.LOCAL_PIPELINE_OUTPUT_DIR / 'pilot_test'
    test_output_dir.mkdir(parents=True, exist_ok=True)

    test_path = test_output_dir / 'test_interaction_raw.jpg'
    test_path.write_bytes(asset.data)

    qc_path = test_output_dir / 'test_interaction_qc.jpg'
    qc_path.write_bytes(jpeg)

    print(f'\n' + '='*80)
    print('TEST RESULTS SAVED')
    print('='*80)
    print(f'Raw image: {test_path}')
    print(f'QC result: {qc_path}')

    print(f'\n' + '='*80)
    if qc_pass:
        print('✓ BROWSER INTEGRATION VERIFIED')
        print('✓ Ready to proceed with 10-photo pilot')
    else:
        print('✓ BROWSER INTEGRATION VERIFIED (QC will upscale)')
        print('✓ Ready to proceed with 10-photo pilot')
    print('='*80 + '\n')

    return 0


if __name__ == '__main__':
    sys.exit(main())
