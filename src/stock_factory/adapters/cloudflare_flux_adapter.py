"""Cloudflare Workers AI FLUX.1 Schnell text-to-image adapter. Free tier only."""
from __future__ import annotations
import os
import sys
import base64
import time
import requests
from .base import Adapter, RawAsset


class CloudflareFluxAdapter(Adapter):
    name = 'cloudflare_flux'

    def __init__(self, prompts: list[str]):
        self.prompts = prompts
        self.api_token = os.environ.get('CLOUDFLARE_API_TOKEN', '')
        self.account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID', '')
        self.timeout_seconds = int(os.getenv('CLOUDFLARE_TIMEOUT', '60'))
        self.max_retries = int(os.getenv('CLOUDFLARE_MAX_RETRIES', '3'))
        self.retry_delay = float(os.getenv('CLOUDFLARE_RETRY_DELAY', '2'))
        self._call_count = 0

    def fetch(self, n: int) -> list[RawAsset]:
        if not self.api_token or not self.account_id:
            return []

        assets = []
        for prompt in self.prompts[:n]:
            asset = self._generate_image(prompt)
            if asset:
                assets.append(asset)

        return assets

    def _generate_image(self, prompt: str) -> RawAsset | None:
        url = (
            f'https://api.cloudflare.com/client/v4/accounts/{self.account_id}'
            '/ai/run/@cf/black-forest-labs/flux-1-schnell'
        )
        headers = {'Authorization': f'Bearer {self.api_token}'}
        payload = {'prompt': prompt, 'steps': 4}

        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                resp.raise_for_status()
                result = resp.json()

                if 'result' in result and 'image' in result['result']:
                    image_data = base64.b64decode(result['result']['image'])
                    self._call_count += 1
                    return RawAsset(
                        data=image_data,
                        source=self.name,
                        origin_name=f'cloudflare-flux-{self._call_count}.jpg',
                        prompt=prompt,
                    )
                else:
                    print(f'ERROR: Unexpected API response structure: {result}', file=sys.stderr)
                    return None
            except requests.exceptions.RequestException as e:
                print(f'ERROR: API request failed (attempt {attempt + 1}/{self.max_retries}): {type(e).__name__}: {e}', file=sys.stderr)
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay ** (attempt + 1))
                else:
                    return None
            except Exception as e:
                print(f'ERROR: Unexpected error in _generate_image: {type(e).__name__}: {e}', file=sys.stderr)
                return None

        return None
