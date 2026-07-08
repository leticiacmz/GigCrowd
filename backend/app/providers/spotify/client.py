import httpx

from app.config import settings


class SpotifyClient:

    BASE_URL = "https://api.spotify.com/v1"

    def __init__(self):

        self.client = httpx.AsyncClient(
            timeout=30
        )

    async def search_artist(
        self,
        query: str,
        token: str,
    ):

        response = await self.client.get(
            f"{self.BASE_URL}/search",
            params={
                "q": query,
                "type": "artist",
                "limit": 10,
            },
            headers={
                "Authorization": f"Bearer {token}"
            }
        )

        response.raise_for_status()

        return response.json()