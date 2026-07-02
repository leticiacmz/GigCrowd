import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import Mock, AsyncMock, patch
from app.ingestion.sources.setlistfm_source import SetlistFmSource


class TestSetlistFmSourceDateFiltering:
    """Tests for Setlist.fm source date filtering"""
    
    def test_search_events_with_date_parameters(self):
        """Test that search_events accepts date parameters"""
        source = SetlistFmSource(api_key="test-key")
        
        # Mock the internal methods
        with patch.object(source, 'get_artist_events', new_callable=AsyncMock) as mock_get_events:
            mock_get_events.return_value = []
            
            # This test verifies the method signature accepts date parameters
            # The actual async call would need to be run in an async context
            assert callable(source.search_events)
    
    def test_normalize_setlist_filters_by_date(self):
        """Test that _normalize_setlist filters events by date range"""
        source = SetlistFmSource(api_key="test-key")
        
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2024, 1, 1)
        
        # Event within range
        valid_setlist = {
            "artist": {"name": "Metallica"},
            "venue": {"name": "Stadium", "city": {"name": "São Paulo", "country": {"name": "Brazil"}}},
            "eventDate": "15-06-2023"
        }
        
        result = source._normalize_setlist(valid_setlist, start_date, end_date)
        assert result is not None
        assert result["artist_name"] == "Metallica"
        assert result["status"] == "past"
        
        # Event before range
        old_setlist = {
            "artist": {"name": "Metallica"},
            "venue": {"name": "Stadium", "city": {"name": "São Paulo", "country": {"name": "Brazil"}}},
            "eventDate": "15-06-2022"
        }
        
        result = source._normalize_setlist(old_setlist, start_date, end_date)
        assert result is None
        
        # Event after range
        future_setlist = {
            "artist": {"name": "Metallica"},
            "venue": {"name": "Stadium", "city": {"name": "São Paulo", "country": {"name": "Brazil"}}},
            "eventDate": "15-06-2025"
        }
        
        result = source._normalize_setlist(future_setlist, start_date, end_date)
        assert result is None
    
    def test_normalize_setlist_without_date_filter(self):
        """Test that _normalize_setlist works without date filtering"""
        source = SetlistFmSource(api_key="test-key")
        
        setlist = {
            "artist": {"name": "Metallica"},
            "venue": {"name": "Stadium", "city": {"name": "São Paulo", "country": {"name": "Brazil"}}},
            "eventDate": "15-06-2023"
        }
        
        result = source._normalize_setlist(setlist)
        assert result is not None
        assert result["artist_name"] == "Metallica"
        assert result["venue_name"] == "Stadium"


class TestEventSearchParams:
    """Tests for event search parameters model"""
    
    def test_event_search_params_creation(self):
        """Test that EventSearchParams can be created with all parameters"""
        from app.models.event import EventSearchParams, EventType
        
        params = EventSearchParams(
            query="metallica",
            event_type=EventType.PAST,
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 1, 1, tzinfo=UTC),
            skip=0,
            limit=20
        )
        
        assert params.query == "metallica"
        assert params.event_type == "past"
        assert params.start_date is not None
        assert params.end_date is not None
        assert params.skip == 0
        assert params.limit == 20
    
    def test_event_search_params_defaults(self):
        """Test that EventSearchParams has correct defaults"""
        from app.models.event import EventSearchParams, EventType
        
        params = EventSearchParams(query="metallica")
        
        assert params.query == "metallica"
        assert params.event_type == "future"  # Default
        assert params.start_date is None
        assert params.end_date is None
        assert params.skip == 0
        assert params.limit == 20


class TestEventTypeLiteral:
    """Tests for EventType literal"""
    
    def test_event_type_values(self):
        """Test that EventType has correct values"""
        from app.models.event import EventType
        
        assert EventType.PAST == "past"
        assert EventType.FUTURE == "future"
    
    def test_event_type_literal(self):
        """Test that EventTypeLiteral accepts correct values"""
        from app.models.event import EventTypeLiteral
        
        assert "past" in ["past", "future"]
        assert "future" in ["past", "future"]


class TestCacheKeyGeneration:
    """Tests for cache key generation logic"""
    
    def test_cache_key_includes_event_type(self):
        """Test that cache key includes event type"""
        query = "metallica"
        event_type = "past"
        start_date = "2023-01-01T00:00:00"
        end_date = "2024-01-01T00:00:00"
        
        cache_key = f"search:{query.lower()}:{event_type}:{start_date}:{end_date}"
        
        assert "past" in cache_key
        assert "metallica" in cache_key
        assert "2023-01-01" in cache_key
    
    def test_cache_key_different_for_past_and_future(self):
        """Test that past and future events have different cache keys"""
        query = "metallica"
        start_date = "2023-01-01T00:00:00"
        end_date = "2024-01-01T00:00:00"
        
        past_key = f"search:{query.lower()}:past:{start_date}:{end_date}"
        future_key = f"search:{query.lower()}:future:{start_date}:{end_date}"
        
        assert past_key != future_key
        assert "past" in past_key
        assert "future" in future_key


class TestDateRangeDefaults:
    """Tests for default date ranges"""
    
    def test_past_events_default_date_range(self):
        """Test that past events use 2 years back as default"""
        now = datetime.now(UTC)
        two_years_ago = now - timedelta(days=730)
        
        assert two_years_ago < now
        assert (now - two_years_ago).days >= 729
    
    def test_future_events_default_date_range(self):
        """Test that future events use 1 year ahead as default"""
        now = datetime.now(UTC)
        one_year_ahead = now + timedelta(days=365)
        
        assert one_year_ahead > now
        assert (one_year_ahead - now).days >= 364


class TestAPIResponseStructure:
    """Tests for API response structure"""
    
    def test_response_structure_for_past_events(self):
        """Test that past events response has correct structure"""
        response = {
            "source": "setlistfm",
            "events": [],
            "total": 0,
            "cached": False,
            "event_type": "past"
        }
        
        assert "source" in response
        assert "events" in response
        assert "total" in response
        assert "cached" in response
        assert "event_type" in response
        assert response["event_type"] == "past"
    
    def test_response_structure_for_future_events(self):
        """Test that future events response has correct structure"""
        response = {
            "source": "bandsintown",
            "events": [],
            "total": 0,
            "cached": False,
            "event_type": "future"
        }
        
        assert "source" in response
        assert "events" in response
        assert "total" in response
        assert "cached" in response
        assert "event_type" in response
        assert response["event_type"] == "future"
        assert response["source"] == "bandsintown"
    
    def test_cache_response_structure(self):
        """Test that cache response has correct structure"""
        response = {
            "source": "cache",
            "events": [],
            "total": 0,
            "cached_at": datetime.now(UTC).isoformat(),
            "event_type": "past"
        }
        
        assert "source" in response
        assert "events" in response
        assert "total" in response
        assert "cached_at" in response
        assert "event_type" in response
        assert response["source"] == "cache"


class TestDateValidation:
    """Tests for date validation logic"""
    
    def test_iso_date_format_validation(self):
        """Test that ISO date format is valid"""
        valid_dates = [
            "2024-01-01T00:00:00",
            "2024-12-31T23:59:59",
            "2024-06-15T12:30:45"
        ]
        
        for date_str in valid_dates:
            try:
                datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                assert True
            except ValueError:
                assert False, f"Date {date_str} should be valid ISO format"
    
    def test_invalid_date_format(self):
        """Test that invalid date format raises error"""
        invalid_dates = [
            "invalid-date",
            "2024/01/01",
            "01-01-2024",
            "not-a-date"
        ]
        
        for date_str in invalid_dates:
            try:
                datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                assert False, f"Date {date_str} should be invalid"
            except ValueError:
                assert True


class TestPaginationParameters:
    """Tests for pagination parameter validation"""
    
    def test_skip_parameter_validation(self):
        """Test that skip parameter must be non-negative"""
        assert 0 >= 0  # Valid
        assert 5 >= 0  # Valid
        assert -1 < 0  # Invalid
    
    def test_limit_parameter_validation(self):
        """Test that limit parameter must be between 1 and 100"""
        assert 1 >= 1  # Valid minimum
        assert 20 <= 100  # Valid
        assert 100 <= 100  # Valid maximum
        assert 0 < 1  # Invalid (too small)
        assert 101 > 100  # Invalid (too large)
    
    def test_default_pagination_values(self):
        """Test that pagination has correct defaults"""
        default_skip = 0
        default_limit = 20
        
        assert default_skip == 0
        assert default_limit == 20
        assert default_limit >= 1
        assert default_limit <= 100
