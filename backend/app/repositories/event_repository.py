from app.domain.event import Event

from app.repositories.base import BaseRepository


class EventRepository(BaseRepository):

    def __init__(self, db):

        super().__init__(
            db,
            "events",
        )

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

    async def insert_event(
        self,
        event: Event,
    ):

        await self.insert_one(
            event.model_dump()
        )