from app.domain.event import Event
from app.schemas.event_response import EventResponse
from app.schemas.venue_response import VenueResponse


class EventResponseMapper:

    @staticmethod
    def from_domain(
        event: Event,
    ) -> EventResponse:

        venue = None

        if event.venue:
            venue = VenueResponse(
                id=event.venue.id,
                slug=event.venue.slug,
                name=event.venue.name,
                city=event.venue.city,
                country=event.venue.country,
                latitude=event.venue.latitude,
                longitude=event.venue.longitude,
            )

        return EventResponse(
            id=event.id,
            title=event.title,
            starts_at=event.starts_at,
            ticket_url=event.ticket_url,
            venue_slug=event.venue.slug if event.venue else None,
            venue=venue,
        )