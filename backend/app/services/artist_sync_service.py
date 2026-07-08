from typing import Any

from app.merge.artist_merge import ArtistMerge
from app.repositories.artist_repository import ArtistRepository
from app.services.provider_manager import ProviderManager

from app.core.logger import get_logger

logger = get_logger("artist_sync")


class ArtistSyncService:

    def __init__(
        self,
        artist_repository: ArtistRepository,
        provider_manager: ProviderManager,
    ):

        self.artist_repository = artist_repository

        self.provider_manager = provider_manager

    async def search_artist(
        self,
        query: str,
    ) -> dict[str, Any]:

        logger.info(f"Searching artist: {query}")

        existing = await self.artist_repository.get_by_name(query)

        if existing:

            logger.info("Artist found in cache.")

            return existing

        logger.info("Artist not found. Searching providers...")

        providers = await self.provider_manager.search_all(query)

        spotify = providers.get("spotify", [])

        bandsintown = providers.get("bandsintown", [])

        spotify_artist = spotify[0] if spotify else {}

        bandsintown_artist = bandsintown[0] if bandsintown else {}

        merged = ArtistMerge.merge(
            spotify_artist,
            bandsintown_artist,
        )

        await self.artist_repository.insert_one(
            merged
        )

        logger.info("Artist synchronized successfully.")

        return merged