from typing import Dict, Any
from datetime import datetime


class EventNormalizer:
    """Normalizes event data from various sources to a standard format"""
    
    def normalize(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw event data to standard format.
        
        Args:
            raw_event: Raw event data from external API
            
        Returns:
            Normalized event data
        """
        artist = raw_event.get("artist", {})
        venue = raw_event.get("venue", {})
        
        # Parse date from Setlist.fm format (DD-MM-YYYY)
        event_date = self._parse_date(raw_event.get("eventDate"))
        
        # Build location string
        city = venue.get("city", {})
        location = f"{city.get('name', '')}, {city.get('country', {}).get('name', '')}"
        
        normalized = {
            "_id": raw_event.get("id", f"event_{datetime.utcnow().timestamp()}"),
            "title": f"{artist.get('name', 'Unknown Artist')} Concert",
            "artist_id": artist.get("mbid", ""),
            "artist_name": artist.get("name", "Unknown Artist"),
            "venue_name": venue.get("name", "Unknown Venue"),
            "venue_id": venue.get("id", ""),
            "date": event_date,
            "location": location,
            "city": city.get("name", ""),
            "country": city.get("country", {}).get("name", ""),
            "latitude": venue.get("city", {}).get("coords", {}).get("lat"),
            "longitude": venue.get("city", {}).get("coords", {}).get("long"),
            "description": raw_event.get("tour", {}).get("name", ""),
            "source": "setlistfm",
            "external_id": raw_event.get("id", ""),
            "status": "upcoming" if event_date >= datetime.utcnow() else "past",
            "going_count": 0,
            "maybe_count": 0,
            "went_count": 0,
            "attendees_count": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        return normalized
    
    def _parse_date(self, date_str: str) -> datetime:
        """
        Parse date string from Setlist.fm format.
        
        Args:
            date_str: Date string in DD-MM-YYYY format
            
        Returns:
            datetime object
        """
        if not date_str:
            return datetime.utcnow()
        
        try:
            # Setlist.fm format: DD-MM-YYYY
            parts = date_str.split("-")
            if len(parts) == 3:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime(year, month, day)
        except (ValueError, IndexError):
            pass
        
        return datetime.utcnow()
