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


@pytest.mark.asyncio
async def test_the_import_loop_carries_the_payload_lineup_into_the_artist_list():
    """The seam between extraction and resolution, pinned end to end.

    The lineup reading and the resolution are each tested apart; this pins
    the wire in `sync_artist_events` that carries the payload's lineup to the
    resolver, so a refactor of the import loop cannot quietly stop passing it
    along and shed the association on every sync. The payload states the id in
    both spellings, and the entry that resolves to nobody contributes nothing.
    """

    payload = {
        "songkick_id": "8100001",
        "name": "Villa Sound 2026",
        "event_type": "festival",
        "url": (
            "https://www.songkick.com/festivals/"
            "8100001-villa-sound"
        ),
        "start_date": "2026-03-25T20:00:00+00:00",
        "end_date": None,
        "venue": {
            "name": "Parque de la Ciudad",
            "url": (
                "https://www.songkick.com/venues/"
                "9001-parque-de-la-ciudad"
            ),
            "address": {
                "addressLocality": "Buenos Aires",
                "addressCountry": "AR",
            },
        },
        "festival": {
            "series_id": "44001",
            "name": "Villa Sound",
            "url": (
                "https://www.songkick.com/festivals/"
                "8100001-villa-sound"
            ),
        },
        "lineup": [
            {"name": "Weather", "songkick_id": "976211"},
            {"name": "Nobody Imported", "songkickId": "999999999"},
        ],
        "artist_ids": [1715773],
    }

    provider_manager = MagicMock()
    songkick_provider = MagicMock()
    songkick_provider.get_artist_events = AsyncMock(
        return_value={
            "events": [payload],
            "upcoming_festivals": [],
        }
    )
    provider_manager.get_provider = MagicMock(
        return_value=songkick_provider
    )

    event_repository = MagicMock()
    event_repository.upsert_event_by_provider = AsyncMock(
        return_value=True
    )

    venue_repository = MagicMock()
    venue_repository.upsert_venue = AsyncMock(return_value=False)
    venue_repository.get_by_external_id = AsyncMock(
        return_value={"slug": "parque-de-la-ciudad"}
    )
    venue_repository.get_by_name = AsyncMock(return_value=None)

    # Full stored shapes: this path reads the initiating artist through
    # `get_by_songkick_id`, which maps the document the way the real
    # catalogue stores it.
    catalogue = [
        {
            "_id": "6ac5d823147149ffe667e901",
            "name": "Demi Lovato",
            "normalized_name": "demi lovato",
            "slug": "demi-lovato",
            "external_ids": {
                "songkick": external_id_for("1715773"),
            },
        },
        {
            "_id": "6ac5d823147149ffe667e902",
            "name": "Weather",
            "normalized_name": "weather",
            "slug": "weather",
            "external_ids": {
                "songkick": external_id_for("976211"),
            },
        },
    ]

    service = SongkickEventImportService(
        provider_manager=provider_manager,
        event_repository=event_repository,
        venue_repository=venue_repository,
        artist_repository=repository_over(catalogue),
    )

    await service.sync_artist_events(
        Artist(
            name="Demi Lovato",
            normalized_name="demi lovato",
            slug="demi-lovato",
            external_ids={"songkick": external_id_for("1715773")},
        )
    )

    event_repository.upsert_event_by_provider.assert_awaited_once()

    written = (
        event_repository.upsert_event_by_provider
        .call_args.args[0]
    )

    # The initiating artist first, the imported lineup member after it, and
    # the lineup entry with no imported artist contributing nothing.
    assert written.artist_slugs == ["demi-lovato", "weather"]


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