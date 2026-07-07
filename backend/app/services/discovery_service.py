from typing import Any

from app.core.logger import get_logger
from app.repositories.artist_repository import ArtistRepository
from app.services.provider_manager import ProviderManager

logger = get_logger("discovery")


class DiscoveryService:

    def __init__(
        self,
        artist_repository: ArtistRepository,
        provider_manager: ProviderManager,
    ):
        self.artist_repository = artist_repository
        self.provider_manager = provider_manager

    async def search_artist(
        self,
        provider_name: str,
        query: str,
    ) -> list[dict[str, Any]]:

        logger.info(
            f"Searching '{query}' using provider '{provider_name}'"
        )

        return await self.provider_manager.search_artist(
            provider_name,
            query,
        )

    async def get_or_create_artist(
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

        await self.artist_repository.insert_one(artist)

        logger.info(
            f"Artist '{artist['name']}' created."
        )

        return artist