import httpx
from typing import List, Dict, Any, Optional


class SetlistFmSource:
    """Source for fetching events from Setlist.fm API"""
    
    BASE_URL = "https://api.setlist.fm/rest/1.0"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Accept": "application/json",
            "x-api-key": api_key
        }
    
    async def search_events(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for events by artist name, venue, or city.
        
        Args:
            query: Search query (artist name, venue, or city)
            
        Returns:
            List of raw event data from Setlist.fm
        """
        async with httpx.AsyncClient() as client:
            # Try searching by artist first
            response = await client.get(
                f"{self.BASE_URL}/search/artists",
                headers=self.headers,
                params={"p": 1, "query": query}
            )
            
            if response.status_code != 200:
                return []
            
            artists = response.json().get("artist", [])
            
            if not artists:
                return []
            
            # Get setlists for the first artist
            artist_mbid = artists[0].get("mbid")
            
            if not artist_mbid:
                return []
            
            response = await client.get(
                f"{self.BASE_URL}/artist/{artist_mbid}/setlists",
                headers=self.headers,
                params={"p": 1}
            )
            
            if response.status_code != 200:
                return []
            
            setlists = response.json().get("setlist", [])
            
            # Convert setlists to event format
            events = []
            for setlist in setlists:
                event = {
                    "artist": setlist.get("artist", {}),
                    "venue": setlist.get("venue", {}),
                    "eventDate": setlist.get("eventDate"),
                    "tour": setlist.get("tour", {}),
                    "sets": setlist.get("sets", {}),
                    "id": setlist.get("id")
                }
                events.append(event)
            
            return events
    
    async def get_artist_events(self, artist_mbid: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get events for a specific artist by MusicBrainz ID.
        
        Args:
            artist_mbid: MusicBrainz ID of the artist
            limit: Maximum number of events to return
            
        Returns:
            List of raw event data from Setlist.fm
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/artist/{artist_mbid}/setlists",
                headers=self.headers,
                params={"p": 1}
            )
            
            if response.status_code != 200:
                return []
            
            setlists = response.json().get("setlist", [])[:limit]
            
            events = []
            for setlist in setlists:
                event = {
                    "artist": setlist.get("artist", {}),
                    "venue": setlist.get("venue", {}),
                    "eventDate": setlist.get("eventDate"),
                    "tour": setlist.get("tour", {}),
                    "sets": setlist.get("sets", {}),
                    "id": setlist.get("id")
                }
                events.append(event)
            
            return events
