from typing import Any

from app.providers.registry import registry
from app.providers.base import BaseProvider


class ProviderManager:

    def get_provider(self, provider_name: str) -> BaseProvider:
        return registry.get_provider(provider_name)

    async def search_artist(
        self,
        provider_name: str,
        query: str
    ) -> list[dict[str, Any]]:

        provider = self.get_provider(provider_name)

        return await provider.search_artist(query)

    async def get_artist(
        self,
        provider_name: str,
        artist_id: str
    ) -> dict[str, Any]:

        provider = self.get_provider(provider_name)

        return await provider.get_artist(artist_id)