from app.providers.base import BaseProvider
from typing import List, Dict, Any
from app.core.logger import get_logger

logger = get_logger("spotify_provider")


class SpotifyProvider(BaseProvider):

    async def search_artist(self, query: str) -> List[Dict[str, Any]]:
        logger.info(f"Searching Spotify artists: {query}")

        # STUB (fase 1 não integra API ainda)
        return [
            {
                "id": "spotify_1",
                "name": f"{query} Artist 1",
                "followers": 1000,
                "source": "spotify"
            }
        ]

    async def get_artist(self, artist_id: str) -> Dict[str, Any]:
        logger.info(f"Getting Spotify artist: {artist_id}")

        return {
            "id": artist_id,
            "name": "Mock Artist",
            "followers": 1000,
            "source": "spotify"
        }