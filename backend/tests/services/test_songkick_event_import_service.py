import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.songkick_event_import_service import SongkickEventImportService
from app.domain.artist import Artist


@pytest.mark.asyncio
async def test_resolve_artist_ids_single():
    """Test resolving a single Songkick artist ID"""
    mock_artist_repo = AsyncMock()
    mock_artist_repo.get_by_songkick_id = AsyncMock(return_value=Artist(
        name="Demi Lovato",
        normalized_name="demi lovato",
        slug="demi-lovato",
        external_ids={"songkick": "Artist976211"}
    ))
    
    service = SongkickEventImportService(
        provider_manager=MagicMock(),
        event_repository=MagicMock(),
        venue_repository=MagicMock(),
        artist_repository=mock_artist_repo
    )
    
    result = await service._resolve_artist_ids([976211], "demi-lovato")
    
    # Should include resolved artist (not duplicated since it's the initiating artist)
    assert result == ["demi-lovato"]
    mock_artist_repo.get_by_songkick_id.assert_called_once_with(976211)


@pytest.mark.asyncio
async def test_resolve_artist_ids_multiple():
    """Test resolving multiple Songkick artist IDs"""
    mock_artist_repo = AsyncMock()
    mock_artist_repo.get_by_songkick_id = AsyncMock(side_effect=[
        Artist(name="Demi Lovato", normalized_name="demi lovato", slug="demi-lovato", external_ids={"songkick": "Artist976211"}),
        Artist(name="Foo Fighters", normalized_name="foo fighters", slug="foo-fighters", external_ids={"songkick": "Artist22766"}),
        Artist(name="Maroon 5", normalized_name="maroon 5", slug="maroon-5", external_ids={"songkick": "Artist29315"}),
    ])
    
    service = SongkickEventImportService(
        provider_manager=MagicMock(),
        event_repository=MagicMock(),
        venue_repository=MagicMock(),
        artist_repository=mock_artist_repo
    )
    
    result = await service._resolve_artist_ids([976211, 22766, 29315], "demi-lovato")
    
    # Should include all resolved artists
    assert "demi-lovato" in result
    assert "foo-fighters" in result
    assert "maroon-5" in result
    assert mock_artist_repo.get_by_songkick_id.call_count == 3


@pytest.mark.asyncio
async def test_resolve_artist_ids_partial_failure():
    """Test resolving when some artist IDs are not found"""
    mock_artist_repo = AsyncMock()
    mock_artist_repo.get_by_songkick_id = AsyncMock(side_effect=[
        Artist(name="Demi Lovato", normalized_name="demi lovato", slug="demi-lovato", external_ids={"songkick": "Artist976211"}),
        None,  # Artist 999999 not found
    ])
    
    service = SongkickEventImportService(
        provider_manager=MagicMock(),
        event_repository=MagicMock(),
        venue_repository=MagicMock(),
        artist_repository=mock_artist_repo
    )
    
    result = await service._resolve_artist_ids([976211, 999999], "demi-lovato")
    
    # Should include initiating artist and resolved artist (deduplicated)
    assert result == ["demi-lovato"]
    assert mock_artist_repo.get_by_songkick_id.call_count == 2


@pytest.mark.asyncio
async def test_resolve_artist_ids_all_not_found():
    """Test resolving when no artist IDs are found"""
    mock_artist_repo = AsyncMock()
    mock_artist_repo.get_by_songkick_id = AsyncMock(side_effect=[None, None])
    
    service = SongkickEventImportService(
        provider_manager=MagicMock(),
        event_repository=MagicMock(),
        venue_repository=MagicMock(),
        artist_repository=mock_artist_repo
    )
    
    result = await service._resolve_artist_ids([999999, 888888], "demi-lovato")
    
    # Should still include initiating artist as fallback
    assert result == ["demi-lovato"]
    assert mock_artist_repo.get_by_songkick_id.call_count == 2


@pytest.mark.asyncio
async def test_resolve_artist_ids_empty_list():
    """Test resolving with empty artist IDs list"""
    mock_artist_repo = AsyncMock()
    
    service = SongkickEventImportService(
        provider_manager=MagicMock(),
        event_repository=MagicMock(),
        venue_repository=MagicMock(),
        artist_repository=mock_artist_repo
    )
    
    result = await service._resolve_artist_ids([], "demi-lovato")
    
    # Should include initiating artist even with empty list
    assert result == ["demi-lovato"]
    mock_artist_repo.get_by_songkick_id.assert_not_called()


# ============================================================
# LINEUP ARTISTS JOIN THE EVENT'S ARTIST LIST
# ============================================================
#
# A gigography payload names the artist being browsed; the festival's own
# lineup names everyone. Both belong on the event's artist list, because both
# are real GigCrowd artists the show is theirs. An id that resolves to no
# imported artist is skipped, not guessed at - the same rule the lineup page
# applies when it renders a name without a link.

from app.repositories.artist_repository import ArtistRepository
from app.services.lineup_artist_resolver import external_id_for
from app.services.songkick_event_import_service import _lineup_songkick_ids
from tests.support.fake_mongo import FakeDatabase


def repository_over(artists: list[dict]):
    return ArtistRepository(
        FakeDatabase({"artists": artists, "events": []})
    )


def service_over(artists: list[dict]) -> SongkickEventImportService:
    return SongkickEventImportService(
        provider_manager=MagicMock(),
        event_repository=MagicMock(),
        venue_repository=MagicMock(),
        artist_repository=repository_over(artists),
    )


DEMI = {
    "name": "Demi Lovato",
    "slug": "demi-lovato",
    "external_ids": {"songkick": external_id_for("1715773")},
}

WEATHER = {
    "name": "Weather",
    "slug": "weather",
    "external_ids": {"songkick": external_id_for("976211")},
}


@pytest.mark.asyncio
async def test_lineup_artists_that_resolve_join_the_artist_list():
    """The initiating artist stays first; resolved lineup members follow."""

    service = service_over([DEMI, WEATHER])

    result = await service._resolve_artist_ids(
        [],
        "demi-lovato",
        lineup_ids=["1715773", "976211", "999999999"],
    )

    # The initiating artist is first regardless of what the lineup resolved,
    # and the id with no imported artist contributes nothing.
    assert result == ["demi-lovato", "weather"]


@pytest.mark.asyncio
async def test_a_lineup_id_already_in_the_list_is_not_duplicated():
    """The initiating artist appearing in the lineup stays one entry."""

    service = service_over([DEMI])

    result = await service._resolve_artist_ids(
        [],
        "demi-lovato",
        lineup_ids=["1715773", "1715773"],
    )

    assert result == ["demi-lovato"]


@pytest.mark.asyncio
async def test_an_empty_lineup_resolves_to_the_initiator_alone():
    service = service_over([DEMI])

    result = await service._resolve_artist_ids(
        [],
        "demi-lovato",
        lineup_ids=[],
    )

    assert result == ["demi-lovato"]


# ============================================================
# READING LINEUP IDS OUT OF A PAYLOAD
# ============================================================


def test_lineup_ids_are_read_from_the_lineup_key():
    payload = {
        "lineup": [
            {"name": "Demi Lovato", "songkick_id": "1715773"},
            {"name": "Weather", "songkick_id": "976211"},
        ]
    }

    assert _lineup_songkick_ids(payload) == ["1715773", "976211"]


def test_lineup_ids_are_read_from_the_performers_fallback():
    """The detail page and the JSON-LD parse do not agree on one key."""

    payload = {
        "performers": [
            {"name": "Demi Lovato", "songkickId": "1715773"},
        ]
    }

    assert _lineup_songkick_ids(payload) == ["1715773"]


def test_an_entry_without_an_id_contributes_nothing():
    """Nothing is inferred from a name: an id is the only usable identity."""

    payload = {
        "lineup": [
            {"name": "Some Band"},
            {"name": "Demi Lovato", "songkick_id": "1715773"},
        ]
    }

    assert _lineup_songkick_ids(payload) == ["1715773"]


def test_duplicates_are_removed_and_bill_order_kept():
    payload = {
        "lineup": [
            {"name": "Weather", "songkick_id": "976211"},
            {"name": "Demi Lovato", "songkick_id": "1715773"},
            {"name": "Weather (again)", "songkick_id": "976211"},
        ]
    }

    assert _lineup_songkick_ids(payload) == ["976211", "1715773"]


def test_a_payload_with_no_lineup_has_no_ids():
    assert _lineup_songkick_ids({}) == []
    assert _lineup_songkick_ids({"lineup": "not-a-list"}) == []