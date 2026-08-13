import pytest
from app.mappers.songkick_event_mapper import SongkickEventMapper
from app.domain.event import Event
from app.domain.venue import Venue


def test_to_domain_single_artist():
    """Test mapping single artist event"""
    songkick_data = {
        "id": "Event43209322",
        "name": "Demi Lovato",
        "date": "2026-08-28T00:00:00Z",
        "venue_name": "Ovation Hall",
        "city_name": "Philadelphia",
        "country_name": "US",
        "event_type": "Concert",
        "geolocation": "39.3627499,-74.4148226",
        "venue_id": 12345
    }
    
    event, venue = SongkickEventMapper.to_domain(songkick_data, ["demi-lovato"])
    
    assert isinstance(event, Event)
    assert event.artist_slugs == ["demi-lovato"]
    assert event.artist_slug == "demi-lovato"
    assert event.event_type == "Concert"
    assert event.external_ids["songkick"] == "Event43209322"
    assert event.ends_at is None
    
    assert isinstance(venue, Venue)
    assert venue.external_ids["songkick"] == "12345"
    assert venue.name == "Ovation Hall"
    assert venue.city == "Philadelphia"
    assert venue.country == "US"


def test_to_domain_festival():
    """Test mapping festival with multiple artists"""
    songkick_data = {
        "id": "Event42907787",
        "name": "Rock In Rio 2026",
        "date": "2026-09-05T00:00:00Z",
        "end_date": "2026-09-13T00:00:00Z",
        "venue_name": "Barra Olympic Park",
        "city_name": "Rio de Janeiro",
        "country_name": "Brazil",
        "event_type": "FestivalInstance",
        "geolocation": "-22.975341,-43.3944549",
        "venue_id": 67890
    }
    
    artist_slugs = ["demi-lovato", "foo-fighters", "maroon-5"]
    event, venue = SongkickEventMapper.to_domain(songkick_data, artist_slugs)
    
    assert isinstance(event, Event)
    assert event.artist_slugs == artist_slugs
    assert event.artist_slug == "demi-lovato"  # First artist for compatibility
    assert event.event_type == "FestivalInstance"
    assert event.ends_at is not None
    assert event.external_ids["songkick"] == "Event42907787"
    
    assert isinstance(venue, Venue)
    assert venue.external_ids["songkick"] == "67890"


def test_to_domain_missing_dates():
    """Test mapping with missing dates"""
    songkick_data = {
        "id": "Event123",
        "name": "Test Event",
        "venue_name": "Test Venue",
        "city_name": "Test City",
        "country_name": "US",
        "event_type": "Concert",
        "venue_id": 111
    }
    
    event, venue = SongkickEventMapper.to_domain(songkick_data, ["test-artist"])
    
    assert event.starts_at is None
    assert event.ends_at is None


def test_to_domain_malformed_date():
    """Test mapping with malformed date"""
    songkick_data = {
        "id": "Event123",
        "name": "Test Event",
        "date": "invalid-date",
        "venue_name": "Test Venue",
        "city_name": "Test City",
        "country_name": "US",
        "event_type": "Concert",
        "venue_id": 111
    }
    
    event, venue = SongkickEventMapper.to_domain(songkick_data, ["test-artist"])
    
    assert event.starts_at is None  # Should handle malformed date gracefully


def test_to_domain_missing_geolocation():
    """Test mapping with missing geolocation"""
    songkick_data = {
        "id": "Event123",
        "name": "Test Event",
        "date": "2026-08-28T00:00:00Z",
        "venue_name": "Test Venue",
        "city_name": "Test City",
        "country_name": "US",
        "event_type": "Concert",
        "venue_id": 111
    }
    
    event, venue = SongkickEventMapper.to_domain(songkick_data, ["test-artist"])
    
    assert venue.latitude is None
    assert venue.longitude is None


def test_to_domain_malformed_geolocation():
    """Test mapping with malformed geolocation"""
    songkick_data = {
        "id": "Event123",
        "name": "Test Event",
        "date": "2026-08-28T00:00:00Z",
        "venue_name": "Test Venue",
        "city_name": "Test City",
        "country_name": "US",
        "event_type": "Concert",
        "geolocation": "invalid,coordinates",
        "venue_id": 111
    }
    
    event, venue = SongkickEventMapper.to_domain(songkick_data, ["test-artist"])
    
    assert venue.latitude is None
    assert venue.longitude is None


def test_to_domain_empty_artist_slugs():
    """Test mapping with empty artist slugs"""
    songkick_data = {
        "id": "Event123",
        "name": "Test Event",
        "date": "2026-08-28T00:00:00Z",
        "venue_name": "Test Venue",
        "city_name": "Test City",
        "country_name": "US",
        "event_type": "Concert",
        "venue_id": 111
    }
    
    event, venue = SongkickEventMapper.to_domain(songkick_data, [])
    
    assert event.artist_slugs == []
    assert event.artist_slug == ""


def test_to_domain_missing_venue_id():
    """Test mapping with missing venue ID"""
    songkick_data = {
        "id": "Event123",
        "name": "Test Event",
        "date": "2026-08-28T00:00:00Z",
        "venue_name": "Test Venue",
        "city_name": "Test City",
        "country_name": "US",
        "event_type": "Concert"
    }
    
    event, venue = SongkickEventMapper.to_domain(songkick_data, ["test-artist"])
    
    assert venue.external_ids == {}  # Should be empty dict when no venue ID
