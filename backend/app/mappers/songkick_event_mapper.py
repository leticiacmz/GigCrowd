from app.domain.event import Event
from app.domain.venue import Venue
from datetime import datetime


class SongkickEventMapper:
    @staticmethod
    def to_domain(songkick_event_data: dict, artist_slugs: list[str]) -> tuple[Event, Venue]:
        """
        Map Songkick event data to domain Event and Venue.
        Preserves complete artist relationship via artist_slugs array.
        """
        # Parse date
        starts_at = None
        if songkick_event_data.get("date"):
            try:
                starts_at = datetime.fromisoformat(
                    songkick_event_data["date"].replace("Z", "+00:00")
                )
            except ValueError:
                pass
        
        # Parse end date for festivals
        ends_at = None
        if songkick_event_data.get("end_date"):
            try:
                ends_at = datetime.fromisoformat(
                    songkick_event_data["end_date"].replace("Z", "+00:00")
                )
            except ValueError:
                pass
        
        # Create venue
        venue = SongkickEventMapper._create_venue(songkick_event_data)
        
        # Create event
        event = Event(
            external_ids={"songkick": songkick_event_data.get("id")},
            artist_slugs=artist_slugs,
            artist_slug=artist_slugs[0] if artist_slugs else "",
            venue_slug=venue.slug,
            title=songkick_event_data.get("name"),
            starts_at=starts_at,
            ends_at=ends_at,
            event_type=songkick_event_data.get("event_type", "Concert"),
            sold_out=False,
            free=False,
            ticket_url=None,
            going_count=0,
            maybe_count=0,
            went_count=0
        )
        
        return (event, venue)
    
    @staticmethod
    def _create_venue(songkick_event_data: dict) -> Venue:
        """Create Venue from Songkick event data."""
        from app.utils.slug import generate_slug
        from app.utils.text import normalize_text
        
        # Parse geolocation
        lat, lng = None, None
        geolocation = songkick_event_data.get("geolocation")
        if geolocation:
            try:
                lat_str, lng_str = geolocation.split(",")
                lat = float(lat_str)
                lng = float(lng_str)
            except (ValueError, AttributeError):
                pass
        
        venue_id = songkick_event_data.get("venue_id")
        venue_name = songkick_event_data.get("venue_name", "")
        
        return Venue(
            external_ids={"songkick": str(venue_id)} if venue_id else {},
            name=venue_name,
            normalized_name=normalize_text(venue_name),
            slug=generate_slug(venue_name),
            city=songkick_event_data.get("city_name", ""),
            country=songkick_event_data.get("country_name", ""),
            region=None,
            latitude=lat,
            longitude=lng,
            street_address=None,
            postal_code=None
        )
