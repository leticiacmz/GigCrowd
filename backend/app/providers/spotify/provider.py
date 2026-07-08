from app.core.logger import get_logger

from app.providers.base import BaseProvider
from app.providers.spotify.client import SpotifyClient

from app.schemas.artist_search import ArtistSearchItem


logger = get_logger("spotify")


class SpotifyProvider(BaseProvider):

    def __init__(self):

        self.client = SpotifyClient()

    async def search_artist(
        self,
        query: str,
    ) -> list[ArtistSearchItem]:

        logger.info(
            "Spotify search requested."
        )

        return [
            ArtistSearchItem(
                provider="spotify",
                provider_artist_id="sp_1",
                name=query,
                followers=1000,
            )
        ]

    async def get_artist(
        self,
        artist_id: str,
    ):

        return {
            "provider": "spotify",
            "provider_artist_id": artist_id,
        }