"""Controlled stock asset generator. Human inspection required before submission."""
from __future__ import annotations
import argparse
import base64
import csv
import hashlib
import json
import os
import random
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps

MODEL = os.getenv('GEMINI_IMAGE_MODEL', 'gemini-3.1-flash-image')
DAILY_LIMIT = min(int(os.getenv('DAILY_LIMIT', '3')), 10)
MAX_REQUESTS = min(int(os.getenv('MAX_REQUESTS', '6')), 20)
QUALITY = int(os.getenv('JPEG_QUALITY', '96'))
MIN_BYTES = 1_500_000  # conservative: 1.5 decimal MB
MIN_SHORT = 2048
MAX_SIDE = 10000

TOPICS = [
 ('artisan craft', 'A craftsperson carefully weaving natural fibers at a sunlit workbench, tactile texture, no writing or logo'),
 ('active aging', 'Two active older adult friends enjoying a relaxed walk on a quiet woodland path, candid documentary framing'),
 ('food craftsmanship', 'Baker preparing fresh handmade bread in a small authentic kitchen, natural window light, simple hands'),
 ('home wellbeing', 'Mature adult tending indoor plants in a quiet lived-in apartment, natural candid moment'),
 ('skincare', 'Adult applying skincare cream in a simple real bathroom, realistic natural skin texture and believable hands'),
 ('small business', 'Independent maker arranging handmade pottery for a local delivery, thoughtful natural light, no brand packaging'),
 ('human connection', 'Two generations sharing a warm conversation in a cozy home, subtle authentic emotion'),
 ('sustainable lifestyle', 'Person repairing a well worn piece of clothing at a home sewing desk, natural textile detail'),
]


def choose_jobs(day: str, n: int) -> list[tuple[str, str]]:
    rng = random.Random(day)
    topics = TOPICS.copy()
    rng.shuffle(topics)
    result=[]
    for i in range(n):
        cat, scene = topics[i % len(topics)]
        result.append((cat, scene))
    return result


def make_prompt(scene: str) -> str:
    return ("Generate one original premium commercial stock PHOTO, not an illustration or CGI. "
            + scene + ". Professional documentary editorial photography with honest natural imperfect detail, "
            "believable skin pores, correct anatomy and fingers, physically plausible lighting, coherent environment, "
            "accurate material texture, strong focal subject, commercially versatile composition. "
            "No logos, text, watermarks, readable screens, signage, celebrity likeness, or brand references. "
            "Avoid duplicated or distorted faces, extra limbs, plastic skin, over-sharpening, artificial bokeh. "
            "One cohesive photograph, no collage. 4K output preferred.")


def validate_image(data: bytes) -> tuple[bool, str, tuple[int,int]]:
    try:
        with Image.open(BytesIO(data)) as im:
            im.verify()
        with Image.open(BytesIO(data)) as im:
            w, h = im.size
            if min(w,h) < MIN_SHORT: return False, 'short_edge_below_2048', (w,h)
            if max(w,h) > MAX_SIDE: return False, 'side_above_10000', (w,h)
            if w*h < 4_000_000: return False, 'under_4MP', (w,h)
            return True, 'pass', (w,h)
    except Exception as exc:
        return False, f'invalid_image:{type(exc).__name__}', (0,0)


def convert_jpeg(raw: bytes) -> bytes:
    with Image.open(BytesIO(raw)) as src:
        im = ImageOps.exif_transpose(src).convert('RGB')
        # The generator is asked for native 4K. Never upscale files merely to bypass checks.
        output = BytesIO()
        im.save(output, 'JPEG', quality=QUALITY, subsampling=0, optimize=True,
                icc_profile=ImageCms_profile_if_present(src))
        return output.getvalue()


def ImageCms_profile_if_present(src):
    return src.info.get('icc_profile', b'')


def generate_google(prompt: str) -> bytes:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    resp = client.models.generate_content(
        model=MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE'],
            image_config=types.ImageConfig(image_size='4K'),
        ),
    )
    for candidate in resp.candidates or []:
        for part in candidate.content.parts or []:
            if getattr(part, 'inline_data', None) and part.inline_data.data:
                return part.inline_data.data
    raise RuntimeError('No image returned by Gemini; no asset saved')


def run(out_dir: Path, day: str, count: int, dry_run: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if count < 1 or count > DAILY_LIMIT: raise ValueError('Count exceeds daily safety limit')
    jobs=choose_jobs(day, count)
    rows=[]
    manifest=[]
    for i, (cat, scene) in enumerate(jobs,1):
        name=f'STK-{day.replace("-", "")}-{i:03d}.jpg'
        prompt=make_prompt(scene)
        row={'filename': name,'category':cat,'title':scene.split(',')[0][:145],
             'keywords': ', '.join([cat, 'realistic photography', 'commercial stock', 'authentic lifestyle', 'natural light']),
             'generated_with_ai':'YES', 'prompt':prompt, 'model':MODEL, 'status':'NOT_GENERATED'}
        if not dry_run:
            if i > MAX_REQUESTS: raise ValueError('Request cap reached')
            raw=generate_google(prompt)
            jpeg=convert_jpeg(raw)
            ok,reason,(w,h)=validate_image(jpeg)
            if not ok or len(jpeg)<MIN_BYTES:
                row['status']='REJECTED_QC'
                row['reason']=reason if not ok else 'filesize_below_1_5MB'
                row['dimensions']=f'{w}x{h}'
            else:
                path=out_dir/name
                path.write_bytes(jpeg)
                row['status']='PENDING_HUMAN_VISUAL_QC'
                row['dimensions']=f'{w}x{h}'
                manifest.append(f'{hashlib.sha256(jpeg).hexdigest()}  {name}')
        rows.append(row)
    with (out_dir/'submission.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f, fieldnames=['filename','category','title','keywords','generated_with_ai','prompt','model','status','reason','dimensions'],extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    (out_dir/'checksums.sha256').write_text('\n'.join(manifest) + ('\n' if manifest else ''),encoding='utf-8')
    (out_dir/'run.json').write_text(json.dumps({'day':day,'count':count,'dry_run':dry_run,'model':MODEL,
      'uploaded_to_magnific':False,'ready_for_submission':False,'human_approval_required':True},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out_dir),'generated':sum(x['status']=='PENDING_HUMAN_VISUAL_QC' for x in rows),'dry_run':dry_run}))

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='output')
    ap.add_argument('--day',default=datetime.now(timezone.utc).date().isoformat())
    ap.add_argument('--count',type=int,default=3)
    ap.add_argument('--execute',action='store_true',help='Spend API credits to generate images; default is safe dry run')
    args=ap.parse_args()
    run(Path(args.out),args.day,args.count,not args.execute)
