from app.domain.venue import Venue
from app.utils.slug import generate_slug
from app.utils.text import normalize_text


class SongkickVenueMapper:
    @staticmethod
    def to_domain(songkick_event_data: dict) -> Venue:
        """
        Map Songkick venue data from event response to domain Venue.
        Properly extracts Songkick venue ID for external_ids.
        """
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
        
        return Venue(
            external_ids={"songkick": str(venue_id)} if venue_id else {},
            name=songkick_event_data.get("venue_name", ""),
            normalized_name=normalize_text(songkick_event_data.get("venue_name", "")),
            slug=generate_slug(songkick_event_data.get("venue_name", "")),
            city=songkick_event_data.get("city_name", ""),
            country=songkick_event_data.get("country_name", ""),
            region=None,
            latitude=lat,
            longitude=lng,
            street_address=None,
            postal_code=None
        )
