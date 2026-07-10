from app.core.logger import get_logger
from app.schemas.artist_search import ArtistSearchItem
from app.services.provider_manager import ProviderManager
from app.repositories.artist_repository import ArtistRepository

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

                    provider="spotify",

                    provider_artist_id=existing["external_ids"]["spotify"],

                    name=existing["name"],

                    followers=existing.get("followers"),

                    image=existing.get("image"),

                    popularity=existing.get("popularity"),

                    genres=existing.get("genres", []),

                    verified=existing.get("verified", False),

                    is_imported=True,
                )
            ]
        logger.info(
            f"Artist '{query}' not found locally."
        )

        return await self.provider_manager.search_artist(query)