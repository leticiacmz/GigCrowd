from app.domain.venue import Venue
from app.utils.text import normalize_text
from app.utils.slug import generate_slug
from app.repositories.base import BaseRepository


class VenueRepository(BaseRepository):

    def __init__(self, db):

        super().__init__(
            db,
            "venues",
        )

    async def get_by_slug(
        self,
        slug: str,
    ):

        return await self.find_one(
            {
                "slug": slug,
            }
        )

    async def insert_venue(
        self,
        venue: Venue,
    ):

        await self.insert_one(
            venue.model_dump()
        )

    async def get_by_name(
        self,
        name: str,
    ):

        normalized = normalize_text(name)

        return await self.find_one(
            {
                "normalized_name": normalized,
            }
        )
    
    async def generate_unique_slug(
        self,
        name: str,
    ) -> str:

        base_slug = generate_slug(name)

        slug = base_slug

        counter = 2

        while await self.get_by_slug(slug):

            slug = f"{base_slug}-{counter}"

            counter += 1

        return slug