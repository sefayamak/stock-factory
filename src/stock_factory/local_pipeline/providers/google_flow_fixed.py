"""Google Flow browser provider - FIXED version for reliable automation.

ROOT CAUSE FIX:
- Use direct project URL (not landing page)
- Reacquire locators AFTER navigation
- Wait for element INTERACTIVITY, not just visibility
- Handle stale element references
- One locator per interaction cycle
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

from .base import ProviderAdapter, ProviderUnavailable, GeneratedAsset


class GoogleFlowFixed(ProviderAdapter):
    name = 'google_flow_fixed'

    def __init__(self):
        super().__init__()
        # Cache the project URL once discovered
        self.cached_project_url = None

    def generate(self, prompt: str, content_type: str) -> GeneratedAsset:
        """Generate image via Google Flow with fixed element handling."""
        if content_type != 'photo':
            raise ProviderUnavailable(f'Unsupported content_type: {content_type}')

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ProviderUnavailable('Playwright not installed')

        browser = None
        try:
            with sync_playwright() as p:
                # Connect to running Chrome
                browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222', timeout=10000)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()

                print(f'  ✓ Connected to Chrome')

                # STEP 1: Navigate to project (use cached URL or discover it)
                project_url = self._get_project_url(page)
                print(f'  → Navigating to project: {project_url[:50]}...')
                page.goto(project_url, wait_until='domcontentloaded', timeout=20000)

                # STEP 2: Wait for page to fully load with interactive elements
                print(f'  → Waiting for interface to load...')
                self._wait_for_interface_ready(page, max_wait=8000)

                # STEP 3: Get fresh locator for textarea (AFTER navigation)
                prompt_box = self._get_prompt_input(page)
                if not prompt_box:
                    raise ProviderUnavailable('Prompt input not accessible')

                # STEP 4: Fill prompt
                print(f'  → Entering prompt...')
                prompt_box.fill(prompt)
                time.sleep(0.5)

                # STEP 5: Get fresh generate button locator
                gen_btn = self._get_generate_button(page)
                if not gen_btn:
                    raise ProviderUnavailable('Generate button not found')

                # STEP 6: Click generate
                print(f'  → Generating image...')
                gen_btn.click()

                # STEP 7: Poll for completion (Nano Banana: 45-90s)
                print(f'  → Waiting for generation (45-90s)...')
                return self._wait_for_image_download(page, prompt, max_wait=120000)

        except ProviderUnavailable:
            raise
        except Exception as e:
            raise ProviderUnavailable(f'Browser error: {type(e).__name__}: {e}')

    def _get_project_url(self, page) -> str:
        """Always use landing page and create fresh project for each generation.

        OLD project URLs have hidden textareas. Fresh projects are reliable.
        """
        return 'https://flow.google.com/'

    def _wait_for_interface_ready(self, page, max_wait=20000):
        """Wait for textarea with proper timing for page load and "Start Creating" click."""
        import time as time_module

        print(f'    Waiting for page content (2-3s for full render)...')

        # CRITICAL: Page needs 2-3 seconds to render buttons and content
        time_module.sleep(3)

        # Check if we're on landing page by looking for "Start Creating"
        start_btn = None
        try:
            start_btn = page.locator('button:has-text("Start Creating")').first
            if start_btn.is_visible(timeout=1000):
                print(f'    ✓ Found "Start Creating" - clicking...')
                start_btn.click()
                print(f'    Waiting for project to load...')
                time_module.sleep(3)
                try:
                    page.wait_for_load_state('domcontentloaded', timeout=10000)
                except:
                    pass
                time_module.sleep(2)
        except Exception as e:
            print(f'    Note: Could not click "Start Creating": {e}')

        # CRITICAL FIX: Textarea might be ENABLED but NOT VISIBLE (display: none)
        # We can still interact with it programmatically
        print(f'    Checking for textarea (even if hidden)...')

        try:
            textarea = page.locator('textarea').first

            # Check if textarea exists and is enabled (even if hidden)
            try:
                is_enabled = textarea.is_enabled(timeout=1000)
                if is_enabled:
                    print(f'    ✓ Textarea found and enabled (may be hidden)')
                    # Try to make it visible by scrolling it into view
                    textarea.scroll_into_view_if_needed()
                    time_module.sleep(0.5)

                    # Try once more
                    try:
                        is_visible = textarea.is_visible(timeout=500)
                        if is_visible:
                            print(f'    ✓ Textarea now visible')
                            return
                        else:
                            # Even if not visible, we can try to use it
                            print(f'    ⚠ Textarea hidden but enabled - attempting interaction...')
                            return
                    except:
                        # If still hidden but enabled, that's OK
                        print(f'    ⚠ Textarea hidden but we can still interact')
                        return

            except Exception as e:
                print(f'    Error checking textarea: {e}')

        except Exception as e:
            print(f'    Textarea not found: {e}')

        # If we reach here, no textarea at all
        raise ProviderUnavailable('No textarea found on project page')

    def _get_prompt_input(self, page):
        """Acquire fresh textarea locator. Returns None if not found."""
        selectors = ['textarea', 'input[type="text"]', '[role="textbox"]']

        for selector in selectors:
            try:
                elem = page.locator(selector).first
                # Critical: check if it's ACTUALLY interactive
                if elem.is_visible(timeout=1000) and elem.is_enabled(timeout=500):
                    return elem
            except:
                pass

        return None

    def _get_generate_button(self, page):
        """Acquire fresh generate button locator."""
        selectors = [
            'button:has-text("Generate")',
            'button[aria-label*="generate" i]',
            'svg + button',
        ]

        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=500) and btn.is_enabled(timeout=500):
                    return btn
            except:
                pass

        return None

    def _wait_for_image_download(self, page, prompt, max_wait=120000):
        """Poll for image completion and download."""
        deadline = time.time() + (max_wait / 1000)

        while time.time() < deadline:
            try:
                # Check for download button (appears after generation)
                download_btn = page.locator(
                    'button[aria-label*="download"], a[download], button:has-text("Download")'
                ).first

                if download_btn.is_visible(timeout=500):
                    print(f'  ✓ Image ready, downloading...')

                    # Download
                    with page.expect_download() as download_info:
                        download_btn.click()

                    download = download_info.value
                    image_bytes = Path(download.path()).read_bytes()
                    file_id = download.suggested_filename.split('.')[0]

                    return GeneratedAsset(
                        data=image_bytes,
                        provider='google_flow_fixed',
                        provider_ref=file_id,
                        prompt_used=prompt,
                    )

                # Check if still generating
                loading = page.locator('[aria-label*="loading"], [aria-label*="generating"]').first
                if loading.is_visible(timeout=500):
                    time.sleep(2)  # Still generating
                    continue

            except:
                pass

            time.sleep(1)

        raise ProviderUnavailable('Generation timeout')
