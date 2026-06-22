import httpx
from typing import List, Dict, Any, Optional


class TicketMasterSource:
    """Source for fetching events from TicketMaster API"""
    
    BASE_URL = "https://app.ticketmaster.com/discovery/v2"
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
    
    async def search_events(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for events by artist name, venue, or city.
        
        Args:
            query: Search query (artist name, venue, or city)
            
        Returns:
            List of raw event data from TicketMaster
        """
        async with httpx.AsyncClient() as client:
            # Search events
            response = await client.get(
                f"{self.BASE_URL}/events.json",
                params={
                    "apikey": self.api_key,
                    "keyword": query,
                    "size": 20
                }
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            
            if "_embedded" not in data or "events" not in data["_embedded"]:
                return []
            
            events = data["_embedded"]["events"]
            
            # Convert to standard format
            normalized_events = []
            for event in events:
                normalized_event = {
                    "id": event.get("id"),
                    "name": event.get("name"),
                    "url": event.get("url"),
                    "dates": event.get("dates"),
                    "venue": event.get("_embedded", {}).get("venues", [{}])[0] if event.get("_embedded") else {},
                    "attractions": event.get("_embedded", {}).get("attractions", []) if event.get("_embedded") else [],
                    "price_ranges": event.get("priceRanges", []),
                    "images": event.get("images", [])
                }
                normalized_events.append(normalized_event)
            
            return normalized_events
    
    async def get_events_by_city(self, city: str, radius: int = 50) -> List[Dict[str, Any]]:
        """
        Get events in a specific city.
        
        Args:
            city: City name
            radius: Search radius in miles
            
        Returns:
            List of raw event data from TicketMaster
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/events.json",
                params={
                    "apikey": self.api_key,
                    "city": city,
                    "radius": radius,
                    "size": 20
                }
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            
            if "_embedded" not in data or "events" not in data["_embedded"]:
                return []
            
            return data["_embedded"]["events"]
