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

    async def get_by_external_id(
        self,
        provider: str,
        external_id: str,
    ):

        if not external_id:
            return None

        return await self.find_one(
            {
                f"external_ids.{provider}": external_id
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

    async def upsert_venue(
        self,
        venue: Venue,
    ) -> bool:
        """
        Upsert venue using external IDs for deduplication.

        Returns:
            True  -> created
            False -> updated
        """

        # --------------------------------------------------
        # Check by external ID
        # --------------------------------------------------

        for provider, external_id in venue.external_ids.items():

            if not external_id:
                continue

            existing = await self.get_by_external_id(
                provider,
                external_id,
            )

            if existing:

                update_data = venue.model_dump(
                    exclude={
                        "id",
                        "external_ids",
                    }
                )

                await self.collection.update_one(
                    {
                        "_id": existing["_id"]
                    },
                    {
                        "$set": update_data
                    }
                )

                return False

        # --------------------------------------------------
        # Fallback: normalized name
        # --------------------------------------------------

        existing = await self.get_by_name(
            venue.name
        )

        if existing:

            existing_external_ids = (
                existing.get(
                    "external_ids",
                    {}
                )
            )

            merged_external_ids = {
                **existing_external_ids,
                **venue.external_ids,
            }

            update_data = venue.model_dump(
                exclude={
                    "id",
                    "external_ids",
                }
            )

            # IMPORTANT:
            # Keep the external IDs together with the
            # other fields in the same $set.
            update_data["external_ids"] = (
                merged_external_ids
            )

            await self.collection.update_one(
                {
                    "_id": existing["_id"]
                },
                {
                    "$set": update_data
                }
            )

            return False

        # --------------------------------------------------
        # Insert
        # --------------------------------------------------

        await self.insert_venue(
            venue
        )

        return True