from app.repositories.base import BaseRepository


class ArtistRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "artists")

    async def get_by_name(self, name: str):
        return await self.find_one({"name": name})