import httpx

from app.config import settings
from app.providers.spotify.auth import spotify_auth


class SpotifyClient:

    def __init__(self):

        self.client = httpx.AsyncClient(
            base_url=settings.SPOTIFY_API_URL,
            timeout=30,
        )

    async def search_artist(
        self,
        query: str,
    ) -> dict:

        token = await spotify_auth.get_access_token()

        response = await self.client.get(
            "/search",
            params={
                "q": query,
                "type": "artist",
                "limit": 10,
            },
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        print("SEARCH STATUS:", response.status_code)
        print("SEARCH BODY:", response.text)
        
        response.raise_for_status()

        return response.json()

    async def get_artist(
        self,
        artist_id: str,
    ) -> dict:

        token = await spotify_auth.get_access_token()

        response = await self.client.get(
            f"/artists/{artist_id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        response.raise_for_status()

        return response.json()