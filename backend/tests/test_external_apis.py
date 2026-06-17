import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Test client for FastAPI app"""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = Mock()
    db.cache = Mock()
    db.events = Mock()
    return db


@pytest.fixture
def mock_settings():
    """Mock settings with API key"""
    from app.config import settings
    original_key = settings.SETLISTFM_API_KEY
    settings.SETLISTFM_API_KEY = "test-api-key"
    yield settings
    settings.SETLISTFM_API_KEY = original_key


class TestSetlistFmAPI:
    """Tests for Setlist.fm API integration"""
    
    @pytest.mark.asyncio
    async def test_search_without_api_key_returns_error(self, client):
        """Test that search returns 503 without API key"""
        from app.config import settings
        original_key = settings.SETLISTFM_API_KEY
        settings.SETLISTFM_API_KEY = None
        
        response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 503
        assert "API key not configured" in response.json()["detail"]
        
        settings.SETLISTFM_API_KEY = original_key
    
    @pytest.mark.asyncio
    async def test_search_with_api_key_calls_setlistfm(self, client, mock_db):
        """Test that search calls Setlist.fm API when key is configured"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[])
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 200
        mock_source.search_events.assert_called_once_with("metallica")
    
    @pytest.mark.asyncio
    async def test_search_artist_by_name(self, client, mock_db):
        """Test searching for events by artist name"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        mock_event = {
            "artist": {"name": "Metallica"},
            "venue": {"name": "Stadium"},
            "eventDate": "2024-06-20"
        }
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[mock_event])
            MockSource.return_value = mock_source
            
            with patch("app.ingestion.normalizers.event_normalizer.EventNormalizer") as MockNormalizer, \
                 patch("app.ingestion.deduplicator.event_deduplicator.EventDeduplicator") as MockDeduplicator:
                
                mock_normalizer = Mock()
                mock_normalizer.normalize = Mock(return_value=mock_event)
                MockNormalizer.return_value = mock_normalizer
                
                mock_deduplicator = Mock()
                mock_deduplicator.find_duplicate = AsyncMock(return_value=None)
                MockDeduplicator.return_value = mock_deduplicator
                
                response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 200
        mock_source.search_events.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_search_by_venue(self, client, mock_db):
        """Test searching for events by venue"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[])
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=stadium")
        
        assert response.status_code == 200
        mock_source.search_events.assert_called_once_with("stadium")
    
    @pytest.mark.asyncio
    async def test_search_by_city(self, client, mock_db):
        """Test searching for events by city"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[])
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=são paulo")
        
        assert response.status_code == 200
        mock_source.search_events.assert_called_once_with("são paulo")


class TestAPIDataNormalization:
    """Tests for normalizing data from external APIs"""
    
    @pytest.mark.asyncio
    async def test_normalizes_setlistfm_data(self, client, mock_db):
        """Test that Setlist.fm data is normalized correctly"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        raw_event = {
            "artist": {"name": "Metallica", "mbid": "artist-mbid"},
            "venue": {"name": "Stadium", "city": {"name": "São Paulo", "country": {"name": "Brazil"}}},
            "eventDate": "20-06-2024"
        }
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[raw_event])
            MockSource.return_value = mock_source
            
            with patch("app.ingestion.normalizers.event_normalizer.EventNormalizer") as MockNormalizer, \
                 patch("app.ingestion.deduplicator.event_deduplicator.EventDeduplicator") as MockDeduplicator:
                
                mock_normalizer = Mock()
                normalized = {
                    "_id": "event1",
                    "title": "Metallica Concert",
                    "artist_id": "artist-mbid",
                    "venue_name": "Stadium",
                    "date": datetime(2024, 6, 20),
                    "location": "São Paulo, Brazil"
                }
                mock_normalizer.normalize = Mock(return_value=normalized)
                MockNormalizer.return_value = mock_normalizer
                
                mock_deduplicator = Mock()
                mock_deduplicator.find_duplicate = AsyncMock(return_value=None)
                MockDeduplicator.return_value = mock_deduplicator
                
                response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 200
        mock_normalizer.normalize.assert_called_once_with(raw_event)
    
    @pytest.mark.asyncio
    async def test_handles_empty_api_response(self, client, mock_db):
        """Test handling empty response from API"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[])
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=nonexistent")
        
        assert response.status_code == 200
        assert response.json()["events"] == []


class TestAPIErrorHandling:
    """Tests for API error handling"""
    
    @pytest.mark.asyncio
    async def test_handles_api_timeout(self, client, mock_db):
        """Test handling API timeout"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(side_effect=TimeoutError("API timeout"))
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 500
        assert "Error fetching events" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_handles_api_rate_limit(self, client, mock_db):
        """Test handling API rate limit"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(side_effect=Exception("Rate limit exceeded"))
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 500
    
    @pytest.mark.asyncio
    async def test_handles_invalid_api_response(self, client, mock_db):
        """Test handling invalid API response"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[{"invalid": "data"}])
            MockSource.return_value = mock_source
            
            with patch("app.ingestion.normalizers.event_normalizer.EventNormalizer") as MockNormalizer, \
                 patch("app.ingestion.deduplicator.event_deduplicator.EventDeduplicator") as MockDeduplicator:
                
                mock_normalizer = Mock()
                mock_normalizer.normalize = Mock(side_effect=ValueError("Invalid data"))
                MockNormalizer.return_value = mock_normalizer
                
                mock_deduplicator = Mock()
                MockDeduplicator.return_value = mock_deduplicator
                
                response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 500


class TestAPICaching:
    """Tests for API response caching"""
    
    @pytest.mark.asyncio
    async def test_caches_api_response(self, client, mock_db):
        """Test that API responses are cached"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[])
            MockSource.return_value = mock_source
            
            with patch("app.ingestion.normalizers.event_normalizer.EventNormalizer") as MockNormalizer, \
                 patch("app.ingestion.deduplicator.event_deduplicator.EventDeduplicator") as MockDeduplicator:
                
                mock_normalizer = Mock()
                MockNormalizer.return_value = mock_normalizer
                
                mock_deduplicator = Mock()
                MockDeduplicator.return_value = mock_deduplicator
                
                response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 200
        mock_db.cache.update_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_key_includes_query(self, client, mock_db):
        """Test that cache key includes search query"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[])
            MockSource.return_value = mock_source
            
            with patch("app.ingestion.normalizers.event_normalizer.EventNormalizer") as MockNormalizer, \
                 patch("app.ingestion.deduplicator.event_deduplicator.EventDeduplicator") as MockDeduplicator:
                
                mock_normalizer = Mock()
                MockNormalizer.return_value = mock_normalizer
                
                mock_deduplicator = Mock()
                MockDeduplicator.return_value = mock_deduplicator
                
                response = client.get("/events/search/external?query=metallica")
        
        # Verify cache key includes query
        call_args = mock_db.cache.update_one.call_args
        assert call_args[0][0]["_id"] == "search:metallica"


class TestMultipleAPIs:
    """Tests for multiple external API sources"""
    
    @pytest.mark.asyncio
    async def test_fallback_to_secondary_api(self, client, mock_db):
        """Test fallback to secondary API when primary fails"""
        # This would be implemented when we add Songkick
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(side_effect=Exception("Primary API failed"))
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=metallica")
        
        # Currently returns error, but could fallback to Songkick in future
        assert response.status_code == 500
