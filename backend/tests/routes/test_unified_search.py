"""The one-box search, at the HTTP boundary.

Both services are stubs, so what these tests pin is what the endpoint *does*
with a query - which service is asked, with what, and what happens when one
of them fails - rather than whether Songkick or MongoDB happens to be
reachable.

The stubs offer no import and no synchronization method at all. If the route
ever grew one, these tests would fail loudly rather than quietly importing an
artist on the reader's behalf, which is exactly the behaviour worth pinning:
search and import are separate actions.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.search import (
    get_artist_search_service,
    get_event_search_service,
    router as search_router,
)
from app.schemas.artist_response import ArtistResponse
from app.schemas.event_search import EventSearchRow


MARINA = ArtistResponse(
    provider="songkick",
    provider_artist_id="Artist10176016",
    name="Marina Sena",
    verified=False,
    is_imported=True,
    id="6ac5cf19a2f4443423eb358e",
    slug="marina-sena",
)

SHOW = EventSearchRow(
    id="6ac5cf19a2f4443423eb358e",
    title="London, UK Electric Brixton",
    starts_at=datetime(2026, 10, 30, 18, 30, tzinfo=timezone.utc),
    venue={"slug": "electric-brixton", "name": "Electric Brixton", "city": "London"},
)


class StubEventSearch:
    """Stands in for `EventSearchService` and records how it was called."""

    def __init__(self, rows: list[EventSearchRow] | None = None, total: int = 0):
        self.rows = rows or []
        self.total = total
        self.calls: list[dict] = []

    async def search(
        self,
        *,
        q=None,
        genre=None,
        limit=20,
        before=None,
        before_id=None,
        include_past=False,
    ):
        self.calls.append(
            {
                "q": q,
                "genre": genre,
                "before": before,
                "before_id": before_id,
                "include_past": include_past,
            }
        )

        return {
            "events": self.rows,
            "total": self.total,
            "next_cursor": None,
            "genre": genre,
        }


class StubArtistSearch:
    """Stands in for `ArtistSearchService`: discovery, and nothing else."""

    def __init__(self, artists: list[ArtistResponse] | None = None, error=None):
        self.artists = artists or []
        self.error = error
        self.queries: list[str] = []

    async def search_artist(self, query: str):
        self.queries.append(query)

        if self.error is not None:
            raise self.error

        return self.artists


@pytest.fixture
def event_search():
    return StubEventSearch(rows=[SHOW], total=37)


@pytest.fixture
def artist_search():
    return StubArtistSearch(artists=[MARINA])


@pytest.fixture
def app(event_search, artist_search):
    """A bare app exposing only the unified search, with both halves stubbed."""

    application = FastAPI()
    application.include_router(search_router)

    application.dependency_overrides[get_event_search_service] = (
        lambda: event_search
    )
    application.dependency_overrides[get_artist_search_service] = (
        lambda: artist_search
    )

    return application


class TestOneQuery:
    def test_one_query_answers_with_both_halves(
        self, app, event_search, artist_search
    ):
        """The reader names no source, so the response carries both sources.

        Each result type is read from where it arrived: acts in `artists`,
        shows in `events`, and the act keeps its slug so a known act opens
        instead of being imported a second time.
        """
        with TestClient(app) as client:
            response = client.get("/search", params={"q": "Marina Sena"})

        payload = response.json()

        assert response.status_code == 200
        assert payload["query"] == "Marina Sena"

        assert [artist["name"] for artist in payload["artists"]] == [
            "Marina Sena"
        ]
        assert payload["artists"][0]["slug"] == "marina-sena"
        assert payload["artists"][0]["is_imported"] is True

        assert [event["id"] for event in payload["events"]] == [SHOW.id]
        assert payload["total"] == 37
        assert payload["next_cursor"] is None

        assert event_search.calls[0]["q"] == "Marina Sena"
        assert artist_search.queries == ["Marina Sena"]

    def test_a_query_is_required(self, app):
        """An empty box is the browse list's question, not this endpoint's."""
        with TestClient(app) as client:
            assert client.get("/search").status_code == 422

    def test_genre_travels_with_the_text(self, app, event_search):
        with TestClient(app) as client:
            payload = client.get(
                "/search", params={"q": "Nova", "genre": "mpb"}
            ).json()

        assert event_search.calls[0]["genre"] == "mpb"
        assert payload["genre"] == "mpb"


class TestWhatTheLookupCanSee:
    def test_the_lookup_reaches_shows_that_have_already_happened(
        self, app, event_search
    ):
        """A search is a lookup, so it reads the whole catalogue.

        The browse list on `/events` stays upcoming-only because it answers
        "what is on". This endpoint answers "have we got that", and a venue or
        a festival whose shows are all behind us would otherwise be reported
        as nothing at all - the box lying about what it holds.
        """
        with TestClient(app) as client:
            client.get("/search", params={"q": "Espaço Unimed"})

        assert event_search.calls[0]["include_past"] is True

    def test_the_artist_half_is_asked_once_per_query(
        self, app, artist_search
    ):
        """Paging is not a new question about who is playing."""
        with TestClient(app) as client:
            first = client.get("/search", params={"q": "Mada"})
            second = client.get(
                "/search",
                params={
                    "q": "Mada",
                    "before": "2026-10-16",
                    "before_id": SHOW.id,
                },
            )

        assert artist_search.queries == ["Mada"]
        assert first.json()["artists"]
        assert second.json()["artists"] == []

    def test_a_catalogue_page_still_carries_its_cursor(
        self, app, event_search
    ):
        """Paging the events half is the same cursor `/events` hands out."""
        with TestClient(app) as client:
            client.get(
                "/search",
                params={"q": "Mada", "before": "2026-10-16", "before_id": "a"},
            )

        assert event_search.calls[0]["before"] == "2026-10-16"
        assert event_search.calls[0]["before_id"] == "a"


class TestWhenOneHalfFails:
    def test_an_artist_provider_outage_does_not_blank_the_catalogue(
        self, app, event_search
    ):
        """Songkick being down is not "no artist by that name".

        The distinction the page needs: an empty list means nothing matched,
        `artists_unavailable` means the question could not be asked. Showing
        the first as if it were the second would tell the reader a lie about
        their own query.
        """
        app.dependency_overrides[get_artist_search_service] = (
            lambda: StubArtistSearch(error=RuntimeError("songkick is down"))
        )

        with TestClient(app) as client:
            payload = client.get(
                "/search", params={"q": "Marina Sena"}
            ).json()

        assert [event["id"] for event in payload["events"]] == [SHOW.id]
        assert payload["artists"] == []
        assert payload["artists_unavailable"] is True

    def test_a_normal_answer_says_the_artist_half_was_reachable(
        self, app
    ):
        with TestClient(app) as client:
            payload = client.get("/search", params={"q": "Marina Sena"}).json()

        assert payload["artists_unavailable"] is False
