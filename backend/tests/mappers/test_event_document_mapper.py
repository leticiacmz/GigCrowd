import pytest
from app.mappers.event_document_mapper import EventDocumentMapper
from app.domain.event import Event


def test_to_domain_new_document_with_artist_slugs():
    """Test mapping new document with artist_slugs"""
    document = {
        "_id": "507f1f77bcf86cd799439011",
        "external_ids": {"songkick": "Event123"},
        "artist_slugs": ["demi-lovato", "foo-fighters"],
        "artist_slug": "demi-lovato",
        "venue_slug": "ovation-hall",
        "title": "Demi Lovato @ Ovation Hall",
        "starts_at": "2026-08-28T19:00:00Z",
        "ends_at": "2026-08-28T23:00:00Z",
        "event_type": "Concert",
        "sold_out": False,
        "free": False,
        "ticket_url": "https://example.com",
        "going_count": 10,
        "maybe_count": 5,
        "went_count": 0
    }
    
    event = EventDocumentMapper.to_domain(document)
    
    assert event.id == "507f1f77bcf86cd799439011"
    assert event.external_ids == {"songkick": "Event123"}
    assert event.artist_slugs == ["demi-lovato", "foo-fighters"]
    assert event.artist_slug == "demi-lovato"
    assert event.venue_slug == "ovation-hall"
    assert event.title == "Demi Lovato @ Ovation Hall"
    assert event.ends_at is not None
    assert event.event_type == "Concert"


def test_to_domain_old_document_only_artist_slug():
    """Test mapping old document with only artist_slug (backward compatibility)"""
    document = {
        "_id": "507f1f77bcf86cd799439011",
        "external_ids": {"bandsintown": "456"},
        "artist_slug": "demi-lovato",
        "venue_slug": "ovation-hall",
        "title": "Demi Lovato @ Ovation Hall",
        "starts_at": "2026-08-28T19:00:00Z",
        "sold_out": False,
        "free": False,
        "ticket_url": "https://example.com",
        "going_count": 10,
        "maybe_count": 5,
        "went_count": 0
    }
    
    event = EventDocumentMapper.to_domain(document)
    
    assert event.id == "507f1f77bcf86cd799439011"
    assert event.external_ids == {"bandsintown": "456"}
    # Should migrate artist_slug to artist_slugs
    assert event.artist_slugs == ["demi-lovato"]
    assert event.artist_slug == "demi-lovato"
    # Should default to Concert for event_type
    assert event.event_type == "Concert"
    # Should default to None for ends_at
    assert event.ends_at is None


def test_to_domain_old_document_empty_artist_slug():
    """Test mapping old document with empty artist_slug"""
    document = {
        "_id": "507f1f77bcf86cd799439011",
        "external_ids": {"bandsintown": "456"},
        "artist_slug": "",
        "venue_slug": "ovation-hall",
        "title": "Demi Lovato @ Ovation Hall",
        "starts_at": "2026-08-28T19:00:00Z",
        "sold_out": False,
        "free": False,
        "ticket_url": "https://example.com",
        "going_count": 10,
        "maybe_count": 5,
        "went_count": 0
    }
    
    event = EventDocumentMapper.to_domain(document)
    
    # Should migrate empty artist_slug to empty artist_slugs
    assert event.artist_slugs == []
    assert event.artist_slug == ""


def test_to_domain_document_with_optional_fields():
    """Test mapping document with optional fields missing"""
    document = {
        "_id": "507f1f77bcf86cd799439011",
        "external_ids": {},
        "artist_slugs": ["test-artist"],
        "artist_slug": "test-artist",
        "venue_slug": "test-venue",
        "title": "Test Event",
        "sold_out": False,
        "free": False,
        "going_count": 0,
        "maybe_count": 0,
        "went_count": 0
    }
    
    event = EventDocumentMapper.to_domain(document)
    
    assert event.starts_at is None
    assert event.ends_at is None
    assert event.ticket_url is None
    assert event.event_type == "Concert"  # Default
