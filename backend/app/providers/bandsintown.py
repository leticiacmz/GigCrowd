from app.providers.base import BaseProvider
from typing import List, Dict, Any
from app.core.logger import get_logger

logger = get_logger("bandsintown_provider")


class BandsintownProvider(BaseProvider):

    async def search_artist(self, query: str) -> List[Dict[str, Any]]:
        logger.info(f"Bandsintown search: {query}")

        # manter comportamento atual (sem quebrar)
        return []

    async def get_artist(self, artist_id: str) -> Dict[str, Any]:
        logger.info(f"Bandsintown get artist: {artist_id}")

        return {}