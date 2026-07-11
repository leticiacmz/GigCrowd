from app.domain.venue import Venue

from app.repositories.base import BaseRepository

from app.mappers.venue_document_mapper import (
    VenueDocumentMapper,
)

from app.utils.slug import generate_slug


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

        document = await self.find_one(
            {
                "slug": slug,
            }
        )

        if not document:
            return None

        return VenueDocumentMapper.to_domain(
            document
        )

    async def get_by_external_id(
        self,
        provider: str,
        provider_venue_id: str,
    ):

        document = await self.find_one(
            {
                "provider": provider,
                "provider_venue_id": provider_venue_id,
            }
        )

        if not document:
            return None

        return VenueDocumentMapper.to_domain(
            document
        )

    async def generate_unique_slug(
        self,
        name: str,
    ) -> str:

        base_slug = generate_slug(
            name
        )

        slug = base_slug

        counter = 2

        while await self.get_by_slug(
            slug
        ):

            slug = f"{base_slug}-{counter}"

            counter += 1

        return slug

    async def insert_venue(
        self,
        venue: Venue,
    ):

        await self.insert_one(
            venue.model_dump(
                exclude={"id"},
            )
        )