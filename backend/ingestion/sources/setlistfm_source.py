import httpx
from typing import List, Dict, Optional
from datetime import datetime
from .base_source import BaseSource


class SetlistFmSource(BaseSource):
    """Setlist.fm API source for concert data"""
    
    BASE_URL = "https://api.setlist.fm/rest/1.0"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)
        if not self.api_key:
            raise ValueError("Setlist.fm API key is required")
    
    async def fetch_events(self, artist_name: str, date_from: datetime, date_to: datetime) -> List[Dict]:
        """Fetch events from setlist.fm for an artist"""
        headers = {
            "Accept": "application/json",
            "x-api-key": self.api_key
        }
        
        # Search for artist
        artist = await self.fetch_artist_info(artist_name)
        if not artist:
            return []
        
        artist_mbid = artist.get("mbid")
        if not artist_mbid:
            return []
        
        # Fetch setlists for the artist
        url = f"{self.BASE_URL}/artist/{artist_mbid}/setlists"
        params = {
            "p": 1  # Page number
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                return []
            
            data = response.json()
            setlists = data.get("setlists", [])
            
            # Convert setlists to event format
            events = []
            for setlist in setlists:
                event = self._parse_setlist_to_event(setlist, artist_name)
                if event:
                    events.append(event)
            
            return events
    
    async def fetch_artist_info(self, artist_name: str) -> Optional[Dict]:
        """Fetch artist information from setlist.fm"""
        headers = {
            "Accept": "application/json",
            "x-api-key": self.api_key
        }
        
        url = f"{self.BASE_URL}/search/artists"
        params = {
            "artistName": artist_name,
            "p": 1
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                return None
            
            data = response.json()
            artists = data.get("artist", [])
            
            if artists and len(artists) > 0:
                return artists[0]
            
            return None
    
    def _parse_setlist_to_event(self, setlist: Dict, artist_name: str) -> Optional[Dict]:
        """Parse a setlist.fm setlist into our event format"""
        try:
            venue = setlist.get("venue", {})
            event_date = setlist.get("eventDate")
            
            if not event_date:
                return None
            
            # Parse date (format: dd-mm-yyyy)
            date_parts = event_date.split("-")
            if len(date_parts) != 3:
                return None
            
            day, month, year = date_parts
            event_datetime = datetime(int(year), int(month), int(day))
            
            return {
                "title": f"{artist_name} Live",
                "artist_name": artist_name,
                "venue_name": venue.get("name", "Unknown Venue"),
                "venue_id": venue.get("id"),
                "date": event_datetime,
                "location": venue.get("city", {}).get("name", "Unknown"),
                "country": venue.get("city", {}).get("country", {}).get("name", "Unknown"),
                "external_id": setlist.get("id"),
                "source": "setlistfm"
            }
        except Exception as e:
            print(f"Error parsing setlist: {e}")
            return None
