from app.providers.base import BaseProvider
from app.providers.registry import registry


class ProviderManager:

    def get_provider(
        self,
        provider_name: str,
    ) -> BaseProvider:

        return registry.get_provider(
            provider_name
        )

    async def search_artist(
        self,
        query: str,
        provider: str = "songkick",
    ):
        """
        Search artists using the specified provider.
        Defaults to Songkick as the canonical source.
        """
        selected_provider = self.get_provider(
            provider
        )

        return await selected_provider.search_artist(
            query
        )

    async def get_artist(
        self,
        provider: str,
        artist_id: str,
    ):

        selected_provider = self.get_provider(
            provider
        )

        return await selected_provider.get_artist(
            artist_id
        )

    async def get_artist_events(
        self,
        artist_name: str,
        provider: str = "bandsintown",
    ):
        """
        Get artist events using the specified provider.
        Defaults to Bandsintown for backward compatibility.
        """
        selected_provider = self.get_provider(
            provider
        )

        return await selected_provider.get_artist_events(
            artist_name
        )