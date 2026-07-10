from app.core.logger import get_logger

from app.providers.base import BaseProvider
from app.providers.spotify.client import SpotifyClient
from app.providers.spotify.artist_mapper import SpotifyArtistMapper

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
            f"Searching Spotify artists: {query}"
        )

        response = await self.client.search_artist(query)

        return SpotifyArtistMapper.map_search_results(response)

    async def get_artist(
        self,
        artist_id: str,
    ):

        logger.info(
            f"Fetching Spotify artist: {artist_id}"
        )

        raise NotImplementedError(
            "get_artist() will be implemented in the next commit."
        )