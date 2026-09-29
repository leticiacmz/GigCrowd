import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.provider_manager import ProviderManager
from app.services.synchronization_service import SynchronizationService
from app.services.event_import_service import EventImportService
from app.services.artist_service import ArtistService
from app.repositories.artist_follow_repository import ArtistFollowRepository
from app.domain.artist import Artist


@pytest.mark.asyncio
async def test_provider_manager_defaults_to_songkick():
    """Verify ProviderManager defaults to Songkick for both search and events"""
    mock_provider = MagicMock()
    mock_provider.search_artist = AsyncMock(return_value=[])
    mock_provider.get_artist_events = AsyncMock(return_value=[])
    
    with patch('app.services.provider_manager.registry') as mock_registry:
        mock_registry.get_provider.return_value = mock_provider
        
        provider_manager = ProviderManager()
        
        # Test search_artist default
        await provider_manager.search_artist("test artist")
        mock_registry.get_provider.assert_called_with("songkick")
        
        # Test get_artist_events default
        await provider_manager.get_artist_events("test artist")
        mock_registry.get_provider.assert_called_with("songkick")


@pytest.mark.asyncio
async def test_synchronization_service_defaults_to_songkick():
    """Verify SynchronizationService defaults to Songkick"""
    mock_artist_repo = AsyncMock()
    mock_event_import_service = AsyncMock()
    mock_event_import_service.sync_artist_events = AsyncMock(return_value={
        "events_received": 0
    })
    
    artist = Artist(
        name="Test Artist",
        normalized_name="test artist",
        slug="test-artist",
        external_ids={"songkick": "Artist123"},
        last_synced_at=None
    )
    
    sync_service = SynchronizationService(
        artist_repository=mock_artist_repo,
        event_import_service=mock_event_import_service
    )
    
    await sync_service.synchronize_artist(artist)
    
    # Verify event import was called with Songkick
    mock_event_import_service.sync_artist_events.assert_called_once()
    call_args = mock_event_import_service.sync_artist_events.call_args
    assert call_args[1]["provider"] == "songkick"


@pytest.mark.asyncio
async def test_artist_service_uses_songkick_for_sync():
    """Verify ArtistService uses Songkick for synchronization"""
    mock_artist_repo = AsyncMock()
    mock_artist_repo.get_by_slug = AsyncMock(return_value=Artist(
        id="test_id",
        name="Test Artist",
        normalized_name="test artist",
        slug="test-artist",
        external_ids={"songkick": "Artist123"},
        last_synced_at=None
    ))
    
    mock_event_repo = AsyncMock()
    mock_event_repo.count_upcoming_by_artist_slug = AsyncMock(return_value=0)
    mock_event_repo.count_by_artist_slug = AsyncMock(return_value=0)
    
    mock_sync_service = AsyncMock()
    mock_sync_service.synchronize_artist = AsyncMock(return_value={
        "artist": MagicMock(name="Test Artist"),
        "synced": True
    })

    mock_follow_repo = AsyncMock()
    mock_follow_repo.count_followers = AsyncMock(return_value=5)

    artist_service = ArtistService(
        artist_repository=mock_artist_repo,
        event_repository=mock_event_repo,
        artist_follow_repository=mock_follow_repo,
        synchronization_service=mock_sync_service
    )
    
    await artist_service.get_artist_profile("test-artist")
    
    # Verify sync was called
    mock_sync_service.synchronize_artist.assert_called_once()
    call_args = mock_sync_service.synchronize_artist.call_args
    assert call_args[1]["provider"] == "songkick"


@pytest.mark.asyncio
async def test_event_import_service_defaults_to_songkick():
    """Verify EventImportService defaults to Songkick"""
    mock_provider_manager = MagicMock()
    
    # Create a proper async mock for get_artist_events
    from unittest.mock import AsyncMock
    mock_songkick_provider = MagicMock()
    mock_songkick_provider.get_artist_events = AsyncMock(return_value={
        "events": [],
        "upcoming": [],
        "upcoming_festivals": [],
        "past_events": [],
        "total_events": 0
    })
    
    mock_provider_manager.get_provider = MagicMock(return_value=mock_songkick_provider)
    
    mock_event_repo = AsyncMock()
    mock_venue_repo = AsyncMock()
    mock_artist_repo = AsyncMock()
    
    artist = Artist(
        name="Test Artist",
        normalized_name="test artist",
        slug="test-artist",
        external_ids={"songkick": "Artist123"}
    )
    
    event_import_service = EventImportService(
        provider_manager=mock_provider_manager,
        event_repository=mock_event_repo,
        venue_repository=mock_venue_repo,
        artist_repository=mock_artist_repo
    )
    
    await event_import_service.sync_artist_events(artist)
    
    # Verify Songkick provider was requested
    mock_provider_manager.get_provider.assert_called_with("songkick")


@pytest.mark.asyncio
async def test_festival_event_with_initiating_artist_fallback():
    """Verify festival events include initiating artist even when others unresolved"""
    from app.services.songkick_event_import_service import SongkickEventImportService
    from app.domain.artist import Artist
    
    mock_provider_manager = MagicMock()
    mock_event_repo = AsyncMock()
    mock_venue_repo = AsyncMock()
    mock_artist_repo = AsyncMock()
    
    # Simulate one resolved artist, one unresolved
    mock_artist_repo.get_by_songkick_id = AsyncMock(side_effect=[
        Artist(name="Demi Lovato", normalized_name="demi lovato", slug="demi-lovato", external_ids={"songkick": "Artist976211"}),
        None  # Second artist not found
    ])
    
    service = SongkickEventImportService(
        provider_manager=mock_provider_manager,
        event_repository=mock_event_repo,
        venue_repository=mock_venue_repo,
        artist_repository=mock_artist_repo
    )
    
    # Resolve with initiating artist as fallback
    result = await service._resolve_artist_ids([976211, 999999], "demi-lovato")
    
    # Should include initiating artist even though one ID is unresolved
    assert "demi-lovato" in result
    assert len(result) == 1  # Only one unique artist (initiating artist)


@pytest.mark.asyncio
async def test_event_import_service_bandsintown_still_supported():
    """Verify Bandsintown can still be explicitly requested"""
    mock_provider_manager = MagicMock()
    mock_provider_manager.get_provider = MagicMock(return_value=MagicMock(
        get_artist_events=AsyncMock(return_value=[])
    ))
    mock_provider_manager.get_artist_events = AsyncMock(return_value=[])
    
    mock_event_repo = AsyncMock()
    mock_venue_repo = AsyncMock()
    mock_artist_repo = AsyncMock()
    
    artist = Artist(
        name="Test Artist",
        normalized_name="test artist",
        slug="test-artist",
        external_ids={"bandsintown": "bandsintown123"}
    )
    
    event_import_service = EventImportService(
        provider_manager=mock_provider_manager,
        event_repository=mock_event_repo,
        venue_repository=mock_venue_repo,
        artist_repository=mock_artist_repo
    )
    
    # Explicitly request Bandsintown
    await event_import_service.sync_artist_events(artist, provider="bandsintown")
    
    # Verify Bandsintown provider was requested
    mock_provider_manager.get_artist_events.assert_called_once_with("Test Artist", provider="bandsintown")


@pytest.mark.asyncio
async def test_spotify_cannot_create_canonical_artist():
    """Verify Spotify canonical import raises NotImplementedError"""
    from app.services.artist_import_service import ArtistImportService
    from app.schemas.artist_import import ArtistImportRequest
    
    mock_provider_manager = MagicMock()
    mock_artist_repo = AsyncMock()
    mock_artist_repo.get_by_external_id = AsyncMock(return_value=None)
    
    service = ArtistImportService(
        provider_manager=mock_provider_manager,
        artist_repository=mock_artist_repo
    )
    
    request = ArtistImportRequest(
        provider="spotify",
        provider_artist_id="spotify_id_123"
    )
    
    with pytest.raises(NotImplementedError) as exc_info:
        await service.import_artist(request)
    
    assert "deprecated" in str(exc_info.value).lower()
    assert "songkick" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_songkick_is_only_canonical_import_path():
    """Verify only Songkick can create canonical artists"""
    from app.services.artist_import_service import ArtistImportService
    from app.schemas.artist_import import ArtistImportRequest
    from app.domain.artist import Artist
    
    mock_provider_manager = MagicMock()
    mock_artist_repo = AsyncMock()
    mock_artist_repo.get_by_external_id = AsyncMock(return_value=None)
    mock_artist_repo.get_by_songkick_id = AsyncMock(return_value=None)  # Fix: return None instead of mock
    mock_artist_repo.generate_unique_slug = AsyncMock(return_value="test-artist")
    mock_artist_repo.insert_artist = AsyncMock()
    
    service = ArtistImportService(
        provider_manager=mock_provider_manager,
        artist_repository=mock_artist_repo
    )
    
    songkick_data = {
        "id": "Artist123",
        "name": "Test Artist",
        "is_valid": True,
        "is_active": True,
        "number_of_events": 10,
        "popularity": 0.5
    }
    
    # Songkick import should work
    result = await service.import_songkick_artist("Test Artist", songkick_data)
    
    assert result["is_new"] is True
    assert result["artist"].external_ids["songkick"] == "Artist123"
    
    # Verify artist was inserted
    mock_artist_repo.insert_artist.assert_called_once()