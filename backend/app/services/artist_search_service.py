from app.core.logger import get_logger
from app.schemas.artist_search import ArtistSearchItem
from app.services.provider_manager import ProviderManager
from app.repositories.artist_repository import ArtistRepository
from app.utils.text import normalize_text

logger = get_logger("artist_search")


class ArtistSearchService:

    def __init__(
        self,
        provider_manager: ProviderManager,
        artist_repository: ArtistRepository,
    ):
        self.provider_manager = provider_manager
        self.artist_repository = artist_repository

    async def search_artist(
        self,
        query: str,
    ) -> list[ArtistSearchItem]:

        existing = await self.artist_repository.get_by_name(query)

        if existing:

            logger.info(
                f"Artist '{query}' found locally."
            )

            return [
                ArtistSearchItem(
                    provider="gigcrowd",
                    provider_artist_id=str(existing["_id"]),
                    name=existing["name"],
                    followers=existing.get("followers"),
                    image=existing.get("image"),
                )
            ]

        logger.info(
            f"Artist '{query}' not found locally. Searching Spotify."
        )

        return await self.provider_manager.search_artist(
            provider_name="spotify",
            query=query,
        )