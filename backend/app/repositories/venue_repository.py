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

    @staticmethod
    def _present_fields(venue: Venue) -> dict:
        """The fields this venue actually states.

        A re-read of the same venue routinely comes back thinner than the
        record it is updating: the listing that named the city this week may
        only carry the name next week. `$set`-ing every field blindly would
        erase what is already stored with a value the source simply did not
        repeat, and a venue with no city is worse than the one before the
        update.

        Blank means "the source said nothing" and is dropped. An explicit
        empty is indistinguishable from an absent field on a scrape, so it is
        never treated as information - clearing a stored value would need a
        deliberate operation, not an incomplete reading.
        """

        dumped = venue.model_dump(
            exclude={
                "id",
                "external_ids",
            },
        )

        return {
            key: value
            for key, value in dumped.items()
            if value not in (None, "", [], {})
        }

    @staticmethod
    def _present_external_ids(
        external_ids: dict[str, str],
    ) -> dict[str, str]:
        """Only the ids actually stated, so a blank never masks a real one."""

        return {
            provider: external_id
            for provider, external_id in external_ids.items()
            if external_id
        }

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

                update_data = self._present_fields(
                    venue,
                )

                if update_data:

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

            # Stored ids first, so a provider id already recorded is never
            # replaced by an empty one from an incomplete reading.
            merged_external_ids = {
                **self._present_external_ids(
                    existing_external_ids,
                ),
                **self._present_external_ids(
                    venue.external_ids,
                ),
            }

            update_data = self._present_fields(
                venue,
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