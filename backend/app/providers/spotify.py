from app.providers.base import BaseProvider
from app.core.logger import get_logger

logger = get_logger("spotify")


class SpotifyProvider(BaseProvider):

    async def search_artist(self, query: str):
        logger.info(f"Spotify search: {query}")

        return [
            {
                "id": "sp_1",
                "name": f"{query} (Spotify)",
                "followers": 1000,
                "source": "spotify"
            }
        ]

    async def get_artist(self, artist_id: str):
        return {
            "id": artist_id,
            "name": "Spotify Artist",
            "followers": 1000,
            "source": "spotify"
        }