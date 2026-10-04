from app.domain.event import Event
from app.domain.event_schedule import is_past
from app.schemas.event_response import (
    EventResponse,
    LineupEntryResponse,
)
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

            ends_at=event.ends_at,

            is_past=is_past(event),

            event_type=event.event_type,

            date_status=event.date_status,

            lineup=[
                LineupEntryResponse(
                    name=entry.name,
                    songkick_id=entry.songkick_id,
                    slug=entry.slug,
                    url=entry.url,
                    image=entry.image,
                    genres=entry.genres,
                    order=entry.order,
                )
                for entry in event.lineup
            ],

            ticket_url=event.ticket_url,

            free=event.free,

            sold_out=event.sold_out,

            venue_slug=event.venue_slug,

            venue=venue_response,

            artist_slugs=event.artist_slugs,

            artist_slug=(
                event.artist_slug
                if event.artist_slug
                else None
            ),

            festival=event.festival,

            location=event.location,

            source=event.source,

            going_count=event.going_count,

            maybe_count=event.maybe_count,

            went_count=event.went_count,
        )