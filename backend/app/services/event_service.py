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

        # A missing venue is a data gap, not a reason to hide the event. The
        # venue document is written by a separate lookup, so an event whose
        # venue row was never created - or was keyed differently by an older
        # import - still has a title, a date and a lineup worth showing, and
        # the response schema already models `venue` as optional. Returning
        # `None` here made the event page 404 for a record that exists, which
        # is the one outcome that cannot be corrected by the reader.
        venue = await self.venue_repository.get_by_slug(
            event.venue_slug
        )

        lineup_slugs = await self._lineup_slugs(
            event.lineup
        )

        # No photo lookup follows. The lineup used to fetch the resolved
        # artists' photographs in a second query, and that query existed only
        # to put faces on this list; the bill renders as names and links, so
        # the resolver's single query is all this page asks of the artists
        # collection.
        return EventResponseMapper.from_domain(
            event=event,
            venue=venue,
            lineup_slugs=lineup_slugs,
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

            # A venue-less event is still an event. Skipping it here dropped
            # rows out of artist pages while the same event remained reachable
            # by id, so the listing and the detail page disagreed about what
            # exists. The mapper renders `venue: null` and the client shows the
            # event without a venue line.
            venue = await self.venue_repository.get_by_slug(
                event.venue_slug
            )

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

            # A venue-less event is still an event. Skipping it here dropped
            # rows out of artist pages while the same event remained reachable
            # by id, so the listing and the detail page disagreed about what
            # exists. The mapper renders `venue: null` and the client shows the
            # event without a venue line.
            venue = await self.venue_repository.get_by_slug(
                event.venue_slug
            )

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
        offset: int = 0,
        limit: int = 1000,
    ):
        """The artist's whole listing, windowed by `offset`/`limit`.

        Defaults keep the original behaviour - the first 1000 rows of the
        year-grouped history - and the endpoint caps `limit` at that same
        bound, so this is pagination over what a call already could read,
        never a wider read.
        """

        events = await self.event_repository.get_all_by_artist_slug(
            artist_slug,
            offset=offset,
            limit=limit,
        )

        responses = []

        for event in events:

            # A venue-less event is still an event. Skipping it here dropped
            # rows out of artist pages while the same event remained reachable
            # by id, so the listing and the detail page disagreed about what
            # exists. The mapper renders `venue: null` and the client shows the
            # event without a venue line.
            venue = await self.venue_repository.get_by_slug(
                event.venue_slug
            )

            responses.append(
                EventResponseMapper.from_domain(
                    event=event,
                    venue=venue,
                )
            )

        return responses