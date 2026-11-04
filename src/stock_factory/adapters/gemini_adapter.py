"""Paid Gemini API image adapter. Disabled unless ALLOW_PAID_GENERATION=true."""
from __future__ import annotations
import os
from .base import Adapter, RawAsset

MODEL = os.getenv('GEMINI_IMAGE_MODEL', 'gemini-3.1-flash-image')


class GeminiAdapter(Adapter):
    name = 'gemini'

    def __init__(self, prompts: list[str]):
        self.prompts = prompts

    def fetch(self, n: int) -> list[RawAsset]:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
        assets = []
        for prompt in self.prompts[:n]:
            resp = client.models.generate_content(
                model=MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_modalities=['TEXT', 'IMAGE'],
                    image_config=types.ImageConfig(image_size='4K'),
                ),
            )
            data = None
            for candidate in resp.candidates or []:
                for part in candidate.content.parts or []:
                    if getattr(part, 'inline_data', None) and part.inline_data.data:
                        data = part.inline_data.data
                        break
                if data:
                    break
            if data is None:
                continue
            assets.append(RawAsset(data=data, source=self.name, origin_name=f'gemini-{len(assets)}.bin', prompt=prompt))
        return assets
