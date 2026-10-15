from typing import Optional

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
        lineup_slugs: Optional[dict] = None,
    ) -> EventResponse:
        """One event, shaped for the client.

        `lineup_slugs` maps a lineup entry's Songkick artist id to the GigCrowd
        page that exists for it. It is supplied by the caller rather than
        resolved here, because the mapper has no repository and the answers
        change every time an artist is imported.

        The lineup deliberately carries no artist-document photographs. They
        used to be looked up by the caller and merged in beside the link, but
        a lineup is read as names - and the lookup existed only to serve this
        list. An entry's own stored `image` still passes through untouched;
        nothing is fetched to fill it.
        """

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

            date_source_checked_at=event.date_source_checked_at,

            lineup=[
                LineupEntryResponse(
                    name=entry.name,
                    songkick_id=entry.songkick_id,
                    slug=entry.slug,
                    url=entry.url,
                    # An entry's own stored image, as import wrote it. No
                    # artist-document photo is merged in: a lineup renders
                    # names and links, and nothing is looked up to dress it.
                    image=entry.image,
                    genres=entry.genres,
                    order=entry.order,
                    # Which of these performers this catalogue has a page for.
                    # Passed in rather than looked up here, so the mapper stays
                    # the one place a response is shaped and does not need a
                    # repository. An id with no entry in the map resolves to
                    # `None`, which the client renders as a plain name - never as
                    # a link to somewhere unverified, and never as an excuse to
                    # create the artist on the spot.
                    artist_slug=(
                        (lineup_slugs or {}).get(
                            str(entry.songkick_id)
                        )
                        if entry.songkick_id
                        else None
                    ),
                )
                for entry in event.lineup
            ],

            ticket_url=event.ticket_url,

            description=event.description,

            image_url=event.image_url,

            event_status=event.event_status,

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