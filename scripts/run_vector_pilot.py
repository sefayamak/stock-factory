#!/usr/bin/env python3
"""Phase 4 pilot: genuine-vector asset batch.

Produces real SVG vector assets (actual <path>/<polygon>/<circle> geometry,
never a raster image wrapped in an SVG container) using the only vector
generation path this repo has that is both authorized and actually working
today: stock_factory.vector.procedural_vector (geometric icons/patterns).
No paid API, no Flow automation, no login bypass of any kind is used here.

Each asset is validated with qc.validate_svg_vector (the dedicated
real-vector-vs-embedded-raster QC gate) before being counted as "pass".
A manifest (JSON) records every asset's id, sha256, QC result, and --
with --upload and Drive credentials present in the environment -- its
real Drive file id in STOCK_FACTORY_MAGNIFIC_OUTPUT.

This never touches Adobe, never calls a paid generation API, and never
submits anything to the Magnific marketplace itself -- --upload only
archives to Drive via the existing drive_archive module, the same
archival step the main pipeline uses.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from stock_factory import config, qc  # noqa: E402
from stock_factory.vector.procedural_vector import (  # noqa: E402
    generate_polygon_icon, generate_repeating_pattern,
)

ICON_SPECS = [
    (3, '#2b2b2b'), (4, '#2b6ea5'), (5, '#a53a2b'), (6, '#3a6ea5'),
    (7, '#6ea53a'), (8, '#a56e3a'),
]
PATTERN_SPECS = [
    (32, 10, '#3a6ea5'), (48, 8, '#a53a6e'), (64, 6, '#6e3aa5'), (96, 4, '#2b8a4a'),
]


def build_assets() -> list[dict]:
    assets = []
    for i, (sides, fill) in enumerate(ICON_SPECS):
        asset = generate_polygon_icon(sides=sides, size=1024, fill=fill)
        assets.append({'id': f'pilot-vector-icon-{i:02d}-{sides}sides', 'svg': asset.svg, 'kind': asset.kind})
    for i, (tile, grid, fill) in enumerate(PATTERN_SPECS):
        asset = generate_repeating_pattern(tile=tile, grid=grid, fill=fill)
        assets.append({'id': f'pilot-vector-pattern-{i:02d}', 'svg': asset.svg, 'kind': asset.kind})
    return assets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default='output/vector_pilot')
    ap.add_argument('--upload', action='store_true', help='Also archive validated SVGs to Drive (requires OAuth env vars + DRIVE_MAGNIFIC_FOLDER_ID)')
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    manifest = []
    for asset in build_assets():
        svg_bytes = asset['svg'].encode('utf-8')
        ok, reason = qc.validate_svg_vector(svg_bytes)
        digest = hashlib.sha256(svg_bytes).hexdigest()
        record = {
            'id': asset['id'], 'kind': asset['kind'], 'qc_pass': ok, 'qc_reason': reason,
            'sha256': digest, 'bytes': len(svg_bytes), 'uploaded': False, 'drive_file_id': None,
        }
        if ok:
            path = out_dir / f"{asset['id']}.svg"
            path.write_bytes(svg_bytes)
            record['local_path'] = str(path)
            if args.upload:
                if not (config.GOOGLE_OAUTH_REFRESH_TOKEN and config.DRIVE_MAGNIFIC_FOLDER_ID):
                    record['upload_blocker'] = 'GOOGLE_OAUTH_REFRESH_TOKEN/DRIVE_MAGNIFIC_FOLDER_ID not configured in this environment'
                else:
                    from stock_factory import drive_archive
                    result = drive_archive.archive(path, 'magnific')
                    record['uploaded'] = bool(result.get('archived'))
                    record['drive_file_id'] = result.get('drive_file_id')
                    record['drive_status'] = result.get('reason', 'archived')
        manifest.append(record)

    elapsed = time.time() - t0
    passed = sum(1 for r in manifest if r['qc_pass'])
    manifest_path = out_dir / 'manifest.json'
    manifest_path.write_text(json.dumps({
        'generated_count': len(manifest),
        'qc_pass_count': passed,
        'qc_pass_rate': passed / len(manifest) if manifest else 0.0,
        'production_time_seconds': round(elapsed, 3),
        'cost_usd': 0.0,
        'cost_note': 'Procedural generation, no paid API call made.',
        'assets': manifest,
    }, indent=2))
    print(f'[pilot] {passed}/{len(manifest)} assets passed QC in {elapsed:.3f}s')
    print(f'[pilot] manifest written to {manifest_path}')


if __name__ == '__main__':
    main()
