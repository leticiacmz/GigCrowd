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

        responses = []

        for artist in spotify_results:

            responses.append(

                ArtistResponse(

                    provider=artist.provider,

                    provider_artist_id=artist.provider_artist_id,

                    name=artist.name,

                    followers=artist.followers,

                    image=artist.image,

                    genres=artist.genres,

                    popularity=artist.popularity,

                    verified=artist.verified,

                    is_imported=False,
                )
            )

        return responses