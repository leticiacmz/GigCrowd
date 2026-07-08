from __future__ import annotations

import asyncio
from typing import Any

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
        provider_name: str,
        query: str,
    ) -> list[dict[str, Any]]:

        provider = self.get_provider(provider_name)

        return await provider.search_artist(query)

    async def get_artist(
        self,
        provider_name: str,
        artist_id: str,
    ) -> dict[str, Any]:

        provider = self.get_provider(provider_name)

        return await provider.get_artist(artist_id)

    async def search_all(
        self,
        query: str,
    ) -> dict[str, Any]:

        spotify = self.get_provider("spotify")

        bandsintown = self.get_provider("bandsintown")

        spotify_task = spotify.search_artist(query)

        bandsintown_task = bandsintown.search_artist(query)

        spotify_result, bandsintown_result = await asyncio.gather(
            spotify_task,
            bandsintown_task,
        )

        return {
            "spotify": spotify_result,
            "bandsintown": bandsintown_result,
        }