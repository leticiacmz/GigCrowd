from app.providers.base import BaseProvider
from app.providers.registry import registry


class ProviderManager:

    def get_provider(
        self,
        provider_name: str,
    ) -> BaseProvider:

        return registry.get_provider(provider_name)

    async def search_artist(
        self,
        query: str,
    ):

        spotify = self.get_provider("spotify")

        return await spotify.search_artist(query)

    async def get_artist(
        self,
        provider: str,
        artist_id: str,
    ):

        selected_provider = self.get_provider(provider)

        return await selected_provider.get_artist(
            artist_id
        )