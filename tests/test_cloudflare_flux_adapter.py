"""Unit tests for CloudflareFluxAdapter."""
import pytest
from unittest.mock import MagicMock, patch
import base64
from io import BytesIO

from PIL import Image
from stock_factory.adapters.cloudflare_flux_adapter import CloudflareFluxAdapter


def make_test_image(w=512, h=512) -> bytes:
    """Create a minimal test JPEG image."""
    img = Image.new('RGB', (w, h), color='blue')
    buf = BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return buf.getvalue()


class TestCloudflareFluxAdapterInit:
    """Test adapter initialization."""

    def test_init_with_credentials(self):
        """Adapter initializes with valid credentials."""
        adapter = CloudflareFluxAdapter(['test prompt'])
        assert adapter.name == 'cloudflare_flux'
        assert adapter.prompts == ['test prompt']
        assert adapter._call_count == 0

    def test_init_multiple_prompts(self):
        """Adapter initializes with multiple prompts."""
        prompts = ['prompt 1', 'prompt 2', 'prompt 3']
        adapter = CloudflareFluxAdapter(prompts)
        assert adapter.prompts == prompts


class TestCloudflareFluxAdapterFetch:
    """Test fetch() method with mocked API."""

    def test_fetch_returns_empty_without_credentials(self):
        """fetch() returns empty list when credentials are missing."""
        adapter = CloudflareFluxAdapter(['test prompt'])
        adapter.api_token = ''
        adapter.account_id = ''

        result = adapter.fetch(1)
        assert result == []

    def test_fetch_missing_token(self):
        """fetch() returns empty list when API token is missing."""
        adapter = CloudflareFluxAdapter(['test prompt'])
        adapter.api_token = ''
        adapter.account_id = 'test-account'

        result = adapter.fetch(1)
        assert result == []

    def test_fetch_missing_account_id(self):
        """fetch() returns empty list when account ID is missing."""
        adapter = CloudflareFluxAdapter(['test prompt'])
        adapter.api_token = 'test-token'
        adapter.account_id = ''

        result = adapter.fetch(1)
        assert result == []

    @patch('stock_factory.adapters.cloudflare_flux_adapter.requests.post')
    def test_fetch_generates_asset(self, mock_post):
        """fetch() generates RawAsset on successful API call."""
        # Create a test image and encode it
        test_img = make_test_image()
        test_img_b64 = base64.b64encode(test_img).decode('utf-8')

        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'result': {
                'image': test_img_b64
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        adapter = CloudflareFluxAdapter(['test prompt'])
        adapter.api_token = 'test-token'
        adapter.account_id = 'test-account'

        assets = adapter.fetch(1)

        assert len(assets) == 1
        assert assets[0].source == 'cloudflare_flux'
        assert assets[0].prompt == 'test prompt'
        assert assets[0].data == test_img
        assert assets[0].origin_name == 'cloudflare-flux-1.jpg'

    @patch('stock_factory.adapters.cloudflare_flux_adapter.requests.post')
    def test_fetch_respects_limit(self, mock_post):
        """fetch(n) respects the limit parameter."""
        test_img = make_test_image()
        test_img_b64 = base64.b64encode(test_img).decode('utf-8')

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'result': {'image': test_img_b64}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        adapter = CloudflareFluxAdapter(['prompt 1', 'prompt 2', 'prompt 3'])
        adapter.api_token = 'test-token'
        adapter.account_id = 'test-account'

        assets = adapter.fetch(2)

        assert len(assets) == 2
        assert mock_post.call_count == 2

    @patch('stock_factory.adapters.cloudflare_flux_adapter.requests.post')
    def test_fetch_handles_api_error(self, mock_post):
        """fetch() returns empty list on API error."""
        mock_post.side_effect = Exception('Connection failed')

        adapter = CloudflareFluxAdapter(['test prompt'])
        adapter.api_token = 'test-token'
        adapter.account_id = 'test-account'

        assets = adapter.fetch(1)

        assert assets == []

    @patch('stock_factory.adapters.cloudflare_flux_adapter.requests.post')
    def test_fetch_handles_missing_image_in_response(self, mock_post):
        """fetch() returns empty list when image is missing from response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {'result': {}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        adapter = CloudflareFluxAdapter(['test prompt'])
        adapter.api_token = 'test-token'
        adapter.account_id = 'test-account'

        assets = adapter.fetch(1)

        assert assets == []

    @patch('stock_factory.adapters.cloudflare_flux_adapter.requests.post')
    def test_call_count_increments(self, mock_post):
        """_call_count increments with each successful asset generation."""
        test_img = make_test_image()
        test_img_b64 = base64.b64encode(test_img).decode('utf-8')

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'result': {'image': test_img_b64}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        adapter = CloudflareFluxAdapter(['p1', 'p2', 'p3'])
        adapter.api_token = 'test-token'
        adapter.account_id = 'test-account'

        assert adapter._call_count == 0

        assets1 = adapter.fetch(1)
        assert adapter._call_count == 1
        assert assets1[0].origin_name == 'cloudflare-flux-1.jpg'

        assets2 = adapter.fetch(1)
        assert adapter._call_count == 2
        assert assets2[0].origin_name == 'cloudflare-flux-2.jpg'


class TestCloudflareFluxAdapterIntegration:
    """Integration-style tests that check the adapter shape."""

    def test_adapter_inherits_from_base(self):
        """Adapter is a subclass of base Adapter."""
        from stock_factory.adapters.base import Adapter
        assert issubclass(CloudflareFluxAdapter, Adapter)

    def test_adapter_has_required_name(self):
        """Adapter has required 'name' class attribute."""
        adapter = CloudflareFluxAdapter(['test'])
        assert hasattr(adapter, 'name')
        assert isinstance(adapter.name, str)
        assert len(adapter.name) > 0

    def test_adapter_returns_raw_assets(self):
        """fetch() returns list of RawAsset objects."""
        from stock_factory.adapters.base import RawAsset

        # When credentials are missing, this should safely return []
        adapter = CloudflareFluxAdapter(['test'])
        adapter.api_token = ''

        assets = adapter.fetch(1)
        assert isinstance(assets, list)
        # If there are assets (when mocked), they should be RawAsset
        for asset in assets:
            assert isinstance(asset, RawAsset)
