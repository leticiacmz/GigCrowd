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
    
    result = await service._resolve_artist_ids([976211])
    
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
    
    result = await service._resolve_artist_ids([976211, 22766, 29315])
    
    assert result == ["demi-lovato", "foo-fighters", "maroon-5"]
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
    
    result = await service._resolve_artist_ids([976211, 999999])
    
    # Only the resolved artist should be returned
    assert result == ["demi-lovato"]
    assert mock_artist_repo.get_by_songkick_id.call_count == 2


@pytest.mark.asyncio
async def test_resolve_artist_ids_all_not_found():
    """Test resolving when no artist IDs are found"""
    mock_artist_repo = AsyncMock()
    mock_artist_repo.get_by_songkick_id = AsyncMock(return_value=None)
    
    service = SongkickEventImportService(
        provider_manager=MagicMock(),
        event_repository=MagicMock(),
        venue_repository=MagicMock(),
        artist_repository=mock_artist_repo
    )
    
    result = await service._resolve_artist_ids([999999, 888888])
    
    # Empty list when no artists resolved
    assert result == []
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
    
    result = await service._resolve_artist_ids([])
    
    assert result == []
    mock_artist_repo.get_by_songkick_id.assert_not_called()