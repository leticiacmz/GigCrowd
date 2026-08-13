import pytest
from unittest.mock import AsyncMock, MagicMock
from app.repositories.artist_repository import ArtistRepository
from app.domain.artist import Artist


@pytest.mark.asyncio
async def test_get_by_songkick_id_numeric():
    """Test lookup by numeric Songkick ID"""
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value={
        "_id": "test_id",
        "name": "Demi Lovato",
        "normalized_name": "demi lovato",
        "slug": "demi-lovato",
        "external_ids": {"songkick": "Artist976211"}
    })
    
    repo = ArtistRepository(MagicMock())
    repo.collection = mock_collection
    
    result = await repo.get_by_songkick_id(976211)
    
    assert result is not None
    assert result.name == "Demi Lovato"
    mock_collection.find_one.assert_called_once_with({
        "external_ids.songkick": "Artist976211"
    })


@pytest.mark.asyncio
async def test_get_by_songkick_id_numeric_string():
    """Test lookup by numeric string Songkick ID"""
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value={
        "_id": "test_id",
        "name": "Demi Lovato",
        "normalized_name": "demi lovato",
        "slug": "demi-lovato",
        "external_ids": {"songkick": "Artist976211"}
    })
    
    repo = ArtistRepository(MagicMock())
    repo.collection = mock_collection
    
    result = await repo.get_by_songkick_id("976211")
    
    assert result is not None
    assert result.name == "Demi Lovato"
    mock_collection.find_one.assert_called_once_with({
        "external_ids.songkick": "Artist976211"
    })


@pytest.mark.asyncio
async def test_get_by_songkick_id_prefixed():
    """Test lookup by prefixed Songkick ID (Artist976211)"""
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value={
        "_id": "test_id",
        "name": "Demi Lovato",
        "normalized_name": "demi lovato",
        "slug": "demi-lovato",
        "external_ids": {"songkick": "Artist976211"}
    })
    
    repo = ArtistRepository(MagicMock())
    repo.collection = mock_collection
    
    result = await repo.get_by_songkick_id("Artist976211")
    
    assert result is not None
    assert result.name == "Demi Lovato"
    mock_collection.find_one.assert_called_once_with({
        "external_ids.songkick": "Artist976211"
    })


@pytest.mark.asyncio
async def test_get_by_songkick_id_not_found():
    """Test lookup when artist not found"""
    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    
    repo = ArtistRepository(MagicMock())
    repo.collection = mock_collection
    
    result = await repo.get_by_songkick_id(999999)
    
    assert result is None
    mock_collection.find_one.assert_called_once_with({
        "external_ids.songkick": "Artist999999"
    })