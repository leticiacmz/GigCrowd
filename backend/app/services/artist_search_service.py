from app.core.logger import get_logger
from app.schemas.artist_search import ArtistSearchItem
from app.services.provider_manager import ProviderManager
from app.repositories.artist_repository import ArtistRepository
from app.schemas.artist_response import ArtistResponse
from app.mappers.artist_response_mapper import ArtistResponseMapper

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

            return [
                ArtistResponseMapper.from_domain(
                    existing
                )
            ]
    
    
        logger.info(
            f"Artist '{query}' not found locally."
        )

        spotify_results = await self.provider_manager.search_artist(query)

        return [
            ArtistResponseMapper.from_search_item(
                artist
            )
            for artist in spotify_results
        ]
