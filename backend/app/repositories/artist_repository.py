from app.repositories.base import BaseRepository
from app.utils.slug import generate_slug


class ArtistRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "artists")

    async def get_by_slug(self, slug: str):
        return await self.find_one({"slug": slug})

    async def get_by_name(self, name: str):
        return await self.get_by_slug(
            generate_slug(name)
        )

    async def get_by_external_id(
        self,
        provider: str,
        external_id: str,
    ):
        return await self.find_one(
            {
                f"external_ids.{provider}": external_id
            }
        )