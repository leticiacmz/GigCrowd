from app.domain.event import Event

from app.repositories.base import BaseRepository

from app.mappers.event_document_mapper import (
    EventDocumentMapper,
)


class EventRepository(BaseRepository):

    def __init__(self, db):

        super().__init__(
            db,
            "events",
        )

    async def get_by_external_id(
        self,
        provider: str,
        provider_event_id: str,
    ):

        document = await self.find_one(
            {
                "provider": provider,
                "provider_event_id": provider_event_id,
            }
        )

        if not document:
            return None

        return EventDocumentMapper.to_domain(
            document
        )

    async def insert_event(
        self,
        event: Event,
    ):

        await self.insert_one(
            event.model_dump(
                exclude={"id"},
            )
        )