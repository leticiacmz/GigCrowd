from app.providers.registry import registry


class DiscoveryService:

    async def search_artist(self, provider_name: str, query: str):
        provider = registry.get_provider(provider_name)
        return await provider.search_artist(query)