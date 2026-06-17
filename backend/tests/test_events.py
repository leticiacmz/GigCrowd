import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.models.event import EventStatus


@pytest.fixture
def client():
    """Test client for FastAPI app"""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = Mock()
    db.events = Mock()
    db.cache = Mock()
    db.users = Mock()
    return db


@pytest.fixture
def sample_event():
    """Sample event data"""
    return {
        "_id": "event1",
        "title": "Metallica Concert",
        "artist_id": "artist1",
        "venue_name": "Stadium",
        "date": datetime.utcnow(),
        "location": "São Paulo, Brazil",
        "status": EventStatus.UPCOMING,
        "going_count": 0,
        "maybe_count": 0,
        "went_count": 0,
        "is_cached": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }


class TestEventCreation:
    """Tests for event creation and storage"""
    
    @pytest.mark.asyncio
    async def test_create_event_success(self, client, mock_db, sample_event):
        """Test creating a new event"""
        mock_db.events.insert_one = AsyncMock(return_value=sample_event)
        
        with patch("app.database.connection.get_database", return_value=mock_db):
            response = client.post("/events", json={
                "title": "Metallica Concert",
                "artist_id": "artist1",
                "venue_name": "Stadium",
                "date": datetime.utcnow().isoformat(),
                "location": "São Paulo, Brazil"
            })
        
        assert response.status_code == 201
    
    @pytest.mark.asyncio
    async def test_get_event_by_id(self, client, mock_db, sample_event):
        """Test getting an event by ID"""
        mock_db.events.find_one = AsyncMock(return_value=sample_event)
        
        with patch("app.database.connection.get_database", return_value=mock_db):
            response = client.get("/events/event1")
        
        assert response.status_code == 200
        assert response.json()["id"] == "event1"
    
    @pytest.mark.asyncio
    async def test_get_event_not_found(self, client, mock_db):
        """Test getting a non-existent event"""
        mock_db.events.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db):
            response = client.get("/events/nonexistent")
        
        assert response.status_code == 404


class TestEventCache:
    """Tests for event caching strategy"""
    
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self, client, mock_db, sample_event):
        """Test that cache returns data when available"""
        cached_data = {
            "_id": "search:metallica",
            "events": [sample_event],
            "created_at": datetime.utcnow(),
            "query": "metallica"
        }
        
        mock_db.cache.find_one = AsyncMock(return_value=cached_data)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"):
            response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 200
        assert response.json()["source"] == "cache"
    
    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_source(self, client, mock_db):
        """Test that cache miss fetches from external source"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[])
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 200
        assert response.json()["source"] == "external"
    
    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self, client, mock_db, sample_event):
        """Test that cache expires after TTL"""
        old_cache = {
            "_id": "search:metallica",
            "events": [sample_event],
            "created_at": datetime.utcnow() - timedelta(days=8),  # Older than 7 days
            "query": "metallica"
        }
        
        mock_db.cache.find_one = AsyncMock(return_value=old_cache)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"), \
             patch("app.config.settings.CACHE_TTL_SECONDS", 604800), \
             patch("app.ingestion.sources.setlistfm_source.SetlistFmSource") as MockSource:
            
            mock_source = Mock()
            mock_source.search_events = AsyncMock(return_value=[])
            MockSource.return_value = mock_source
            
            response = client.get("/events/search/external?query=metallica")
        
        # Should fetch from external source since cache is expired
        assert response.status_code == 200
        assert response.json()["source"] == "external"


class TestEventStorage:
    """Tests for permanent event storage"""
    
    @pytest.mark.asyncio
    async def test_import_cached_event_to_permanent(self, client, mock_db, sample_event):
        """Test importing a cached event to permanent storage"""
        cached_event = {
            "_id": "search:metallica",
            "events": [{
                **sample_event,
                "is_cached": True,
                "cached_at": datetime.utcnow()
            }]
        }
        
        mock_db.cache.find_one = AsyncMock(return_value=cached_event)
        mock_db.events.find_one = AsyncMock(return_value=None)
        mock_db.events.insert_one = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.auth.dependencies.get_current_active_user") as mock_auth:
            mock_auth.return_value = {"_id": "user1"}
            
            response = client.post("/events/import/event1")
        
        assert response.status_code == 200
        mock_db.events.insert_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cached_event_has_flag(self, client, mock_db, sample_event):
        """Test that cached events have is_cached flag"""
        cached_event = {
            "_id": "search:metallica",
            "events": [{
                **sample_event,
                "is_cached": True,
                "cached_at": datetime.utcnow()
            }]
        }
        
        mock_db.cache.find_one = AsyncMock(return_value=cached_event)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.config.settings.SETLISTFM_API_KEY", "test-key"):
            response = client.get("/events/search/external?query=metallica")
        
        assert response.status_code == 200
        assert response.json()["events"][0]["is_cached"] == True
    
    @pytest.mark.asyncio
    async def test_permanent_event_no_cache_flag(self, client, mock_db, sample_event):
        """Test that permanent events don't have cache flags"""
        mock_db.events.find_one = AsyncMock(return_value=sample_event)
        
        with patch("app.database.connection.get_database", return_value=mock_db):
            response = client.get("/events/event1")
        
        assert response.status_code == 200
        assert response.json()["is_cached"] == False


class TestEventAttendance:
    """Tests for event attendance and automatic import"""
    
    @pytest.mark.asyncio
    async def test_attend_cached_event_imports_automatically(self, client, mock_db, sample_event):
        """Test that attending a cached event imports it automatically"""
        cached_event = {
            "_id": "search:metallica",
            "events": [{
                **sample_event,
                "is_cached": True,
                "cached_at": datetime.utcnow()
            }]
        }
        
        mock_db.cache.find_one = AsyncMock(return_value=cached_event)
        mock_db.events.find_one = AsyncMock(return_value=None)
        mock_db.events.insert_one = AsyncMock()
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.services.show_log_service.ShowLogService.create_show_log") as mock_create_log, \
             patch("app.services.activity_service.ActivityService.create_activity") as mock_create_activity, \
             patch("app.auth.dependencies.get_current_active_user") as mock_auth:
            
            mock_auth.return_value = {"_id": "user1"}
            mock_create_log.return_value = Mock()
            mock_create_activity = AsyncMock()
            
            response = client.post("/events/event1/attend", json={"status": "going"})
        
        assert response.status_code == 200
        mock_db.events.insert_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_attend_permanent_event_no_import(self, client, mock_db, sample_event):
        """Test that attending a permanent event doesn't trigger import"""
        mock_db.cache.find_one = AsyncMock(return_value=None)
        mock_db.events.find_one = AsyncMock(return_value=sample_event)
        
        with patch("app.database.connection.get_database", return_value=mock_db), \
             patch("app.services.show_log_service.ShowLogService.create_show_log") as mock_create_log, \
             patch("app.services.activity_service.ActivityService.create_activity") as mock_create_activity, \
             patch("app.auth.dependencies.get_current_active_user") as mock_auth:
            
            mock_auth.return_value = {"_id": "user1"}
            mock_create_log.return_value = Mock()
            mock_create_activity = AsyncMock()
            
            response = client.post("/events/event1/attend", json={"status": "going"})
        
        assert response.status_code == 200
        # insert_one should NOT be called since event is already permanent
        assert not hasattr(mock_db.events, 'insert_one') or not mock_db.events.insert_one.called


class TestEventQueries:
    """Tests for event queries and filtering"""
    
    @pytest.mark.asyncio
    async def test_get_events_with_filters(self, client, mock_db):
        """Test getting events with filters"""
        mock_db.events.find = Mock()
        mock_db.find().skip = Mock(return_value=mock_db.find())
        mock_db.find().limit = Mock(return_value=mock_db.find())
        mock_db.find().to_list = AsyncMock(return_value=[])
        
        with patch("app.database.connection.get_database", return_value=mock_db):
            response = client.get("/events?artist_id=artist1&location=São Paulo")
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_get_event_attendees(self, client, mock_db):
        """Test getting attendees for an event"""
        mock_db.show_logs = Mock()
        mock_db.show_logs.find = Mock()
        mock_db.find().skip = Mock(return_value=mock_db.find())
        mock_db.find().limit = Mock(return_value=mock_db.find())
        mock_db.find().to_list = AsyncMock(return_value=[])
        
        with patch("app.database.connection.get_database", return_value=mock_db):
            response = client.get("/events/event1/attendees")
        
        assert response.status_code == 200


class TestEventDeduplication:
    """Tests for event deduplication"""
    
    @pytest.mark.asyncio
    async def test_duplicate_event_not_stored_twice(self, client, mock_db, sample_event):
        """Test that duplicate events are not stored twice"""
        mock_db.events.find_one = AsyncMock(return_value=sample_event)
        
        with patch("app.database.connection.get_database", return_value=mock_db):
            response = client.post("/events/import/event1")
        
        # Should return message that event already exists
        assert response.status_code == 200
        assert "already in permanent storage" in response.json()["message"]
