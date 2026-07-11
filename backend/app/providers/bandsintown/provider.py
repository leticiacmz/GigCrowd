from app.providers.base import BaseProvider
from app.core.logger import get_logger

logger = get_logger("bandsintown")


class BandsintownProvider(BaseProvider):

    async def search_artist(self, query: str):
        logger.info(f"Bandsintown search: {query}")
        return []

    async def get_artist(self, artist_id: str):
        return {}