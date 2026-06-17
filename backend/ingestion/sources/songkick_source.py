import httpx
from typing import List, Dict, Optional
from datetime import datetime
from .base_source import BaseSource


class SongkickSource(BaseSource):
    """Songkick API source for concert data (placeholder for scraping implementation)"""
    
    BASE_URL = "https://api.songkick.com/api/3.0"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)
        if not self.api_key:
            raise ValueError("Songkick API key is required")
    
    async def fetch_events(self, artist_name: str, date_from: datetime, date_to: datetime) -> List[Dict]:
        """Fetch events from Songkick for an artist"""
        # This would implement the Songkick API call
        # For now, return empty list as placeholder
        headers = {
            "Accept": "application/json"
        }
        
        url = f"{self.BASE_URL}/search/artists.json"
        params = {
            "apikey": self.api_key,
            "query": artist_name
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                return []
            
            data = response.json()
            results = data.get("resultsPage", {}).get("results", {})
            artists = results.get("artist", [])
            
            if not artists:
                return []
            
            artist_id = artists[0].get("id")
            
            # Fetch events for the artist
            events_url = f"{self.BASE_URL}/artists/{artist_id}/calendar.json"
            events_params = {
                "apikey": self.api_key,
                "min_date": date_from.strftime("%Y-%m-%d"),
                "max_date": date_to.strftime("%Y-%m-%d")
            }
            
            events_response = await client.get(events_url, headers=headers, params=events_params)
            if events_response.status_code != 200:
                return []
            
            events_data = events_response.json()
            events_results = events_data.get("resultsPage", {}).get("results", {})
            events = events_results.get("event", [])
            
            return [self._parse_event_to_dict(event) for event in events]
    
    async def fetch_artist_info(self, artist_name: str) -> Optional[Dict]:
        """Fetch artist information from Songkick"""
        headers = {
            "Accept": "application/json"
        }
        
        url = f"{self.BASE_URL}/search/artists.json"
        params = {
            "apikey": self.api_key,
            "query": artist_name
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                return None
            
            data = response.json()
            results = data.get("resultsPage", {}).get("results", {})
            artists = results.get("artist", [])
            
            if artists and len(artists) > 0:
                return {
                    "id": artists[0].get("id"),
                    "name": artists[0].get("displayName"),
                    "uri": artists[0].get("uri")
                }
            
            return None
    
    def _parse_event_to_dict(self, event: Dict) -> Dict:
        """Parse a Songkick event into our format"""
        venue = event.get("venue", {})
        location = venue.get("city", {})
        
        return {
            "title": event.get("displayName", ""),
            "artist_name": "",  # Would need to be extracted
            "venue_name": venue.get("displayName", ""),
            "venue_id": venue.get("id"),
            "date": datetime.fromisoformat(event.get("start", {}).get("date", "")),
            "location": location.get("displayName", ""),
            "country": location.get("country", {}).get("displayName", ""),
            "external_id": str(event.get("id")),
            "source": "songkick"
        }
