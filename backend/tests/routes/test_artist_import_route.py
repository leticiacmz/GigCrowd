"""Route-level tests for artist import dispatch and error handling."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.domain.artist import Artist


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


def test_spotify_discovery_import_resolves_songkick_canonical():
    """A Spotify discovery result is resolved to a Songkick canonical artist."""
    service = MagicMock()
    service.import_from_spotify = AsyncMock(
        return_value={"artist": _artist(), "is_new": True}
    )
    service.import_artist = AsyncMock()

    with patch("app.routes.artists.artist_import_service", service):
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
    service = MagicMock()
    service.import_artist = AsyncMock(
        return_value={"artist": _artist(), "is_new": True}
    )
    service.import_from_spotify = AsyncMock()

    with patch("app.routes.artists.artist_import_service", service):
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


def test_unresolvable_artist_returns_controlled_400():
    """An unresolvable identity is a controlled client error, not a 500."""
    service = MagicMock()
    service.import_from_spotify = AsyncMock(
        side_effect=ValueError(
            "Could not find an exact Songkick match for 'Demi Lovato'."
        )
    )

    with patch("app.routes.artists.artist_import_service", service):
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

    with patch("app.routes.artists.artist_import_service", service):
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