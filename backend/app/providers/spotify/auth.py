from datetime import datetime, timedelta, UTC
import base64

import httpx

from app.config import settings
from app.core.logger import get_logger

logger = get_logger("spotify_auth")


class SpotifyAuth:

    TOKEN_URL = f"{settings.SPOTIFY_AUTH_URL}/token"

    def __init__(self):
        self.access_token: str | None = None
        self.expires_at: datetime | None = None

    async def get_access_token(self) -> str:

        if (
            self.access_token
            and self.expires_at
            and datetime.now(UTC) < self.expires_at
        ):
            logger.info("Using cached Spotify access token.")
            return self.access_token

        logger.info("Spotify access token expired or not found.")

        token = await self._request_token()

        self.access_token = token["access_token"]

        self.expires_at = (
            datetime.now(UTC)
            + timedelta(seconds=token["expires_in"] - 60)
        )

        return self.access_token

    async def _request_token(self):

        logger.info("Requesting new Spotify access token.")

        credentials = (
            f"{settings.SPOTIFY_CLIENT_ID}:"
            f"{settings.SPOTIFY_CLIENT_SECRET}"
        )

        credentials = base64.b64encode(
            credentials.encode()
        ).decode()

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}"
                },
                data={
                    "grant_type": "client_credentials"
                },
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            logger.exception("Failed to obtain Spotify access token.")
            raise

        return response.json()


spotify_auth = SpotifyAuth()