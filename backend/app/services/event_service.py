from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository

from app.mappers.event_document_mapper import EventDocumentMapper
from app.mappers.event_response_mapper import EventResponseMapper


class EventService:

    def __init__(
        self,
        event_repository: EventRepository,
        venue_repository: VenueRepository,
    ):
        self.event_repository = event_repository
        self.venue_repository = venue_repository

    async def get_artist_events(
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

            responses.append(

                EventResponseMapper.from_domain(
                    event=event,
                    venue=venue,
                )
            )

        return responses