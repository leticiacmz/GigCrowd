"""How the Songkick client addresses one artist.

The resolution rules live in `songkick_identity` and are tested there. What
matters here is that the client *obeys* them against a stubbed site: that a
trusted ID is what decides, that a dead ID falls back to an exact name match
rather than to the first result, and that a page belonging to a different artist
is refused instead of imported.

The site is stubbed, so these tests assert behaviour rather than Songkick's
current markup, and they cannot pass by coincidence.
"""
from __future__ import annotations

import pytest

from app.providers.songkick.client import (
    SongkickClient,
    SongkickNotFound,
)


class StubClient(SongkickClient):
    """A Songkick client whose site is a dict of canned responses.

    Each key is a URL and each value is the body served there. A URL that is not in
    the map is a 404, which is what Songkick does for an identifier it does not
    know.
    """

    def __init__(self, pages: dict, artists: list | None = None):
        super().__init__()

        self.pages = pages
        self.requested: list[str] = []

        self._stub_artists = artists or []

    async def _request(self, url: str, **kwargs):
        self.requested.append(url)

        body = self.pages.get(url)

        if body is None:

            return type(
                "Response",
                (),
                {
                    "status_code": 404,
                    "text": "",
                    "url": url,
                },
            )()

        return type(
            "Response",
            (),
            {
                "status_code": 200,
                "text": body,
                "url": url,
            },
        )()

    async def search_artist_full(self, query: str) -> dict:
        return {
            "artists": self._stub_artists,
            "top_results": [],
        }


# The pages `scrape_artist` reads. The artist page is what the identity guard
# inspects, and the calendar and gigography pages are read but their contents do
# not matter for identity.
def page(url: str, name: str = "") -> str:
    return (
        f'<html><head><meta property="og:title" content="{name}">'
        f"</head><body></body></html>"
    )


def pages_for(artist_id: str, slug: str, name: str) -> dict:
    url = (
        f"https://www.songkick.com/artists/"
        f"{artist_id}-{slug}"
    )

    body = page(url, name)

    return {
        url: body,
        f"{url}/gigography": body,
        f"{url}/calendar": body,
    }


def entry(artist_id, name):
    return {"document": {"id": artist_id, "name": name}}


class TestTheTrustedIdDecidesWhichArtist:
    @pytest.mark.asyncio
    async def test_the_page_for_the_trusted_id_is_read(self):
        client = StubClient(
            pages_for("520117", "arctic-monkeys", "Arctic Monkeys")
        )

        data = await client.scrape_artist(
            "Arctic Monkeys", artist_id="Artist520117"
        )

        assert data["artist"]["id"] == "520117"
        assert any(
            "520117" in url for url in client.requested
        )

    @pytest.mark.asyncio
    async def test_a_same_named_competitor_is_not_read(self):
        # Search offers both, the ID says which one this is.
        client = StubClient(
            pages_for("520117", "arctic-monkeys", "Arctic Monkeys"),
            artists=[
                entry("111", "Arctic Monkeys"),
                entry("520117", "Arctic Monkeys"),
            ],
        )

        await client.scrape_artist(
            "Arctic Monkeys", artist_id="Artist520117"
        )

        assert not any(
            "111" in url for url in client.requested
        )


class TestADeadStoredIdIsReportedNotGuessed:
    @pytest.mark.asyncio
    async def test_it_falls_back_to_an_exact_name_match(self):
        client = StubClient(
            pages_for("10176016", "marina-sena", "Marina Sena"),
            artists=[
                entry("10176016", "Marina Sena"),
                entry("10235798", "Marina Sen"),
            ],
        )

        data = await client.scrape_artist(
            "Marina Sena", artist_id="Artist3090429"
        )

        assert data["artist"]["id"] == "10176016"
        assert data["artist"]["name"] == "Marina Sena"

    @pytest.mark.asyncio
    async def test_the_fallback_never_picks_a_near_match(self):
        # Only the exact name is acceptable. "Marina Sen" is a different act.
        client = StubClient(
            pages_for("10176016", "marina-sena", "Marina Sena"),
            artists=[
                entry("10235798", "Marina Sen"),
            ],
        )

        with pytest.raises(ValueError) as caught:

            await client.scrape_artist(
                "Marina Sena", artist_id="Artist3090429"
            )

        assert "no exact name match" in str(caught.value)

    @pytest.mark.asyncio
    async def test_a_dead_id_with_no_search_results_raises(self):
        client = StubClient(pages={}, artists=[])

        # No page for the ID and no exact name match: nothing to resolve, so it
        # must say so rather than pick something.
        with pytest.raises(ValueError) as caught:

            await client.scrape_artist(
                "Marina Sena", artist_id="Artist3090429"
            )

        assert "no exact name match" in str(caught.value)

    @pytest.mark.asyncio
    async def test_no_id_and_no_exact_match_raises(self):
        # The old code took the first search result here, which is how a wrong
        # gigography got imported without anything looking wrong.
        client = StubClient(
            pages={},
            artists=[entry("10235798", "Marina Sen")],
        )

        with pytest.raises(ValueError) as caught:

            await client.scrape_artist("Marina Sena")

        assert "trusted ID" in str(caught.value)


class TestAPageForTheWrongArtistIsRefused:
    @pytest.mark.asyncio
    async def test_a_redirect_to_another_artist_raises(self):
        # Songkick serves whichever artist the URL resolves to. If that is not the
        # artist that was asked for, importing its events would be silent and
        # wrong, so it is an error.
        pages = pages_for("520117", "arctic-monkeys", "Arctic Monkeys")

        # A URL built from the trusted ID is redirected by the site to a
        # different artist's page.
        requested = (
            "https://www.songkick.com/artists/520117-arctic-monkeys"
        )

        redirected = (
            "https://www.songkick.com/artists/999999-someone-else"
        )

        client = StubClient(pages)

        async def serve(url, **kwargs):

            client.requested.append(url)

            body = pages.get(url)

            if body is None:

                return type(
                    "Response",
                    (),
                    {"status_code": 404, "text": "", "url": url},
                )()

            # Answer with the other artist's page, served from our URL.
            response = type(
                "Response",
                (),
                {"status_code": 200, "text": body, "url": redirected},
            )()

            return response

        client._request = serve

        with pytest.raises(ValueError) as caught:

            await client.scrape_artist(
                "Arctic Monkeys", artist_id="Artist520117"
            )

        assert "different artist" in str(caught.value)
        assert requested


class TestSpotifyIdsAreNeverUsedToAddressSongkick:
    @pytest.mark.asyncio
    async def test_a_spotify_id_is_refused_rather_than_sent(self):
        # If the Spotify ID were used, the URL would contain it. It must not.
        client = StubClient(
            pages_for("520117", "arctic-monkeys", "Arctic Monkeys"),
            artists=[entry("520117", "Arctic Monkeys")],
        )

        await client.scrape_artist(
            "Arctic Monkeys",
            artist_id="4aXyz885Ai9JG3F9dJ1PHB",
        )

        assert not any(
            "4aXyz885Ai9JG3F9dJ1PHB" in url
            for url in client.requested
        )

    @pytest.mark.asyncio
    async def test_the_spotify_id_does_not_reach_the_artist_url(self):
        client = StubClient(
            pages_for("520117", "arctic-monkeys", "Arctic Monkeys"),
            artists=[entry("520117", "Arctic Monkeys")],
        )

        data = await client.scrape_artist(
            "Arctic Monkeys",
            artist_id="4aXyz885Ai9JG3F9dJ1PHB",
        )

        assert "4aXyz" not in data["artist"]["url"]
        assert data["artist"]["id"] == "520117"


class TestTheCanonicalSlugIsAdopted:
    @pytest.mark.asyncio
    async def test_songkicks_own_spelling_is_used_afterwards(self):
        # A decorative slug is redirected to the canonical one. Adopting the site's
        # spelling keeps later requests on a URL that is already correct.
        pages = pages_for("520117", "arctic-monkeys", "Arctic Monkeys")

        client = StubClient(pages)

        data = await client.scrape_artist(
            "Arctic Monkeys", artist_id="Artist520117"
        )

        assert data["artist"]["slug"] == "arctic-monkeys"
        assert data["artist"]["url"].endswith(
            "/artists/520117-arctic-monkeys"
        )


class TestTheResolvedArtistIsReported:
    @pytest.mark.asyncio
    async def test_the_artist_returned_is_the_one_that_was_read(self):
        # After a fallback, this must describe the artist actually fetched. An
        # import that trusted a stale ID here would believe it had reached the
        # artist it was asked for when it had not.
        client = StubClient(
            pages_for("10176016", "marina-sena", "Marina Sena"),
            artists=[entry("10176016", "Marina Sena")],
        )

        data = await client.scrape_artist(
            "Marina Sena", artist_id="Artist3090429"
        )

        assert data["artist"]["id"] == "10176016"
        assert data["artist"]["name"] == "Marina Sena"
        assert "3090429" not in str(data["artist"])