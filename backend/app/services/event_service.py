from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.repositories.artist_repository import ArtistRepository

from app.mappers.event_response_mapper import EventResponseMapper
from app.services.lineup_artist_resolver import (
    LineupArtistResolver,
)


class EventService:

    def __init__(
        self,
        event_repository: EventRepository,
        venue_repository: VenueRepository,
        artist_repository: ArtistRepository,
    ):
        self.event_repository = event_repository
        self.venue_repository = venue_repository
        self.artist_repository = artist_repository

        # The same resolver the festival page uses, so an event page and a
        # festival page cannot disagree about which performers are linkable.
        self.resolver = LineupArtistResolver(
            artist_repository
        )

    async def get_event(
        self,
        event_id: str,
    ):

        event = await self.event_repository.get_by_id(
            event_id
        )

        if not event:
            return None

        venue = await self.venue_repository.get_by_slug(
            event.venue_slug
        )

        if not venue:
            return None

        return EventResponseMapper.from_domain(
            event=event,
            venue=venue,
            lineup_slugs=await self._lineup_slugs(
                event.lineup
            ),
        )

    async def _lineup_slugs(
        self,
        entries,
    ) -> dict[str, str]:
        """Which of these performers have a GigCrowd page, by Songkick id.

        An event page and a festival page show the same bill, so the same entry
        has to be pressable on both. The festival route has always resolved these
        ids; this one did not, which meant a performer GigCrowd has a page for -
        and has imported, and publishes a full discography for - rendered as a
        plain name on the event page while being one click away on the festival
        page.

        Resolution is by Songkick artist id and never by name: two acts can share
        a name, and a wrong link is worse than no link. An id with no page here is
        simply absent from the map, and that absence is what renders the entry as
        a plain name rather than as a broken link.

        Resolved at read time and handed to the mapper rather than written onto
        the response afterwards. Pydantic does not validate on assignment, so
        assigning a list of plain dictionaries over a list of models replaces
        them silently - and the stored lineup must not learn about this either
        way, because "does this catalogue have a page for that id" changes every
        time an artist is imported.
        """

        ids = [
            entry.songkick_id
            for entry in (entries or [])
            if getattr(entry, "songkick_id", None)
        ]

        if not ids:
            return {}

        return await self.resolver.resolve(ids)

    async def get_upcoming_artist_events(
        self,
        artist_slug: str,
    ):

        events = await self.event_repository.get_by_artist_slug(
            artist_slug
        )

        responses = []

        for event in events:

            venue = await self.venue_repository.get_by_slug(
                event.venue_slug
            )

            if not venue:
                continue

            responses.append(
                EventResponseMapper.from_domain(
                    event=event,
                    venue=venue,
                )
            )

        return responses

    async def get_artist_events(
        self,
        artist_slug: str,
    ):

        events = await self.event_repository.get_upcoming_by_artist_slug(
            artist_slug,
            limit=6,
        )

        responses = []

        for event in events:

            venue = await self.venue_repository.get_by_slug(
                event.venue_slug
            )

            if not venue:
                continue

            responses.append(
                EventResponseMapper.from_domain(
                    event=event,
                    venue=venue,
                )
            )

        return responses

    async def get_all_artist_events(
        self,
        artist_slug: str,
    ):

        events = await self.event_repository.get_all_by_artist_slug(
            artist_slug
        )

        responses = []

        for event in events:

            venue = await self.venue_repository.get_by_slug(
                event.venue_slug
            )

            if not venue:
                continue

            responses.append(
                EventResponseMapper.from_domain(
                    event=event,
                    venue=venue,
                )
            )

        return responses