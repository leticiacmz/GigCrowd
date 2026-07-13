from app.domain.event import Event
from app.domain.venue import Venue

from app.mappers.bandsintown_venue_mapper import (
    BandsintownVenueMapper,
)


class BandsintownEventMapper:

    @staticmethod
    def to_domain(
        payload: dict,
        artist_slug: str,
    ) -> tuple[Event, Venue]:

        venue = BandsintownVenueMapper.to_domain(
            payload["venue"]
        )

        offers = payload.get(
            "offers",
            [],
        )

        ticket_url = None

        if offers:

            ticket_url = offers[0].get(
                "url"
            )

        title = payload.get(
            "title"
        )

        if not title:

            title = (
                f"{payload['lineup'][0]} @ {venue.name}"
            )

        event = Event(

            external_ids={
                "bandsintown": payload["id"]
            },

            artist_slug=artist_slug,

            venue_slug=venue.slug,

            title=title,

            starts_at=(
                payload.get("starts_at")
                or payload.get("datetime")
            ),

            sold_out=payload.get(
                "sold_out",
                False,
            ),

            free=payload.get(
                "free",
                False,
            ),

            ticket_url=ticket_url,
        )

        return (
            event,
            venue,
        )