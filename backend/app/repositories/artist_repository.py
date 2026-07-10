from app.domain.artist import Artist

from app.repositories.base import BaseRepository

from app.utils.text import normalize_text


class ArtistRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(db, "artists")

    async def get_by_slug(
        self,
        slug: str,
    ):

        return await self.find_one(
            {
                "slug": slug
            }
        )

    async def get_by_name(
        self,
        name: str,
    ):

        normalized = normalize_text(name)

        return await self.find_one(
            {
                "normalized_name": normalized
            }
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

    async def insert_artist(
        self,
        artist: Artist,
    ):

        return await self.insert_one(
            artist.model_dump()
        )