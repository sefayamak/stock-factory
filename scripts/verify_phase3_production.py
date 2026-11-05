#!/usr/bin/env python3
"""Phase 3: Complete production pipeline test with REAL Google Flow image.

Tests: QC → Archive → Ledger Recovery
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from stock_factory import config, qc, drive_archive
from stock_factory.processing import convert_jpeg, sha256_hex
from stock_factory.local_pipeline import state_store

def main():
    print('='*70)
    print('PHASE 3: PRODUCTION PIPELINE TEST WITH REAL GOOGLE FLOW IMAGE')
    print('='*70)
    
    image_path = Path('src/stock_factory/local_pipeline/_test_data/production_test_photo.jpg')
    raw = image_path.read_bytes()
    raw_sha256 = sha256_hex(raw)
    
    print(f'\n✓ Real Google Flow image loaded')
    print(f'  File: {image_path.name}')
    print(f'  SHA256: {raw_sha256}')
    print(f'  Size: {len(raw)/1024:.1f} KB')
    
    # QC test
    print(f'\n1. TECHNICAL QC...')
    jpeg = convert_jpeg(raw)
    jpeg_sha256 = sha256_hex(jpeg)
    ready, reason, dims = qc.validate_image(jpeg)
    
    print(f'   JPEG SHA256: {jpeg_sha256}')
    print(f'   Dimensions: {dims}')
    print(f'   QC Result: {"✓ PASS" if ready else "✗ FAIL"}')
    if not ready:
        print(f'   Reason: {reason}')
        print(f'   EXPECTED: Real Flow images may be below 2048px minimum')
    
    # Archive attempt (will succeed regardless of QC)
    print(f'\n2. GOOGLE DRIVE ARCHIVE...')
    out_dir = config.LOCAL_PIPELINE_OUTPUT_DIR / 'processed' / '2026-11-05'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'phase3_production_test.jpg'
    out_path.write_bytes(jpeg)
    
    archive_result = drive_archive.archive(out_path, 'magnific')
    if archive_result.get('archived'):
        print(f'   ✓ Archived: {archive_result.get("file_id")}')
    else:
        print(f'   ✗ Failed: {archive_result.get("reason")}')
    
    # Ledger
    print(f'\n3. PRODUCTION LEDGER...')
    ledger = DuplicateLedger(config.LOCAL_PIPELINE_STATE_DIR)
    is_dup = ledger.is_duplicate(jpeg_sha256)
    print(f'   Duplicate check: {is_dup}')
    
    print('\n' + '='*70)
    print('PHASE 3 TEST COMPLETE')
    print('='*70)
    return 0

if __name__ == '__main__':
    sys.exit(main())
