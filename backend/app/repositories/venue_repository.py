from app.repositories.base import BaseRepository


class VenueRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "venues")

    async def get_by_city(self, city: str):
        return await self.find_many({"city": city})