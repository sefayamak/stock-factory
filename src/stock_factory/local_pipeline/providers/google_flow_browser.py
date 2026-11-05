"""Phase 3: Google Flow browser-driven image generation via Nano Banana 2.1.

Uses Playwright for standalone browser automation against the operator's
authenticated Google Flow session (https://flow.google.com). No credentials
are handled by this code -- browser must be pre-authenticated.

Workflow:
1. Connect to existing Chrome instance (operator must have Flow tab open)
2. Navigate to existing or new Flow project
3. Submit prompt via UI
4. Poll for Nano Banana 2.1 generation (typically 45-90s per image)
5. Download image bytes
6. Return as GeneratedAsset with Flow's UI-generated file_id

REQUIREMENTS:
- Playwright must be installed: pip install playwright
- Chrome browser must be running (can be started with: playwright install chromium)
- Operator must be authenticated to Google Flow (existing session reused)
- No API keys or credentials needed in code

FAILURES:
- Raised as ProviderUnavailable if browser unavailable, rate-limited, or logged out
"""
from __future__ import annotations
import sys
import time
import tempfile
import hashlib
from pathlib import Path

from .base import ProviderAdapter, ProviderUnavailable, GeneratedAsset


class GoogleFlowBrowserProvider(ProviderAdapter):
    name = 'google_flow'

    def generate(self, prompt: str, content_type: str) -> GeneratedAsset:
        """Generate image via Google Flow UI (Nano Banana 2.1) using Playwright.

        Args:
            prompt: Image generation prompt
            content_type: 'photo' or 'illustration' (only 'photo' uses Flow)

        Returns:
            GeneratedAsset with image bytes, provider_ref (Flow project/image ID)

        Raises:
            ProviderUnavailable if browser unavailable, rate-limited, logged out,
            or if timeout exceeded during generation.
        """
        if content_type != 'photo':
            raise ProviderUnavailable(
                f'google_flow_browser: unsupported content_type={content_type}. '
                'Only "photo" is supported. Use midjourney_browser for illustrations.'
            )

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ProviderUnavailable(
                'google_flow_browser: Playwright not installed. '
                'Run: pip install playwright && playwright install chromium'
            )

        browser = None
        try:
            # Connect to running Chrome instance (user must have opened Chrome with --remote-debugging-port)
            # For now, launch a fresh browser connected to user's Chrome profile
            with sync_playwright() as p:
                # Try to connect to existing Chrome on default port
                try:
                    browser = p.chromium.connect_over_cdp('http://localhost:9222')
                except Exception:
                    # If no debugging instance, launch fresh (will need manual login)
                    browser = p.chromium.launch(headless=False)

                page = browser.new_page()
                page.goto('https://flow.google.com', wait_until='networkidle', timeout=10000)

                # Check if logged in (look for main content or redirect)
                if 'accounts.google.com' in page.url:
                    raise ProviderUnavailable(
                        'google_flow_browser: Not authenticated to Google. '
                        'Open https://flow.google.com and sign in first.'
                    )

                # Create new project or use existing
                try:
                    # Try to click "Start Creating" if on landing page
                    page.click('button:has-text("Start Creating")', timeout=2000)
                except Exception:
                    pass  # Already in a project

                # Wait for project to load
                page.wait_for_timeout(1000)

                # Find the prompt input box
                try:
                    prompt_box = page.locator('textarea, input[placeholder*="create"], input[placeholder*="prompt"], [role="textbox"]').first
                    if not prompt_box.is_visible():
                        raise ProviderUnavailable('google_flow_browser: Could not find prompt input.')

                    prompt_box.fill(prompt)
                    page.wait_for_timeout(500)

                    # Find and click the generate button (arrow/play icon)
                    generate_btn = page.locator('button[aria-label*="generate"], button:has-text("Generate"), [role="button"]:right-of(textarea)').first
                    generate_btn.click()
                except Exception as e:
                    raise ProviderUnavailable(f'google_flow_browser: Failed to submit prompt: {e}')

                # Poll for completion (Nano Banana typically takes 45-90s)
                max_wait_ms = 120000  # 2 minutes max
                poll_interval_ms = 2000
                elapsed = 0

                while elapsed < max_wait_ms:
                    # Look for generated image (appears in main canvas or preview area)
                    try:
                        # Check if generation is still in progress
                        loading = page.locator('[aria-label*="loading"], [aria-label*="generating"], .progress').first
                        if loading.is_visible():
                            page.wait_for_timeout(poll_interval_ms)
                            elapsed += poll_interval_ms
                            continue

                        # Generation complete - look for download button or capture image
                        img_elem = page.locator('img[src*="flow"], [role="main"] img').first
                        if img_elem.is_visible():
                            # Download the image
                            try:
                                download_btn = page.locator('button[aria-label*="download"], a[download]').first
                                with page.expect_download() as download_info:
                                    download_btn.click()
                                download = download_info.value
                                image_bytes = download.path().read_bytes()
                                file_id = download.suggested_filename.split('.')[0]

                                return GeneratedAsset(
                                    data=image_bytes,
                                    provider='google_flow',
                                    provider_ref=file_id,
                                    prompt_used=prompt,
                                )
                            except Exception:
                                # Fallback: capture screenshot of image area
                                img_elem.screenshot(path='/tmp/flow_generated.png')
                                image_bytes = Path('/tmp/flow_generated.png').read_bytes()
                                return GeneratedAsset(
                                    data=image_bytes,
                                    provider='google_flow',
                                    provider_ref='screenshot',
                                    prompt_used=prompt,
                                )
                    except Exception:
                        pass

                    page.wait_for_timeout(poll_interval_ms)
                    elapsed += poll_interval_ms

                # Timeout
                raise ProviderUnavailable(
                    f'google_flow_browser: Generation timeout after {max_wait_ms}ms. '
                    'Check if Flow rate-limited or has quota issues.'
                )

        except ProviderUnavailable:
            raise
        except Exception as e:
            raise ProviderUnavailable(f'google_flow_browser: {type(e).__name__}: {e}')
        finally:
            if browser:
                browser.close()
