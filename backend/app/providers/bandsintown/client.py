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
        date: str = "upcoming",
    ):

        print("==============================")
        print("BANDSINTOWN REQUEST")
        print(
            f"Artist: {artist_name}"
        )
        print(
            f"Date: {date}"
        )
        print("==============================")


        response = await self.client.get(
            f"/artists/{artist_name}/events",
            params={
                "app_id": settings.BANDSINTOWN_APP_ID,
                "date": date,
            },
        )


        print(
            "STATUS:",
            response.status_code
        )


        print(
            "RESPONSE SIZE:",
            len(response.text)
        )


        print(
            response.text[:500]
        )


        response.raise_for_status()

        return response.json()