import httpx
from app.config import settings
from typing import List, Dict, Any, Optional
from datetime import datetime


class BandsintownSource:
    """Source for fetching events from Bandsintown using official API"""
    
    BASE_URL = "https://rest.bandsintown.com"
    
    def __init__(self):
        self.app_id = settings.BANDSINTOWN_APP_ID
        if not self.app_id:
            raise ValueError("BANDSINTOWN_APP_ID not configured in settings")
    
    async def get_artist(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """
        Get artist information from Bandsintown API.
        
        Args:
            artist_name: Artist name (URL-encoded)
            
        Returns:
            Artist data or None if not found
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/artists/{artist_name}",
                params={"app_id": self.app_id}
            )
            
            if response.status_code == 200:
                return response.json()
            return None
    
    async def search_events(
        self,
        artist_name: str,
        date_filter: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Search for events by artist name using Bandsintown API.
        
        Args:
            artist_name: Artist name (URL-encoded)
            date_filter: Date filter (upcoming, past, all, or date range like "2025-01-01,2026-12-31")
            
        Returns:
            List of normalized event data from Bandsintown
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/artists/{artist_name}/events",
                params={
                    "app_id": self.app_id,
                    "date": date_filter
                }
            )
            
            if response.status_code != 200:
                print(f"Bandsintown API error: {response.status_code}")
                return []
            
            events = response.json()
            return [self._normalize_event(event) for event in events]
    
    async def search_events_with_date_fallback(
        self,
        artist_name: str,
        specific_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for events with intelligent date fallback.
        
        Strategy:
        - If no specific_date: search all events (date_filter="all")
        - If specific_date provided:
          1. Try exact date first
          2. If no results, try range of 1 week before and after
          3. If still no results, return empty
        
        Args:
            artist_name: Artist name (URL-encoded)
            specific_date: Optional specific date in format "YYYY-MM-DD"
            
        Returns:
            List of normalized event data from Bandsintown
        """
        if not specific_date:
            # No specific date, search all events
            return await self.search_events(artist_name, date_filter="all")
        
        # Try exact date first
        events = await self.search_events(artist_name, date_filter=specific_date)
        if events:
            return events
        
        # Try range of 1 week before and after
        try:
            from datetime import datetime, timedelta
            date_obj = datetime.strptime(specific_date, "%Y-%m-%d")
            start_date = (date_obj - timedelta(days=7)).strftime("%Y-%m-%d")
            end_date = (date_obj + timedelta(days=7)).strftime("%Y-%m-%d")
            
            date_range = f"{start_date},{end_date}"
            events = await self.search_events(artist_name, date_filter=date_range)
            if events:
                return events
        except ValueError:
            # Invalid date format, just search all
            return await self.search_events(artist_name, date_filter="all")
        
        # No events found
        return []
    
    def _normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Bandsintown event data to standard format"""
        venue = event.get("venue", {})
        
        # Parse datetime from Bandsintown format
        datetime_str = event.get("datetime")
        date_obj = None
        if datetime_str:
            try:
                date_obj = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        
        # Determine status based on date
        status = "past" if date_obj and date_obj < datetime.now(date_obj.tzinfo) else "future"
        
        return {
            "title": event.get("title"),
            "artist_name": event.get("artist", {}).get("name", "Unknown"),
            "venue_name": venue.get("name", "Unknown Venue"),
            "date": date_obj.isoformat() if date_obj else None,
            "location": f"{venue.get('city', 'Unknown')}, {venue.get('country', 'Unknown')}",
            "city": venue.get("city", "Unknown"),
            "country": venue.get("country", "Unknown"),
            "description": event.get("description"),
            "image_url": event.get("image_url"),
            "ticket_url": event.get("url"),
            "status": status,
            "source": "bandsintown",
            "lineup": event.get("lineup", [])
        }
