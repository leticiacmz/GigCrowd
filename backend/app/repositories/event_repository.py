from app.repositories.base import BaseRepository


class EventRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "events")

    async def get_by_artist_id(self, artist_id: str):
        return await self.find_many({"artist_id": artist_id})