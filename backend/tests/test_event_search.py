import pytest
from datetime import datetime, timedelta, UTC
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


class TestEventSearchPast:
    """Tests for searching past events"""
    
    def test_search_past_events_uses_setlistfm(self, client, mock_db):
        """Test that past events search uses Setlist.fm API"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", "test-key"), \
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
                
                response = client.get("/events/search/external?query=metallica&event_type=past")
        
        assert response.status_code == 200
        mock_source.search_events.assert_called_once()
        
        # Verify date parameters were passed (default 2 years back)
        call_args = mock_source.search_events.call_args
        assert call_args[0][0] == "metallica"
        assert call_args[1]["start_date"] is not None
        assert call_args[1]["end_date"] is not None
    
    def test_search_past_events_without_api_key_returns_error(self, client, mock_db):
        """Test that past events search returns 503 without Setlist.fm API key"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", None):
            
            response = client.get("/events/search/external?query=metallica&event_type=past")
        
        assert response.status_code == 503
        assert "Setlist.fm API key not configured" in response.json()["detail"]
    
    def test_search_past_events_with_custom_date_range(self, client, mock_db):
        """Test past events search with custom date range"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        start_date = (datetime.now(UTC) - timedelta(days=365)).isoformat()
        end_date = datetime.now(UTC).isoformat()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", "test-key"), \
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
                
                response = client.get(
                    f"/events/search/external?query=metallica&event_type=past&start_date={start_date}&end_date={end_date}"
                )
        
        assert response.status_code == 200
        
        # Verify custom dates were passed
        call_args = mock_source.search_events.call_args
        assert call_args[1]["start_date"] is not None
        assert call_args[1]["end_date"] is not None
    
    def test_search_past_events_sets_status_to_past(self, client, mock_db):
        """Test that past events have status set to 'past'"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        mock_event = {
            "artist": {"name": "Metallica"},
            "venue": {"name": "Stadium"},
            "eventDate": "20-06-2023"
        }
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[mock_event])
            MockSource.return_value = mock_source
            
            with patch("app.ingestion.normalizers.event_normalizer.EventNormalizer") as MockNormalizer, \
                 patch("app.ingestion.deduplicator.event_deduplicator.EventDeduplicator") as MockDeduplicator:
                
                mock_normalizer = Mock()
                normalized_event = {"title": "Metallica Live", "status": "upcoming"}
                mock_normalizer.normalize = Mock(return_value=normalized_event)
                MockNormalizer.return_value = mock_normalizer
                
                mock_deduplicator = Mock()
                mock_deduplicator.find_duplicate = AsyncMock(return_value=None)
                MockDeduplicator.return_value = mock_deduplicator
                
                response = client.get("/events/search/external?query=metallica&event_type=past")
        
        assert response.status_code == 200
        # Verify status was set to past
        assert normalized_event["status"] == "past"


class TestEventSearchFuture:
    """Tests for searching future events"""
    
    def test_search_future_events_uses_ticketmaster(self, client, mock_db):
        """Test that future events search uses TicketMaster API first"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.TICKETMASTER_CONSUMER_KEY", "test-key"), \
             patch("app.config.settings.TICKETMASTER_CONSUMER_SECRET", "test-secret"), \
             patch("app.ingestion.sources.ticketmaster_source.TicketMasterSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[{"id": "event1"}])
            MockSource.return_value = mock_source
            
            with patch("app.ingestion.normalizers.event_normalizer.EventNormalizer") as MockNormalizer, \
                 patch("app.ingestion.deduplicator.event_deduplicator.EventDeduplicator") as MockDeduplicator:
                
                mock_normalizer = Mock()
                MockNormalizer.return_value = mock_normalizer
                
                mock_deduplicator = Mock()
                MockDeduplicator.return_value = mock_deduplicator
                
                response = client.get("/events/search/external?query=metallica&event_type=future")
        
        assert response.status_code == 200
        mock_source.search_events.assert_called_once_with("metallica")
    
    def test_search_future_events_fallback_to_bandsintown(self, client, mock_db):
        """Test that future events search falls back to Bandsintown when TicketMaster returns no results"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.TICKETMASTER_CONSUMER_KEY", "test-key"), \
             patch("app.config.settings.TICKETMASTER_CONSUMER_SECRET", "test-secret"), \
             patch("app.ingestion.sources.ticketmaster_source.TicketMasterSource") as MockTM, \
             patch("app.ingestion.sources.bandsintown_source.BandsintownSource") as MockBIT:
            
            mock_tm = Mock()
            mock_tm.search_events = AsyncMock(return_value=[])  # No results from TicketMaster
            MockTM.return_value = mock_tm
            
            mock_bit = Mock()
            mock_bit.search_events = AsyncMock(return_value=[{"title": "Metallica Concert"}])
            MockBIT.return_value = mock_bit
            
            with patch("app.ingestion.normalizers.event_normalizer.EventNormalizer") as MockNormalizer, \
                 patch("app.ingestion.deduplicator.event_deduplicator.EventDeduplicator") as MockDeduplicator:
                
                mock_normalizer = Mock()
                MockNormalizer.return_value = mock_normalizer
                
                mock_deduplicator = Mock()
                MockDeduplicator.return_value = mock_deduplicator
                
                response = client.get("/events/search/external?query=metallica&event_type=future")
        
        assert response.status_code == 200
        mock_tm.search_events.assert_called_once()
        mock_bit.search_events.assert_called_once()
    
    def test_search_future_events_sets_status_to_upcoming(self, client, mock_db):
        """Test that future events have status set to 'upcoming'"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.TICKETMASTER_CONSUMER_KEY", "test-key"), \
             patch("app.config.settings.TICKETMASTER_CONSUMER_SECRET", "test-secret"), \
             patch("app.ingestion.sources.ticketmaster_source.TicketMasterSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[{"id": "event1"}])
            MockSource.return_value = mock_source
            
            with patch("app.ingestion.normalizers.event_normalizer.EventNormalizer") as MockNormalizer, \
                 patch("app.ingestion.deduplicator.event_deduplicator.EventDeduplicator") as MockDeduplicator:
                
                mock_normalizer = Mock()
                normalized_event = {"title": "Metallica Live", "status": "past"}
                mock_normalizer.normalize = Mock(return_value=normalized_event)
                MockNormalizer.return_value = mock_normalizer
                
                mock_deduplicator = Mock()
                mock_deduplicator.find_duplicate = AsyncMock(return_value=None)
                MockDeduplicator.return_value = mock_deduplicator
                
                response = client.get("/events/search/external?query=metallica&event_type=future")
        
        assert response.status_code == 200
        # Verify status was set to upcoming
        assert normalized_event["status"] == "upcoming"


class TestEventSearchCaching:
    """Tests for event search caching with event_type separation"""
    
    def test_cache_key_includes_event_type(self, client, mock_db):
        """Test that cache key includes event_type for separate caching"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", "test-key"), \
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
                
                response = client.get("/events/search/external?query=metallica&event_type=past")
        
        assert response.status_code == 200
        
        # Verify cache key includes event_type
        call_args = mock_db.cache.update_one.call_args
        cache_key = call_args[0][0]["_id"]
        assert "past" in cache_key
        assert "metallica" in cache_key
    
    def test_past_and_future_have_separate_cache_keys(self, client, mock_db):
        """Test that past and future events have separate cache entries"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", "test-key"), \
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
                
                # Search past events
                response1 = client.get("/events/search/external?query=metallica&event_type=past")
                past_cache_key = mock_db.cache.update_one.call_args[0][0]["_id"]
                
                # Search future events
                response2 = client.get("/events/search/external?query=metallica&event_type=future")
                future_cache_key = mock_db.cache.update_one.call_args[0][0]["_id"]
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert past_cache_key != future_cache_key
        assert "past" in past_cache_key
        assert "future" in future_cache_key
    
    def test_cache_hit_returns_cached_events(self, client, mock_db):
        """Test that cache hit returns cached events without calling API"""
        cached_events = [
            {"_id": "event1", "title": "Metallica Live", "status": "past"}
        ]
        
        mock_db.cache.find_one = AsyncMock(return_value={
            "_id": "search:metallica:past:...",
            "events": cached_events,
            "created_at": datetime.now(UTC)
        })
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[])
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=metallica&event_type=past")
        
        assert response.status_code == 200
        assert response.json()["source"] == "cache"
        assert response.json()["events"] == cached_events
        # API should not be called on cache hit
        mock_source.search_events.assert_not_called()


class TestEventSearchDateValidation:
    """Tests for date parameter validation"""
    
    def test_invalid_start_date_format_returns_error(self, client, mock_db):
        """Test that invalid start date format returns 400 error"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db):
            response = client.get(
                "/events/search/external?query=metallica&event_type=past&start_date=invalid-date"
            )
        
        assert response.status_code == 400
        assert "Invalid start_date format" in response.json()["detail"]
    
    def test_invalid_end_date_format_returns_error(self, client, mock_db):
        """Test that invalid end date format returns 400 error"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db):
            response = client.get(
                "/events/search/external?query=metallica&event_type=past&end_date=invalid-date"
            )
        
        assert response.status_code == 400
        assert "Invalid end_date format" in response.json()["detail"]
    
    def test_valid_iso_date_format_accepted(self, client, mock_db):
        """Test that valid ISO date format is accepted"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        start_date = "2024-01-01T00:00:00"
        end_date = "2024-12-31T23:59:59"
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", "test-key"), \
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
                
                response = client.get(
                    f"/events/search/external?query=metallica&event_type=past&start_date={start_date}&end_date={end_date}"
                )
        
        assert response.status_code == 200


class TestEventSearchPagination:
    """Tests for search result pagination"""
    
    def test_skip_parameter_works(self, client, mock_db):
        """Test that skip parameter skips results"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", "test-key"), \
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
                
                response = client.get("/events/search/external?query=metallica&event_type=past&skip=5")
        
        assert response.status_code == 200
    
    def test_limit_parameter_works(self, client, mock_db):
        """Test that limit parameter limits results"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", "test-key"), \
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
                
                response = client.get("/events/search/external?query=metallica&event_type=past&limit=10")
        
        assert response.status_code == 200
    
    def test_limit_over_100_returns_error(self, client, mock_db):
        """Test that limit over 100 returns validation error"""
        response = client.get("/events/search/external?query=metallica&event_type=past&limit=101")
        assert response.status_code == 422  # Validation error
    
    def test_response_includes_total_count(self, client, mock_db):
        """Test that response includes total count of events"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.cache.update_one = AsyncMock()
        mock_db.cache.create_index = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLIST_FM_API_KEY", "test-key"), \
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
                
                response = client.get("/events/search/external?query=metallica&event_type=past")
        
        assert response.status_code == 200
        assert "total" in response.json()
