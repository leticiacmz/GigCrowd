"""A refused Spotify search goes quiet instead of costing every search.

Spotify contributes extras to artist discovery: results Songkick did not
return. That contribution is optional by design - a refusal must not affect
discovery, which is the whole point of making it optional. What a refusal
must also not do is cost one HTTP call on every later search: it is an
answer about this app's access, not about the query, so the provider quiets
itself for a bounded window. The first search after the window asks again,
because credentials come back without this process restarting.

Only a refusal (an HTTP status the API itself chose) quiets. A transport
error says nothing about this app's access, so it leaves the next search
free to try again immediately.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.providers.spotify.provider import SpotifyProvider


def a_refusal(status_code: int = 403) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "POST",
        "https://accounts.spotify.com/api/token",
    )

    response = httpx.Response(status_code, request=request)

    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


def an_answer(name: str = "Marina Sena") -> dict:
    return {
        "artists": {
            "items": [
                {
                    "id": "spotify-artist-1",
                    "name": name,
                    "images": [],
                    "genres": [],
                }
            ]
        }
    }


class AClient:
    """The HTTP half of the provider: answers or refuses, and counts."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls: list[str] = []

    async def search_artist(self, query: str):
        self.calls.append(query)

        answer = self.answers.pop(0)

        if isinstance(answer, Exception):
            raise answer

        return answer


def a_provider(answers) -> SpotifyProvider:
    provider = SpotifyProvider()
    provider.client = AClient(answers)

    return provider


class TestARefusedSearchQuietsTheProvider:
    @pytest.mark.asyncio
    async def test_a_refusal_quiets_the_next_searches(self):
        provider = a_provider([a_refusal(), an_answer()])

        with pytest.raises(httpx.HTTPStatusError):
            await provider.search_artist("Marina Sena")

        # The window is ahead, and its length is the configured one.
        assert provider._search_quiet_until is not None

        ahead = (
            provider._search_quiet_until
            - datetime.now(timezone.utc)
        ).total_seconds()

        assert 0 < ahead <= (
            settings.SPOTIFY_SEARCH_COOLDOWN_MINUTES * 60
        )

        # The next search is answered from the quiet state: no HTTP call,
        # no result - not even the answer the stub would have given.
        results = await provider.search_artist("Marina Sena")

        assert results == []
        assert provider.client.calls == ["Marina Sena"]

    @pytest.mark.asyncio
    async def test_the_first_search_after_the_window_asks_again(self):
        provider = a_provider([an_answer()])

        # A window that has already passed: the provider asks again, and a
        # success means it keeps asking.
        provider._search_quiet_until = datetime.now(
            timezone.utc
        ) - timedelta(seconds=1)

        results = await provider.search_artist("Marina Sena")

        assert [item.name for item in results] == ["Marina Sena"]
        assert provider.client.calls == ["Marina Sena"]
        assert provider._search_quiet_until is None

    @pytest.mark.asyncio
    async def test_a_success_after_the_window_clears_the_quiet(self):
        provider = a_provider([a_refusal(), an_answer()])

        with pytest.raises(httpx.HTTPStatusError):
            await provider.search_artist("Marina Sena")

        # Time passes (simulated): the window is behind the provider.
        provider._search_quiet_until = datetime.now(
            timezone.utc
        ) - timedelta(seconds=1)

        results = await provider.search_artist("Marina Sena")

        assert [item.name for item in results] == ["Marina Sena"]
        assert provider._search_quiet_until is None

    @pytest.mark.asyncio
    async def test_a_transport_error_does_not_quiet_the_provider(self):
        provider = a_provider(
            [
                httpx.ConnectTimeout("timed out"),
                an_answer(),
            ]
        )

        with pytest.raises(httpx.ConnectTimeout):
            await provider.search_artist("Marina Sena")

        results = await provider.search_artist("Marina Sena")

        assert [item.name for item in results] == ["Marina Sena"]
        assert provider.client.calls == ["Marina Sena", "Marina Sena"]
