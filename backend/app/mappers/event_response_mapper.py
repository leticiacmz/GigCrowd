from app.domain.event import Event
from app.schemas.event_response import EventResponse


class EventResponseMapper:

    @staticmethod
    def from_domain(
        event: Event,
    ) -> EventResponse:

        return EventResponse(

            id=event.id,

            title=event.title,

            starts_at=event.starts_at,

            ticket_url=event.ticket_url,

            free=event.free,

            sold_out=event.sold_out,

            venue_slug=event.venue_slug,
        )