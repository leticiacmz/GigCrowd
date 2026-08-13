import asyncio
from playwright.async_api import async_playwright
from urllib.parse import quote
from app.config import settings
from app.core.logger import get_logger

logger = get_logger("songkick_client")


class SongkickClient:
    def __init__(self):
        self.headless = settings.PLAYWRIGHT_HEADLESS
        self.require_navigation = settings.SONGKICK_REQUIRE_NAVIGATION
        self.base_url = settings.SONGKICK_BASE_URL
        self.search_endpoint = "/api/universal_search"

    async def search_artist(self, artist_name: str) -> dict:
        """
        Execute Songkick artist search using Playwright.
        Returns raw JSON response from Songkick API.
        """
        logger.info(f"Searching Songkick for: {artist_name}")
        
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.headless)
            
            try:
                context = await browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    locale="en-US"
                )
                
                page = await context.new_page()
                
                # Configurable navigation for performance testing
                if self.require_navigation:
                    logger.debug("Using initial navigation (proven method)")
                    await page.goto(
                        self.base_url,
                        wait_until="domcontentloaded",
                        timeout=60_000
                    )
                else:
                    logger.debug("Skipping initial navigation (performance test)")
                
                # Call internal API directly (proven mechanism from test_scraper.py)
                endpoint = f"{self.base_url}{self.search_endpoint}?query={quote(artist_name)}"
                
                response = await page.evaluate(
                    """
                    async (url) => {
                        const response = await fetch(url, {
                            method: "GET",
                            credentials: "include",
                            headers: {"Accept": "application/json"}
                        });
                        return {
                            status: response.status,
                            body: await response.text()
                        };
                    }
                    """,
                    endpoint
                )
                
                if response["status"] != 200:
                    logger.error(f"Songkick API returned {response['status']}")
                    raise Exception(f"Songkick API error: {response['status']}")
                
                import json
                return json.loads(response["body"])
                
            finally:
                await browser.close()
