from typing import Dict, Optional
from datetime import datetime


class EventNormalizer:
    """Normalizes event data from various sources into a unified format"""
    
    @staticmethod
    def normalize(raw_event: Dict, source: str) -> Dict:
        """
        Normalize event data from a source into our unified format
        
        Args:
            raw_event: Raw event data from source
            source: Name of the source (setlistfm, songkick, etc.)
        
        Returns:
            Normalized event dictionary
        """
        normalized = {
            "title": raw_event.get("title", ""),
            "venue_name": raw_event.get("venue_name", ""),
            "date": EventNormalizer._parse_date(raw_event.get("date")),
            "location": EventNormalizer._format_location(raw_event),
            "latitude": raw_event.get("latitude"),
            "longitude": raw_event.get("longitude"),
            "description": raw_event.get("description"),
            "image_url": raw_event.get("image_url"),
            "ticket_url": raw_event.get("ticket_url"),
            "price_min": raw_event.get("price_min"),
            "price_max": raw_event.get("price_max"),
            "source": source,
            "external_id": raw_event.get("external_id"),
            "raw_data": raw_event  # Keep original data for reference
        }
        
        return normalized
    
    @staticmethod
    def _parse_date(date_input) -> Optional[datetime]:
        """Parse date from various formats"""
        if isinstance(date_input, datetime):
            return date_input
        
        if isinstance(date_input, str):
            # Try common date formats
            formats = [
                "%Y-%m-%d",
                "%d-%m-%Y",
                "%Y/%m/%d",
                "%d/%m/%Y",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_input, fmt)
                except ValueError:
                    continue
        
        return None
    
    @staticmethod
    def _format_location(event: Dict) -> str:
        """Format location from event data"""
        location = event.get("location", "")
        country = event.get("country", "")
        
        if location and country:
            return f"{location}, {country}"
        elif location:
            return location
        elif country:
            return country
        
        return "Unknown"
    
    @staticmethod
    def normalize_artist(raw_artist: Dict, source: str) -> Dict:
        """Normalize artist data from various sources"""
        normalized = {
            "name": raw_artist.get("name", raw_artist.get("displayName", "")),
            "spotify_id": raw_artist.get("spotify_id"),
            "image_url": raw_artist.get("image_url"),
            "genres": raw_artist.get("genres", []),
            "bio": raw_artist.get("bio"),
            "source": source,
            "external_id": raw_artist.get("id"),
            "raw_data": raw_artist
        }
        
        return normalized
