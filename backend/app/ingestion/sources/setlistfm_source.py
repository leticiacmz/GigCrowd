from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime, timedelta, UTC


class SetlistFmSource:
    """Source for fetching event data from Setlist.fm API"""
    
    BASE_URL = "https://api.setlist.fm/rest/1.0"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Accept": "application/json",
            "x-api-key": api_key
        }
    
    async def search_events(
        self, 
        query: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for events by artist name with optional date filtering.
        
        Args:
            query: Artist name or search query
            start_date: Start date for filtering (default: 2 years ago for past events)
            end_date: End date for filtering (default: current date for past events)
        
        Returns:
            List of normalized event data
        """
        async with httpx.AsyncClient() as client:
            # Search setlists directly by artist name
            response = await client.get(
                f"{self.BASE_URL}/search/setlists",
                params={"artistName": query},
                headers=self.headers
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            setlists = data.get("setlist", [])
            
            events = []
            for setlist in setlists:
                event = self._normalize_setlist(setlist, start_date, end_date)
                if event:
                    events.append(event)
            
            return events
    
    async def get_artist_events(
        self, 
        mbid: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get events for a specific artist by MusicBrainz ID with date filtering.
        
        Args:
            mbid: MusicBrainz ID of the artist
            start_date: Start date for filtering (default: 2 years ago)
            end_date: End date for filtering (default: current date)
        
        Returns:
            List of normalized event data filtered by date range
        """
        # Set default date range for past events (2 years back)
        if not start_date:
            start_date = datetime.now(UTC) - timedelta(days=730)  # 2 years
        if not end_date:
            end_date = datetime.now(UTC)
        
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
                event = self._normalize_setlist(setlist, start_date, end_date)
                if event:
                    events.append(event)
            
            return events
    
    def _normalize_setlist(
        self, 
        setlist: Dict[str, Any],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize setlist data to standard event format with date filtering.
        
        Args:
            setlist: Raw setlist data from API
            start_date: Start date for filtering
            end_date: End date for filtering
        
        Returns:
            Normalized event data or None if outside date range
        """
        try:
            venue = setlist.get("venue", {})
            city = venue.get("city", {})
            country = city.get("country", {})
            
            event_date = setlist.get("eventDate")
            if event_date:
                # Parse date from DD-MM-YYYY format (naive datetime)
                date_obj = datetime.strptime(event_date, "%d-%m-%Y")
                
                # Remove timezone from start_date and end_date if present for comparison
                start_date_naive = start_date.replace(tzinfo=None) if start_date and start_date.tzinfo else start_date
                end_date_naive = end_date.replace(tzinfo=None) if end_date and end_date.tzinfo else end_date
                
                # Filter by date range if provided
                if start_date_naive and date_obj < start_date_naive:
                    return None
                if end_date_naive and date_obj > end_date_naive:
                    return None
            else:
                return None
            
            # Extract setlist songs
            sets_data = setlist.get("sets", {})
            set_items = sets_data.get("set", [])
            
            songs = []
            if set_items:
                for set_item in set_items:
                    songs_in_set = set_item.get("song", [])
                    if songs_in_set:
                        for song in songs_in_set:
                            if isinstance(song, dict):
                                song_name = song.get("name", "")
                                if song_name:
                                    songs.append(song_name)
                            elif isinstance(song, str):
                                songs.append(song)
            
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
                "source": "setlistfm",
                "setlist": songs,
                "setlist_count": len(songs)
            }
        except Exception as e:
            print(f"Error normalizing setlist: {e}")
            return None
