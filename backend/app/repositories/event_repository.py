from app.domain.event import Event
from app.repositories.base import BaseRepository
from app.mappers.event_document_mapper import EventDocumentMapper
from datetime import datetime, UTC

class EventRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "events")

    async def get_by_external_id(
        self,
        provider: str,
        external_id: str,
    ):

        return await self.find_one(
            {
                f"external_ids.{provider}": external_id,
            }
        )

    async def get_by_artist_slug(
        self,
        artist_slug: str,
    ):

        cursor = (
            self.collection
            .find(
                {
                    "artist_slug": artist_slug,
                }
            )
            .sort(
                "starts_at",
                -1,
            )
        )

        documents = await cursor.to_list(
            length=1000,
        )

        return [

            EventDocumentMapper.to_domain(
                document
            )

            for document in documents
        ]

    async def insert_event(
        self,
        event: Event,
    ):

        await self.insert_one(
            event.model_dump(
                exclude={"id"}
            )
        )

    async def count_by_artist_slug(
        self,
        artist_slug: str,
    ) -> int:

        return await self.collection.count_documents(
            {
                    "artist_slug": artist_slug,
                }
            )


    async def count_upcoming_by_artist_slug(
        self,
        artist_slug: str,
    ) -> int:

        return await self.collection.count_documents(
            {
                "artist_slug": artist_slug,
                "starts_at": {
                    "$gte": datetime.now(UTC),
                },
            }
        )