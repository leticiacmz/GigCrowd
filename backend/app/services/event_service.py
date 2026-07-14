from app.repositories.event_repository import EventRepository
from app.mappers.event_document_mapper import EventDocumentMapper
from app.mappers.event_response_mapper import EventResponseMapper


class EventService:

    def __init__(
        self,
        event_repository: EventRepository,
    ):
        self.event_repository = event_repository

    async def get_artist_events(
        self,
        artist_slug: str,
    ):

        documents = await self.event_repository.get_by_artist_slug(
            artist_slug
        )

        responses = []

        for document in documents:

            event = EventDocumentMapper.to_domain(
                document
            )

            responses.append(

                EventResponseMapper.from_domain(
                    event
                )
            )

        return responses