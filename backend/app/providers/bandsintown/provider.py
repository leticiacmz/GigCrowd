from app.core.logger import get_logger

from app.providers.base import BaseProvider

from app.providers.bandsintown.client import (
    BandsintownClient,
)


logger = get_logger("bandsintown")


class BandsintownProvider(BaseProvider):

    def __init__(self):

        self.client = BandsintownClient()

    async def search_artist(
        self,
        query: str,
    ):

        return []

    async def get_artist(
        self,
        artist_id: str,
    ):

        return {}

    async def get_artist_events(
        self,
        artist_name: str,
    ):

        logger.info(
            f"Fetching events for '{artist_name}'"
        )

        return await self.client.get_artist_events(
            artist_name=artist_name,
            date="all",
        )