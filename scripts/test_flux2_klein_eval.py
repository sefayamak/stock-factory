#!/usr/bin/env python3
"""
Evaluation-only script for @cf/black-forest-labs/flux-2-klein-4b as a
candidate replacement for flux-1-schnell (REJECTED on visual QC: synthetic
skin/fabric/hair, weak stock value -- see incident notes).

This is NOT a production adapter and is NOT wired into pipeline.py or
config.ENABLED_ADAPTERS. It:
  - reuses the existing CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID secrets
    already configured in this repo's GitHub Actions -- never requests,
    prints, or logs a token;
  - generates exactly three distinct photographic test images at the
    model's native maximum resolution (1920x1920 -- see NATIVE_RESOLUTION
    note below), with no beauty-retouch/CGI/"studio portrait" language in
    any prompt;
  - runs the full Magnific acceptance contract (qc.check_magnific_acceptance)
    on each image UNCHANGED -- no Lanczos upscale, no re-encode tuning, no
    threshold changes;
  - never archives to Drive, pass or fail. Visual QC is always
    PENDING_HUMAN for every image this script produces.

NATIVE_RESOLUTION: Cloudflare's flux-2-klein-4b accepts width/height
independently in [256, 1920] (no documented max-megapixel cap beyond that
per-dimension range at the time of writing). 1920x1920 is therefore the
model's native maximum square output -- but it is BELOW
config.MIN_SHORT_EDGE (2048), so even a perfect, fully-detailed native
generation from this model cannot pass Gate 1 (dimension pre-screen) as
currently configured, let alone Gate 2 (MAGNIFIC_READY). That is expected
and is reported plainly below, not worked around.
"""
import sys
import json
import base64
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from stock_factory import config, qc
from stock_factory.processing import sha256_hex

MODEL = '@cf/black-forest-labs/flux-2-klein-4b'
NATIVE_MAX_DIM = 1920  # documented per-dimension ceiling for this model

# Three distinct, non-studio-portrait photographic briefs per instruction:
# realistic workplace documentary, natural outdoor lifestyle, detailed
# product still life. No "beauty retouching", "flawless skin", "CGI",
# or "studio portrait" language anywhere.
SCENES = [
    {
        'key': 'workplace_documentary',
        'prompt': (
            'documentary photojournalism style, a warehouse logistics worker checking '
            'inventory on a handheld scanner mid-shift, visible sweat and skin texture, '
            'creased work uniform, cluttered shelving in the background, available '
            'fluorescent warehouse lighting, candid unposed moment, shot on a 35mm lens'
        ),
    },
    {
        'key': 'outdoor_lifestyle',
        'prompt': (
            'natural outdoor lifestyle photography, a person tying their hiking boots '
            'on a rocky trailhead at golden hour, windblown hair, visible skin pores and '
            'sun texture, worn fabric on their jacket, real overcast-to-gold ambient '
            'light, candid documentary framing, no retouching'
        ),
    },
    {
        'key': 'product_still_life',
        'prompt': (
            'detailed product still life photography, a pair of leather work gloves and '
            'a stainless steel thermos on a scratched wooden workbench, visible material '
            'grain and wear, soft directional window light, shallow depth of field, '
            'macro-level surface detail, no studio softbox look'
        ),
    },
]


def _generate(prompt: str) -> tuple[bytes | None, str | None]:
    import requests
    url = (
        f'https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}'
        f'/ai/run/{MODEL}'
    )
    headers = {'Authorization': f'Bearer {config.CLOUDFLARE_API_TOKEN}'}
    # Cloudflare's documented request shape for this model is multipart
    # form data with prompt/width/height fields (not the JSON body used by
    # flux-1-schnell). The (None, value) form forces `requests` to encode
    # these as multipart/form-data fields with no actual file attached.
    fields = {
        'prompt': (None, prompt),
        'width': (None, str(NATIVE_MAX_DIM)),
        'height': (None, str(NATIVE_MAX_DIM)),
    }

    resp = requests.post(url, headers=headers, files=fields, timeout=config.CLOUDFLARE_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()

    result = body.get('result', body)
    image_b64 = None
    if isinstance(result, dict):
        image_b64 = result.get('image')
    if not image_b64:
        return None, f'unexpected_response_shape:{json.dumps(body)[:300]}'
    return base64.b64decode(image_b64), None


def main():
    output_dir = Path('/tmp')
    metadata_file = output_dir / 'flux2_klein_eval_metadata.json'

    report = {
        'model': MODEL,
        'license': 'FLUX.2 [klein] 4B weights: Apache-2.0 (permissive, commercial use of '
                   'weights and outputs permitted) -- verify against the live model card '
                   'before relying on this for production; the 9B variant is under the '
                   'separate, more restrictive FLUX Non-Commercial License and is NOT used here.',
        'free_tier': True,
        'native_resolution_requested': f'{NATIVE_MAX_DIM}x{NATIVE_MAX_DIM}',
        'native_resolution_note': (
            f'{NATIVE_MAX_DIM} is below config.MIN_SHORT_EDGE ({config.MIN_SHORT_EDGE}); '
            'native output from this model cannot clear the dimension pre-screen as-is.'
        ),
        'images': [],
        'total_neurons_estimate': 0.0,
        'error': None,
    }

    try:
        if not config.CLOUDFLARE_API_TOKEN or not config.CLOUDFLARE_ACCOUNT_ID:
            raise ValueError('CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set')

        for scene in SCENES:
            entry = {
                'key': scene['key'], 'prompt': scene['prompt'],
                'dimensions': None, 'file_size': 0, 'sha256': None,
                'technical_qc': {'pass': False, 'reason': None},
                'magnific_acceptance': {'pass': False, 'reason': None, 'details': None},
                'neurons_estimate': 0.0,
                'drive_archived': False,
                'drive_archive_reason': 'visual_qc_pending_human_review',
                'error': None,
            }
            try:
                print(f"\n-> Generating '{scene['key']}' at {NATIVE_MAX_DIM}x{NATIVE_MAX_DIM}...")
                img_bytes, err = _generate(scene['prompt'])
                if err:
                    raise RuntimeError(err)

                out_path = output_dir / f"flux2_klein_{scene['key']}.jpg"
                out_path.write_bytes(img_bytes)

                from PIL import Image
                with Image.open(BytesIO(img_bytes)) as im:
                    w, h = im.size

                entry['dimensions'] = [w, h]
                entry['file_size'] = len(img_bytes)
                entry['sha256'] = sha256_hex(img_bytes)

                pre_pass, pre_reason, _ = qc.validate_image(img_bytes)
                entry['technical_qc'] = {'pass': pre_pass, 'reason': pre_reason}

                ready, ready_reason, details = qc.check_magnific_acceptance(img_bytes)
                entry['magnific_acceptance'] = {'pass': ready, 'reason': ready_reason, 'details': details}

                # Per-tile Neuron pricing: $0.000059/input 512x512 tile (5.37
                # Neurons), $0.000287/output 512x512 tile (26.05 Neurons).
                # 1920x1920 output = ceil(1920/512)^2 = 16 output tiles.
                tiles = -(-NATIVE_MAX_DIM // 512) ** 2
                neurons = tiles * 26.05
                entry['neurons_estimate'] = neurons
                report['total_neurons_estimate'] += neurons

                print(f'  {w}x{h}, {len(img_bytes):,} bytes')
                print(f'  Dimension pre-screen: {"PASS" if pre_pass else "FAIL"} ({pre_reason})')
                print(f'  MAGNIFIC_READY: {"YES" if ready else "NO"} ({ready_reason})')

            except Exception as e:
                entry['error'] = str(e)
                print(f"  ERROR generating '{scene['key']}': {e}", file=sys.stderr)

            report['images'].append(entry)

    except Exception as e:
        report['error'] = str(e)
        print(f'\nERROR: {e}', file=sys.stderr)

    finally:
        metadata_file.write_text(json.dumps(report, indent=2))
        print(f'\nOK Metadata saved to {metadata_file}')
        print('\n' + '=' * 60)
        print('FLUX.2 [klein] 4B EVALUATION SUMMARY')
        print('=' * 60)
        print(f'Model: {report["model"]}')
        print(f'License: {report["license"]}')
        print(f'Native resolution requested: {report["native_resolution_requested"]}')
        print(f'Note: {report["native_resolution_note"]}')
        for img in report['images']:
            dims = f'{img["dimensions"][0]}x{img["dimensions"][1]}' if img['dimensions'] else 'N/A'
            print(f"\n[{img['key']}]")
            print(f'  dimensions={dims} bytes={img["file_size"]:,}')
            print(f'  technical_qc={img["technical_qc"]["pass"]} ({img["technical_qc"]["reason"]})')
            print(f'  magnific_ready={img["magnific_acceptance"]["pass"]} ({img["magnific_acceptance"]["reason"]})')
            print(f'  drive_archived=False (visual_qc_pending_human_review)')
            if img['error']:
                print(f'  error={img["error"]}')
        print(f'\nTotal Neurons (estimate): {report["total_neurons_estimate"]:.0f}')
        print('Bulk production, Adobe dispatch, and marketplace submission: all disabled.')
        print('=' * 60)

    if report['error'] or any(i['error'] for i in report['images']):
        sys.exit(1)


if __name__ == '__main__':
    main()
