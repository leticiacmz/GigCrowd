from app.providers.registry import registry
from app.repositories.artist_repository import ArtistRepository
from app.core.logger import get_logger

logger = get_logger("discovery")


class DiscoveryService:

    def __init__(self, artist_repository: ArtistRepository):
        self.artist_repository = artist_repository

    async def search_artist(self, provider: str, query: str):
        provider = registry.get_provider(provider)
        return await provider.search_artist(query)

    async def get_or_create_artist(self, artist: dict):

        existing = await self.artist_repository.get_by_name(
            artist.get("name")
        )

        if existing:
            return existing

        await self.artist_repository.insert_one(artist)

        return artist