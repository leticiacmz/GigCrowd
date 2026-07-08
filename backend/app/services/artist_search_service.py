from app.core.logger import get_logger
from app.schemas.artist_search import ArtistSearchItem
from app.services.provider_manager import ProviderManager

logger = get_logger("artist_search")


class ArtistSearchService:
    """
    Responsible only for searching artists.

    It does not import or save artists.
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
    ):
        self.provider_manager = provider_manager

    async def search_artist(
        self,
        query: str,
    ) -> list[ArtistSearchItem]:

        logger.info(f"Searching artist '{query}'")

        spotify_results = await self.provider_manager.search_artist(
            provider_name="spotify",
            query=query,
        )

        artists: list[ArtistSearchItem] = []

        for artist in spotify_results:

            artists.append(
                ArtistSearchItem(
                    provider="spotify",
                    provider_artist_id=artist["id"],
                    name=artist["name"],
                    followers=artist.get("followers"),
                    image=artist.get("image"),
                    popularity=artist.get("popularity"),
                    verified=artist.get("verified", False),
                    genres=artist.get("genres", []),
                )
            )

        return artists