from app.core.logger import get_logger

from app.schemas.artist_search import ArtistSearchItem

from app.services.provider_manager import ProviderManager

from app.repositories.artist_repository import ArtistRepository

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


        logger.info(
            f"Searching artist: {query}"
        )


        spotify_results = await self.provider_manager.search_artist(
            query
        )


        return [

            ArtistResponseMapper.from_search_item(
                artist
            )

            for artist in spotify_results

        ]