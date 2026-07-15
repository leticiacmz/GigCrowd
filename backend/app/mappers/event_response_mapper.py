from app.domain.event import Event
from app.schemas.event_response import EventResponse
from app.schemas.venue_response import VenueResponse


class EventResponseMapper:

    @staticmethod
    def from_domain(
        event: Event,
        venue,
    ) -> EventResponse:

        venue_response = None

        if venue:

            venue_response = VenueResponse(

                id=venue.get("id"),

                slug=venue.get("slug"),

                name=venue.get("name"),

                city=venue.get("city"),

                country=venue.get("country"),

                latitude=venue.get("latitude"),

                longitude=venue.get("longitude"),
            )

        return EventResponse(

            id=event.id,

            title=event.title,

            starts_at=event.starts_at,

            ticket_url=event.ticket_url,

            venue_slug=event.venue_slug,

            venue=venue_response,
        )