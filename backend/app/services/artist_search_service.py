from typing import Any

from app.core.logger import get_logger
from app.services.provider_manager import ProviderManager

logger = get_logger("artist_search")


class ArtistSearchService:
    """
    Responsible only for searching artists in external providers.

    This service does not:
    - save artists
    - import artists
    - access MongoDB
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
    ):
        self.provider_manager = provider_manager

    async def search_artist(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        """
        Search artists using the default provider.

        Today:
            Spotify

        Future:
            Spotify + cache + other providers.
        """

        logger.info(f"Searching artist '{query}'")

        return await self.provider_manager.search_artist(
            provider_name="spotify",
            query=query,
        )