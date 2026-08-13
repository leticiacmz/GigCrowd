import pytest
from app.providers.songkick.client import SongkickClient


def test_client_initialization():
    """Test client initialization with configuration"""
    client = SongkickClient()
    
    assert client.headless is True
    assert client.require_navigation is True
    assert client.base_url == "https://www.songkick.com"
    assert client.search_endpoint == "/api/universal_search"


def test_client_configuration_from_settings():
    """Test that client uses configuration from settings"""
    from app.config import settings
    
    client = SongkickClient()
    
    assert client.headless == settings.PLAYWRIGHT_HEADLESS
    assert client.require_navigation == settings.SONGKICK_REQUIRE_NAVIGATION
    assert client.base_url == settings.SONGKICK_BASE_URL


@pytest.mark.asyncio
async def test_search_artist_requires_real_playwright():
    """
    Test that search_artist requires Playwright browser.
    This test verifies the method exists and has the right signature.
    Actual Playwright tests would require a real browser or complex mocking.
    """
    client = SongkickClient()
    
    # Verify the method exists
    assert hasattr(client, 'search_artist')
    assert callable(client.search_artist)
    
    # This would require a real Playwright browser to test fully
    # For now, we just verify the interface exists
