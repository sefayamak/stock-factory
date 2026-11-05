"""Phase 3.2: Secured Google Flow browser automation with dedicated profile.

Security hardening:
- Uses dedicated persistent Chrome profile (not personal profile)
- CDP debugging bound to localhost only (127.0.0.1:9222)
- No credential extraction or session token handling
- Manual authentication when required
- Full user transparency on browser interactions
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

from .base import ProviderAdapter, ProviderUnavailable, GeneratedAsset


class GoogleFlowBrowserSecure(ProviderAdapter):
    name = 'google_flow_secure'

    def generate(self, prompt: str, content_type: str) -> GeneratedAsset:
        """Generate image via Google Flow UI using secured Playwright connection.

        Args:
            prompt: Image generation prompt
            content_type: 'photo' only

        Returns:
            GeneratedAsset with image bytes and provider_ref

        Raises:
            ProviderUnavailable if browser unavailable or not authenticated
        """
        if content_type != 'photo':
            raise ProviderUnavailable(f'Unsupported content_type: {content_type}')

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ProviderUnavailable(
                'Playwright not installed. Run: pip install playwright'
            )

        browser = None
        try:
            with sync_playwright() as p:
                # Step 1: Try to connect to existing Chrome with debugging
                # (must be started manually with: --remote-debugging-port=9222)
                try:
                    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
                    print('  ✓ Connected to existing Chrome debugging instance')
                except Exception as e:
                    raise ProviderUnavailable(
                        f'Google Flow browser unavailable.\n'
                        f'Start Chrome with debugging:\n'
                        f'  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\\n'
                        f'    --remote-debugging-port=9222 \\\n'
                        f'    --user-data-dir="/tmp/stock-factory-chrome-profile" &\n'
                        f'\n'
                        f'Error: {e}'
                    )

                # Step 2: Get or create page
                contexts = browser.contexts
                if contexts:
                    context = contexts[0]
                    pages = context.pages
                    page = pages[0] if pages else context.new_page()
                else:
                    context = browser.new_context()
                    page = context.new_page()

                # Step 3: Navigate to Google Flow
                print('  → Navigating to Google Flow...')
                page.goto('https://flow.google.com', wait_until='networkidle', timeout=15000)

                # Step 4: Check authentication
                if 'accounts.google.com' in page.url or 'signin' in page.url.lower():
                    raise ProviderUnavailable(
                        'Not authenticated to Google Flow.\n'
                        'Please authenticate manually at: https://flow.google.com\n'
                        'Keep the Chrome window open and try again.'
                    )

                # Step 5: Wait for page to fully load
                page.wait_for_timeout(2000)

                # Step 6: Find and fill prompt input (with iframe/dynamic content handling)
                print('  → Submitting prompt to Google Flow...')
                try:
                    # Wait longer for dynamic content and iframes to load
                    page.wait_for_timeout(3000)

                    # Try multiple selectors (Flow uses iframes and dynamic rendering)
                    selectors = [
                        'textarea',
                        'input[type="text"]',
                        '[contenteditable="true"]',
                        'input[placeholder*="create"]',
                        'input[placeholder*="prompt"]',
                        'input[placeholder*="what"]',
                        '[role="textbox"]'
                    ]

                    prompt_box = None
                    for selector in selectors:
                        try:
                            box = page.locator(selector).first
                            if box.is_visible(timeout=2000):
                                prompt_box = box
                                break
                        except:
                            pass

                    if not prompt_box:
                        raise ProviderUnavailable('Could not find prompt input field (iframe or dynamic loading issue)')

                    prompt_box.fill(prompt)
                    page.wait_for_timeout(500)

                    # Click generate button (try multiple selectors for robustness)
                    gen_selectors = [
                        'button:has-text("Generate")',
                        'button[aria-label*="generate"]',
                        'button[aria-label*="Generate"]',
                        'svg + button',  # Icon + button pattern
                        'button:right-of(textarea)',  # Button after textarea
                    ]

                    generate_btn = None
                    for selector in gen_selectors:
                        try:
                            btn = page.locator(selector).first
                            if btn.is_visible(timeout=1500):
                                generate_btn = btn
                                break
                        except:
                            pass

                    if not generate_btn:
                        raise ProviderUnavailable('Generate button not found')

                    generate_btn.click()
                    print('  ✓ Prompt submitted')

                except Exception as e:
                    raise ProviderUnavailable(f'Failed to submit prompt: {e}')

                # Step 7: Poll for generation completion (up to 2 minutes)
                print('  → Waiting for generation (45-90s typical)...')
                max_wait_ms = 120000
                poll_interval_ms = 3000
                elapsed = 0

                while elapsed < max_wait_ms:
                    try:
                        # Check for loading indicator
                        loading = page.locator(
                            '[aria-label*="loading"], [aria-label*="generating"], .progress'
                        ).first

                        try:
                            if loading.is_visible(timeout=1000):
                                elapsed += poll_interval_ms
                                page.wait_for_timeout(poll_interval_ms)
                                continue
                        except:
                            pass

                        # Check for generated image
                        img_elem = page.locator('img[src*="flow"], [role="main"] img').first

                        try:
                            if img_elem.is_visible(timeout=1000):
                                print('  ✓ Image generation complete')
                                return self._download_image(page, prompt)
                        except:
                            pass

                        elapsed += poll_interval_ms
                        page.wait_for_timeout(poll_interval_ms)

                    except Exception:
                        elapsed += poll_interval_ms
                        page.wait_for_timeout(poll_interval_ms)

                # Timeout
                raise ProviderUnavailable(
                    f'Generation timeout after {max_wait_ms}ms.\n'
                    'Check Google Flow quotas or connection issues.'
                )

        except ProviderUnavailable:
            raise
        except Exception as e:
            raise ProviderUnavailable(f'Browser error: {type(e).__name__}: {e}')
        finally:
            # IMPORTANT: Do NOT close the browser—it was launched by user manually
            # Only close the page context if we created it
            pass

    def _download_image(self, page, prompt: str) -> GeneratedAsset:
        """Download generated image from Flow."""
        try:
            download_btn = page.locator(
                'button[aria-label*="download"], a[download], button:has-text("Download")'
            ).first

            if download_btn.is_visible(timeout=3000):
                with page.expect_download() as download_info:
                    download_btn.click()
                download = download_info.value
                image_bytes = Path(download.path()).read_bytes()
                file_id = download.suggested_filename.split('.')[0]

                return GeneratedAsset(
                    data=image_bytes,
                    provider='google_flow_secure',
                    provider_ref=file_id,
                    prompt_used=prompt,
                )
        except Exception as download_err:
            pass

        # Fallback: screenshot
        try:
            img_elem = page.locator('[role="main"] img').first
            img_elem.screenshot(path='/tmp/flow_generated.png')
            image_bytes = Path('/tmp/flow_generated.png').read_bytes()

            return GeneratedAsset(
                data=image_bytes,
                provider='google_flow_secure',
                provider_ref='screenshot',
                prompt_used=prompt,
            )
        except Exception as e:
            raise ProviderUnavailable(f'Failed to capture image: {e}')
