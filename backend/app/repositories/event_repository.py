from app.domain.event import Event
from app.repositories.base import BaseRepository


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
        .sort("starts_at", -1)
        )
        
        return await cursor.to_list(length=1000)

    async def insert_event(
        self,
        event: Event,
    ):

        await self.insert_one(
            event.model_dump(
                exclude={"id"}
            )
        )