from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime


class SetlistFmSource:
    """Source for fetching event data from Setlist.fm API"""
    
    BASE_URL = "https://api.setlist.fm/rest/1.0"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Accept": "application/json",
            "x-api-key": api_key
        }
    
    async def search_events(self, query: str) -> List[Dict[str, Any]]:
        """Search for events by artist name"""
        async with httpx.AsyncClient() as client:
            # Search for artist first
            response = await client.get(
                f"{self.BASE_URL}/search/artists",
                params={"artistName": query},
                headers=self.headers
            )
            
            if response.status_code != 200:
                return []
            
            artists = response.json().get("artist", [])
            if not artists:
                return []
            
            # Get first artist's MusicBrainz ID
            artist = artists[0] if isinstance(artists, list) else artists
            mbid = artist.get("mbid")
            
            if not mbid:
                return []
            
            # Get artist's setlists
            return await self.get_artist_events(mbid)
    
    async def get_artist_events(self, mbid: str) -> List[Dict[str, Any]]:
        """Get events for a specific artist by MusicBrainz ID"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/artist/{mbid}/setlists",
                headers=self.headers
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            setlists = data.get("setlist", [])
            
            events = []
            for setlist in setlists:
                event = self._normalize_setlist(setlist)
                if event:
                    events.append(event)
            
            return events
    
    def _normalize_setlist(self, setlist: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize setlist data to standard event format"""
        try:
            venue = setlist.get("venue", {})
            city = venue.get("city", {})
            country = city.get("country", {})
            
            event_date = setlist.get("eventDate")
            if event_date:
                # Parse date from DD-MM-YYYY format
                date_obj = datetime.strptime(event_date, "%d-%m-%Y")
            else:
                return None
            
            return {
                "title": f"{setlist.get('artist', {}).get('name', 'Unknown')} Live",
                "artist_name": setlist.get("artist", {}).get("name", "Unknown"),
                "venue_name": venue.get("name", "Unknown Venue"),
                "date": date_obj.isoformat(),
                "location": f"{city.get('name', 'Unknown')}, {country.get('name', 'Unknown')}",
                "city": city.get("name", "Unknown"),
                "country": country.get("name", "Unknown"),
                "description": f"Setlist from {event_date}",
                "image_url": None,
                "ticket_url": None,
                "status": "past",
                "source": "setlistfm"
            }
        except Exception as e:
            print(f"Error normalizing setlist: {e}")
            return None
