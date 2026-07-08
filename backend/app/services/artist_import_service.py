from typing import Any

from app.core.logger import get_logger
from app.repositories.artist_repository import ArtistRepository
from app.utils.text import normalize_text

logger = get_logger("artist_import")


class ArtistImportService:

    def __init__(
        self,
        artist_repository: ArtistRepository,
    ):
        self.artist_repository = artist_repository

    async def import_artist(
        self,
        artist: dict[str, Any],
    ) -> dict[str, Any]:

        existing = await self.artist_repository.get_by_name(
            artist["name"]
        )

        if existing:
            logger.info(
                f"Artist '{artist['name']}' already exists."
            )

            return existing

        artist["normalized_name"] = normalize_text(
            artist["name"]
        )

        await self.artist_repository.insert_one(
            artist
        )

        logger.info(
            f"Artist '{artist['name']}' imported."
        )

        return artist