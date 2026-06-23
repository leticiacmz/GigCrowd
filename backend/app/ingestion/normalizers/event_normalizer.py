from typing import Dict, Any
from datetime import datetime, UTC


class EventNormalizer:
    """Normalizes event data from various sources to a standard format"""
    
    def normalize(self, raw_event: Dict[str, Any], source: str = "setlistfm") -> Dict[str, Any]:
        """
        Normalize raw event data to standard format.
        
        Args:
            raw_event: Raw event data from external API
            source: Source API (setlistfm, ticketmaster, spotify, bandsintown)
            
        Returns:
            Normalized event data
        """
        if source == "setlistfm":
            return self._normalize_setlistfm(raw_event)
        elif source == "ticketmaster":
            return self._normalize_ticketmaster(raw_event)
        elif source == "spotify":
            return self._normalize_spotify(raw_event)
        elif source == "bandsintown":
            return self._normalize_bandsintown(raw_event)
        else:
            return self._normalize_setlistfm(raw_event)  # Default
    
    def _normalize_setlistfm(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Setlist.fm event data"""
        artist = raw_event.get("artist", {})
        venue = raw_event.get("venue", {})
        
        # Parse date from Setlist.fm format (DD-MM-YYYY)
        event_date = self._parse_date(raw_event.get("eventDate"))
        
        # Build location string
        city = venue.get("city", {})
        location = f"{city.get('name', '')}, {city.get('country', {}).get('name', '')}"
        
        normalized = {
            "_id": raw_event.get("id", f"event_{datetime.now(UTC).timestamp()}"),
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
            "status": "upcoming" if event_date >= datetime.now(UTC) else "past",
            "going_count": 0,
            "maybe_count": 0,
            "went_count": 0,
            "attendees_count": 0,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC)
        }
        
        return normalized
    
    def _normalize_ticketmaster(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize TicketMaster event data"""
        venue = raw_event.get("venue", {})
        dates = raw_event.get("dates", {}).get("start", {})
        attractions = raw_event.get("attractions", [])
        
        # Parse date from TicketMaster format
        event_date = self._parse_ticketmaster_date(dates.get("localDate"))
        
        # Get artist info
        artist_name = "Unknown Artist"
        artist_id = ""
        if attractions:
            artist_name = attractions[0].get("name", "Unknown Artist")
            artist_id = attractions[0].get("id", "")
        
        # Build location string
        city = venue.get("city", {})
        location = f"{city.get('name', '')}, {city.get('country', {}).get('name', '')}"
        
        # Get image
        images = raw_event.get("images", [])
        image_url = images[0].get("url") if images else None
        
        # Get ticket URL
        ticket_url = raw_event.get("url", "")
        
        normalized = {
            "_id": raw_event.get("id", f"event_{datetime.now(UTC).timestamp()}"),
            "title": raw_event.get("name", "Event"),
            "artist_id": artist_id,
            "artist_name": artist_name,
            "venue_name": venue.get("name", "Unknown Venue"),
            "venue_id": venue.get("id", ""),
            "date": event_date,
            "location": location,
            "city": city.get("name", ""),
            "country": city.get("country", {}).get("name", ""),
            "latitude": venue.get("location", {}).get("latitude"),
            "longitude": venue.get("location", {}).get("longitude"),
            "description": raw_event.get("description", ""),
            "image_url": image_url,
            "ticket_url": ticket_url,
            "source": "ticketmaster",
            "external_id": raw_event.get("id", ""),
            "status": "upcoming" if event_date >= datetime.now(UTC) else "past",
            "going_count": 0,
            "maybe_count": 0,
            "went_count": 0,
            "attendees_count": 0,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC)
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
            return datetime.now(UTC)
        
        try:
            # Setlist.fm format: DD-MM-YYYY
            parts = date_str.split("-")
            if len(parts) == 3:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime(year, month, day)
        except (ValueError, IndexError):
            pass
        
        return datetime.now(UTC)
    
    def _parse_ticketmaster_date(self, date_str: str) -> datetime:
        """
        Parse date string from TicketMaster format.
        
        Args:
            date_str: Date string in YYYY-MM-DD format
            
        Returns:
            datetime object
        """
        if not date_str:
            return datetime.now(UTC)
        
        try:
            # TicketMaster format: YYYY-MM-DD
            parts = date_str.split("-")
            if len(parts) == 3:
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime(year, month, day)
        except (ValueError, IndexError):
            pass
        
        return datetime.now(UTC)
    
    def _normalize_bandsintown(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Bandsintown event data"""
        # Parse date from Bandsintown format (varies)
        event_date = self._parse_bandsintown_date(raw_event.get("date"))
        
        normalized = {
            "_id": raw_event.get("id", f"event_{datetime.now(UTC).timestamp()}"),
            "title": raw_event.get("title", "Event"),
            "artist_id": raw_event.get("artist_id", ""),
            "artist_name": raw_event.get("title", "Unknown Artist").split(" at ")[0] if " at " in raw_event.get("title", "") else raw_event.get("title", "Unknown Artist"),
            "venue_name": raw_event.get("venue", "Unknown Venue"),
            "venue_id": "",
            "date": event_date,
            "location": raw_event.get("location", ""),
            "city": raw_event.get("location", "").split(",")[0] if "," in raw_event.get("location", "") else raw_event.get("location", ""),
            "country": raw_event.get("location", "").split(",")[-1] if "," in raw_event.get("location", "") else "",
            "latitude": None,
            "longitude": None,
            "description": "",
            "image_url": None,
            "ticket_url": raw_event.get("url", ""),
            "source": "bandsintown",
            "external_id": raw_event.get("id", ""),
            "status": "upcoming" if event_date >= datetime.now(UTC) else "past",
            "going_count": 0,
            "maybe_count": 0,
            "went_count": 0,
            "attendees_count": 0,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC)
        }
        
        return normalized
    
    def _parse_bandsintown_date(self, date_str: str) -> datetime:
        """Parse date string from Bandsintown format"""
        if not date_str:
            return datetime.now(UTC)
        
        try:
            # Try various date formats
            # Bandsintown uses formats like "Jun 15, 2024", "June 15, 2024", etc.
            from dateutil import parser
            return parser.parse(date_str)
        except:
            pass
        
        try:
            # Try ISO format
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            pass
        
        try:
            # Try YYYY-MM-DD format
            parts = date_str.split("-")
            if len(parts) == 3:
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime(year, month, day)
        except:
            pass
        
        return datetime.now(UTC)
    
    def _normalize_spotify(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Spotify event data"""
        normalized = {
            "_id": raw_event.get("id", f"event_{datetime.now(UTC).timestamp()}"),
            "title": raw_event.get("name", "Event"),
            "artist_id": raw_event.get("artist_id", ""),
            "artist_name": raw_event.get("artist_name", "Unknown Artist"),
            "venue_name": raw_event.get("venue_name", "Unknown Venue"),
            "venue_id": raw_event.get("venue_id", ""),
            "date": self._parse_spotify_date(raw_event.get("date")),
            "location": raw_event.get("location", ""),
            "city": raw_event.get("city", ""),
            "country": raw_event.get("country", ""),
            "latitude": raw_event.get("latitude"),
            "longitude": raw_event.get("longitude"),
            "description": raw_event.get("description", ""),
            "image_url": raw_event.get("image_url"),
            "source": "spotify",
            "external_id": raw_event.get("id", ""),
            "status": "upcoming" if self._parse_spotify_date(raw_event.get("date")) >= datetime.now(UTC) else "past",
            "going_count": 0,
            "maybe_count": 0,
            "went_count": 0,
            "attendees_count": 0,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC)
        }
        
        return normalized
    
    def _parse_spotify_date(self, date_str: str) -> datetime:
        """Parse date string from Spotify format"""
        if not date_str:
            return datetime.now(UTC)
        
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
        
        try:
            parts = date_str.split("-")
            if len(parts) == 3:
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime(year, month, day)
        except (ValueError, IndexError):
            pass
        
        return datetime.now(UTC)
