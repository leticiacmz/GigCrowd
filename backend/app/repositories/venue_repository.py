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

    # NEW: Upsert venue by external ID
    async def upsert_venue(
        self,
        venue: Venue,
    ) -> bool:
        """
        Upsert venue using external_ids for deduplication.
        Returns:
            True  -> created
            False -> updated
        """
        # Check if venue exists by external ID
        for provider, external_id in venue.external_ids.items():
            existing = await self.find_one({
                f"external_ids.{provider}": external_id
            })
            if existing:
                # Update existing venue
                await self.collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": venue.model_dump(exclude={"id", "external_ids"})}
                )
                return False
        
        # Check by normalized name as fallback
        existing = await self.get_by_name(venue.name)
        if existing:
            # Merge external IDs
            existing_external_ids = existing.get("external_ids", {})
            merged_external_ids = {**existing_external_ids, **venue.external_ids}
            await self.collection.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": venue.model_dump(exclude={"id", "external_ids"}),
                    "$set": {"external_ids": merged_external_ids}
                }
            )
            return False
        
        # Insert new venue
        await self.insert_venue(venue)
        return True