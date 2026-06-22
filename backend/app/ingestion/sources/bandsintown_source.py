from typing import List, Dict, Any
from playwright.async_api import async_playwright, Browser, Page
import asyncio


class BandsintownSource:
    """Source for fetching events from Bandsintown using Playwright scraper"""
    
    BASE_URL = "https://www.bandsintown.com"
    
    def __init__(self):
        self.browser = None
        self.page = None
    
    async def _initialize_browser(self):
        """Initialize Playwright browser"""
        if not self.browser:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=True)
            self.page = await self.browser.new_page()
    
    async def _close_browser(self):
        """Close Playwright browser"""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None
    
    async def search_events(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for events by artist name using Bandsintown scraper.
        
        Args:
            query: Artist name or search query
            
        Returns:
            List of raw event data from Bandsintown
        """
        await self._initialize_browser()
        
        try:
            # Navigate to Bandsintown search
            search_url = f"{self.BASE_URL}/search?q={query}"
            await self.page.goto(search_url, wait_until="networkidle")
            
            # Wait for results to load
            await self.page.wait_for_selector(".event-item", timeout=10000)
            
            # Extract event data
            events = await self.page.evaluate("""
                () => {
                    const events = [];
                    const eventItems = document.querySelectorAll('.event-item');
                    
                    eventItems.forEach(item => {
                        const titleElement = item.querySelector('.event-title');
                        const dateElement = item.querySelector('.event-date');
                        const venueElement = item.querySelector('.event-venue');
                        const locationElement = item.querySelector('.event-location');
                        const linkElement = item.querySelector('a');
                        
                        if (titleElement && dateElement) {
                            events.push({
                                title: titleElement.textContent.trim(),
                                date: dateElement.textContent.trim(),
                                venue: venueElement ? venueElement.textContent.trim() : '',
                                location: locationElement ? locationElement.textContent.trim() : '',
                                url: linkElement ? linkElement.href : '',
                                source: 'bandsintown'
                            });
                        }
                    });
                    
                    return events;
                }
            """)
            
            return events[:20]  # Limit to 20 events
            
        except Exception as e:
            print(f"Error scraping Bandsintown: {e}")
            return []
        finally:
            await self._close_browser()
    
    async def get_artist_events(self, artist_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get events for a specific artist using Bandsintown scraper.
        
        Args:
            artist_name: Artist name
            limit: Maximum number of events to return
            
        Returns:
            List of raw event data from Bandsintown
        """
        await self._initialize_browser()
        
        try:
            # Navigate to artist page
            artist_url = f"{self.BASE_URL}/a/{artist_name.replace(' ', '-')}"
            await self.page.goto(artist_url, wait_until="networkidle")
            
            # Wait for events to load
            await self.page.wait_for_selector(".event-item", timeout=10000)
            
            # Extract event data
            events = await self.page.evaluate("""
                () => {
                    const events = [];
                    const eventItems = document.querySelectorAll('.event-item');
                    
                    eventItems.forEach(item => {
                        const titleElement = item.querySelector('.event-title');
                        const dateElement = item.querySelector('.event-date');
                        const venueElement = item.querySelector('.event-venue');
                        const locationElement = item.querySelector('.event-location');
                        const linkElement = item.querySelector('a');
                        
                        if (titleElement && dateElement) {
                            events.push({
                                title: titleElement.textContent.trim(),
                                date: dateElement.textContent.trim(),
                                venue: venueElement ? venueElement.textContent.trim() : '',
                                location: locationElement ? locationElement.textContent.trim() : '',
                                url: linkElement ? linkElement.href : '',
                                source: 'bandsintown'
                            });
                        }
                    });
                    
                    return events;
                }
            """)
            
            return events[:limit]
            
        except Exception as e:
            print(f"Error scraping artist events from Bandsintown: {e}")
            return []
        finally:
            await self._close_browser()
    
    async def get_events_by_location(self, city: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get events in a specific location using Bandsintown scraper.
        
        Args:
            city: City name
            limit: Maximum number of events to return
            
        Returns:
            List of raw event data from Bandsintown
        """
        await self._initialize_browser()
        
        try:
            # Navigate to location page
            location_url = f"{self.BASE_URL}/events/{city.replace(' ', '-')}"
            await self.page.goto(location_url, wait_until="networkidle")
            
            # Wait for events to load
            await self.page.wait_for_selector(".event-item", timeout=10000)
            
            # Extract event data
            events = await self.page.evaluate("""
                () => {
                    const events = [];
                    const eventItems = document.querySelectorAll('.event-item');
                    
                    eventItems.forEach(item => {
                        const titleElement = item.querySelector('.event-title');
                        const dateElement = item.querySelector('.event-date');
                        const venueElement = item.querySelector('.event-venue');
                        const locationElement = item.querySelector('.event-location');
                        const linkElement = item.querySelector('a');
                        
                        if (titleElement && dateElement) {
                            events.push({
                                title: titleElement.textContent.trim(),
                                date: dateElement.textContent.trim(),
                                venue: venueElement ? venueElement.textContent.trim() : '',
                                location: locationElement ? locationElement.textContent.trim() : '',
                                url: linkElement ? linkElement.href : '',
                                source: 'bandsintown'
                            });
                        }
                    });
                    
                    return events;
                }
            """)
            
            return events[:limit]
            
        except Exception as e:
            print(f"Error scraping location events from Bandsintown: {e}")
            return []
        finally:
            await self._close_browser()
