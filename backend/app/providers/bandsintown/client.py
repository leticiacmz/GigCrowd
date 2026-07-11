import httpx

from app.config import settings


class BandsintownClient:

    def __init__(self):

        self.client = httpx.AsyncClient(
            base_url=settings.BANDSINTOWN_BASE_URL,
            timeout=30,
        )

    async def get_artist_events(
        self,
        artist_name: str,
    ) -> list[dict]:

        response = await self.client.get(
            f"/artists/{artist_name}/events",
            params={
                "app_id": settings.BANDSINTOWN_APP_ID,
            },
        )

        response.raise_for_status()

        return response.json()