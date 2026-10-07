"""Route-level tests for artist import dispatch, synchronization and errors.

Selecting an artist from search is a request to bring that artist here, and
"here" is the artist *and* their shows. These tests hold the route to that: the
artist row is written, the gigography is fetched, and the outcome of both travels
back to the caller so a partial import cannot masquerade as a complete one.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.domain.artist import Artist
from app.schemas.artist_profile_response import ArtistProfileResponse


client = TestClient(app)


def _artist() -> Artist:
    return Artist(
        id="artist_mongo_id",
        name="Demi Lovato",
        normalized_name="demi lovato",
        slug="demi-lovato",
        external_ids={"songkick": "976211"},
        genres=["pop"],
        followers=None,
        image="https://i.scdn.co/image/ab67616d0000b273",
        popularity=70,
        verified=True,
    )


def _sync(
    events_received: int = 531,
    events_created: int = 526,
    events_existing: int = 5,
    synced: bool = True,
):
    """A synchronization service double that reports a completed import."""

    service = MagicMock()

    service.synchronize_artist = AsyncMock(
        return_value={
            "synced": synced,
            "result": {
                "events_received": events_received,
                "events_created": events_created,
                "events_existing": events_existing,
            },
        }
    )

    return service


def _import_service(**overrides):
    service = MagicMock()

    result = {"artist": _artist(), "is_new": True}
    result.update(overrides)

    service.import_artist = AsyncMock(return_value=result)
    service.import_from_spotify = AsyncMock(return_value=result)

    return service


def _read_side(state: str):
    """Doubles for both halves of a page read.

    The read is stubbed rather than allowed to reach a database. A live query
    inside the test client's event loop leaves that loop holding a Mongo handle,
    which then fails every later test file that opens a client of its own - and
    the failure looks like a bug in an unrelated file, which is a miserable thing
    to chase.

    `state` is the artist's `sync_status`, which is the only thing the route
    consults to decide whether opening the page may fetch.
    """

    artist = _artist()

    artist.sync_status = state

    reads = MagicMock()

    reads.get_artist_profile = AsyncMock(
        return_value=ArtistProfileResponse(
            id=artist.id,
            slug=artist.slug,
            name=artist.name,
            external_ids={"songkick": "976211"},
            genres=[],
            followers_count=0,
            popularity=None,
            verified=False,
            events={"upcoming": 3, "total": 531},
        )
    )

    repository = MagicMock()

    # The first call decides the state; the second re-reads what the fetch
    # stored. Both see the same artist, which is what a successful fetch followed
    # by a reload looks like from the route's side.
    repository.get_by_slug = AsyncMock(return_value=artist)

    # Nobody holds the claim, so the route may take it.
    repository.claim_initialization = AsyncMock(return_value=True)

    repository.release_initialization_claim = AsyncMock(return_value=None)

    return reads, repository


def test_spotify_discovery_import_resolves_songkick_canonical():
    """A Spotify discovery result is resolved to a Songkick canonical artist."""
    service = _import_service()

    with patch("app.routes.artists.artist_import_service", service), \
            patch("app.routes.artists.synchronization_service", _sync()):
        response = client.post(
            "/artists/import",
            json={
                "provider": "spotify",
                "provider_artist_id": "spotify_id_123",
                "artist_data": {
                    "name": "Demi Lovato",
                    "image": "https://i.scdn.co/image/ab67616d0000b273",
                },
            },
        )

    assert response.status_code == 200

    service.import_from_spotify.assert_awaited_once_with(
        spotify_artist_id="spotify_id_123"
    )
    # Spotify must never be used as the canonical import path
    service.import_artist.assert_not_awaited()

    body = response.json()

    # Canonical identity is Songkick; Spotify only enriched the record
    assert body["external_ids"]["songkick"] == "976211"
    assert body["image"] == "https://i.scdn.co/image/ab67616d0000b273"


def test_songkick_import_is_delegated_to_service():
    """Songkick requests keep using the service import path."""
    service = _import_service()

    with patch("app.routes.artists.artist_import_service", service), \
            patch("app.routes.artists.synchronization_service", _sync()):
        response = client.post(
            "/artists/import",
            json={
                "provider": "songkick",
                "provider_artist_id": "976211",
                "artist_data": {"name": "Demi Lovato"},
            },
        )

    assert response.status_code == 200
    service.import_artist.assert_awaited_once()
    service.import_from_spotify.assert_not_awaited()


class TestTheImportActuallySynchronizes:
    """The reported bug: an artist appeared, and nothing else did.

    Searching, choosing the right act, and getting an artist row back with an
    empty page is indistinguishable from a working import until you look for the
    shows - so the route now asks for them, and says what happened.
    """

    def test_selecting_an_artist_fetches_its_gigography(self):
        service = _import_service()
        sync = _sync()

        with patch("app.routes.artists.artist_import_service", service), \
                patch("app.routes.artists.synchronization_service", sync):
            response = client.post(
                "/artists/import",
                json={
                    "provider": "songkick",
                    "provider_artist_id": "976211",
                    "artist_data": {"name": "Demi Lovato"},
                },
            )

        assert response.status_code == 200

        sync.synchronize_artist.assert_awaited_once()

        called = sync.synchronize_artist.await_args

        assert called.args[0].slug == "demi-lovato"

        # Forced, because this is the explicit selection the reader just made.
        # The TTL guard would otherwise skip an artist whose shows were already
        # known and silently do nothing.
        assert called.kwargs.get("force") is True

    def test_the_outcome_is_reported(self):
        service = _import_service()

        with patch("app.routes.artists.artist_import_service", service), \
                patch("app.routes.artists.synchronization_service", _sync()):
            response = client.post(
                "/artists/import",
                json={
                    "provider": "songkick",
                    "provider_artist_id": "976211",
                    "artist_data": {"name": "Demi Lovato"},
                },
            )

        body = response.json()

        assert body["sync"]["attempted"] is True
        assert body["sync"]["succeeded"] is True
        assert body["sync"]["events_received"] == 531
        assert body["sync"]["events_created"] == 526

    def test_zero_upcoming_events_is_a_success_not_a_failure(self):
        """An artist with nothing announced is a real answer.

        Treating "the provider had nothing for this artist" as a failed import
        would make a correct result look broken, and would invite a retry loop
        against a provider that has already said no.
        """

        service = _import_service()

        with patch("app.routes.artists.artist_import_service", service), \
                patch(
                    "app.routes.artists.synchronization_service",
                    _sync(
                        events_received=0,
                        events_created=0,
                        events_existing=0,
                    ),
                ):
            response = client.post(
                "/artists/import",
                json={
                    "provider": "songkick",
                    "provider_artist_id": "976211",
                    "artist_data": {"name": "Demi Lovato"},
                },
            )

        body = response.json()

        assert body["sync"]["succeeded"] is True
        assert body["sync"]["events_received"] == 0

    def test_the_artist_survives_a_provider_failure(self):
        """A partial success must not be reported as a failure.

        The artist is real and persisted by this point. Turning a provider error
        into a 4xx/5xx would leave the caller unable to tell "not imported" from
        "imported, but the shows did not come" - and the artist would look like
        it had never been selected.
        """

        service = _import_service()

        sync = MagicMock()
        sync.synchronize_artist = AsyncMock(
            side_effect=RuntimeError("Songkick API error: 503")
        )

        with patch("app.routes.artists.artist_import_service", service), \
                patch("app.routes.artists.synchronization_service", sync):
            response = client.post(
                "/artists/import",
                json={
                    "provider": "songkick",
                    "provider_artist_id": "976211",
                    "artist_data": {"name": "Demi Lovato"},
                },
            )

        assert response.status_code == 200

        body = response.json()

        # The artist came back with its identity intact, which is the whole
        # point: a provider failure must not erase a successful import.
        assert body["slug"] == "demi-lovato"
        assert body["external_ids"]["songkick"] == "976211"

        assert body["sync"]["attempted"] is True
        assert body["sync"]["succeeded"] is False
        assert "503" in body["sync"]["reason"]

    def test_a_read_of_an_initialized_artist_page_never_synchronizes(self):
        """The separation that matters.

        An artist whose gigography has been fetched is read-only, forever. If a
        page load could reach the synchronization, then browsing would start
        scraping and the catalogue would grow under a reader who only looked at
        it.
        """

        sync = _sync()

        reads, repository = _read_side(state="success")

        with patch("app.routes.artists.artist_service", reads), \
                patch("app.routes.artists.artist_repository", repository), \
                patch("app.routes.artists.synchronization_service", sync):
            response = client.get("/artists/demi-lovato")

        assert response.status_code == 200

        reads.get_artist_profile.assert_awaited_once_with("demi-lovato")

        sync.synchronize_artist.assert_not_awaited()


def test_unresolvable_artist_returns_controlled_400():
    """An unresolvable identity is a controlled client error, not a 500."""
    service = MagicMock()
    service.import_from_spotify = AsyncMock(
        side_effect=ValueError(
            "Could not find an exact Songkick match for 'Demi Lovato'."
        )
    )

    with patch("app.routes.artists.artist_import_service", service), \
            patch("app.routes.artists.synchronization_service", _sync()):
        response = client.post(
            "/artists/import",
            json={
                "provider": "spotify",
                "provider_artist_id": "spotify_id_123",
            },
        )

    assert response.status_code == 400
    assert "exact Songkick match" in response.json()["detail"]


def test_missing_canonical_id_returns_controlled_400():
    """The reported 'Songkick artist requires an ID' case is now a 400."""
    service = MagicMock()
    service.import_artist = AsyncMock(
        side_effect=ValueError("Songkick import requires provider_artist_id.")
    )

    with patch("app.routes.artists.artist_import_service", service), \
            patch("app.routes.artists.synchronization_service", _sync()):
        response = client.post(
            "/artists/import",
            json={
                "provider": "songkick",
                "provider_artist_id": "",
                "artist_data": {"name": "Demi Lovato"},
            },
        )

    assert response.status_code == 400
    assert "provider_artist_id" in response.json()["detail"]