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


class TestAnUndatedListingIsNotAClaimAboutTheSource:
    """The importer must not assert that a source has no date.

    An artist's gigography lists festival dates with no date on them, because the
    listing does not state one - yet each of those rows has a page of its own
    carrying the real dates. Recording `unavailable` here asserted something the
    listing cannot know, and the enrichment selector trusted it, so fifty festival
    dates whose dates were sitting on Songkick were never re-read.

    What a listing without a date establishes is that the date is *unknown*, and
    unknown is what enrichment retries.
    """

    def test_a_listing_without_a_date_leaves_the_status_unset(self):
        event, _ = SongkickEventMapper.to_domain(
            {
                "id": "39163166",
                "name": "14 Festival Se Rasgum 2019",
                "event_type": "Festival",
            },
            ["gal-costa"],
        )

        assert event.starts_at is None
        assert event.date_status is None

    def test_a_listing_with_a_date_is_still_marked_as_read_from_the_source(self):
        event, _ = SongkickEventMapper.to_domain(
            {
                "id": "39163166",
                "name": "14 Festival Se Rasgum 2019",
                "event_type": "Festival",
                "start_date": "2019-11-01",
            },
            ["gal-costa"],
        )

        assert event.date_status == "source"

    def test_a_source_that_states_unavailable_is_still_honoured(self):
        # A provider that genuinely reports the source has no date is believed.
        # Only the mapper's own guess is withdrawn.
        event, _ = SongkickEventMapper.to_domain(
            {
                "id": "39163166",
                "name": "14 Festival Se Rasgum 2019",
                "event_type": "Festival",
                "date_status": "unavailable",
            },
            ["gal-costa"],
        )

        assert event.date_status == "unavailable"

    def test_a_malformed_date_is_not_read_as_the_source_having_none(self):
        # A value the parser could not read is a parser problem, not evidence
        # about the source.
        event, _ = SongkickEventMapper.to_domain(
            {
                "id": "39163166",
                "name": "14 Festival Se Rasgum 2019",
                "event_type": "Festival",
                "date": "not-a-date",
            },
            ["gal-costa"],
        )

        assert event.starts_at is None
        assert event.date_status in (None, "parser_failed")


class TestAFestivalEditionOwnsItsOwnDates:
    """A festival's range belongs to the edition, not to the artist's set.

    A broad range such as 5-13 September describes when the festival runs. It
    does not say the artist performed on any particular day of it, so the range
    may only be stored on the edition - never narrowed onto an artist
    performance.
    """

    def test_a_festival_range_is_kept_as_the_range_it_is(self):
        event, _ = SongkickEventMapper.to_domain(
            {
                "id": "39163166",
                "name": "14 Festival Se Rasgum 2019",
                "event_type": "Festival",
                "start_date": "2019-11-01",
                "end_date": "2019-11-03",
            },
            ["gal-costa"],
        )

        assert event.starts_at is not None
        assert event.ends_at is not None
        assert event.ends_at >= event.starts_at

    def test_a_range_is_never_narrowed_to_its_first_day(self):
        event, _ = SongkickEventMapper.to_domain(
            {
                "id": "39163166",
                "name": "14 Festival Se Rasgum 2019",
                "event_type": "Festival",
                "start_date": "2019-11-01",
                "end_date": "2019-11-03",
            },
            ["gal-costa"],
        )

        assert event.ends_at is not None

        # The end is genuinely later than the start, so nothing collapsed it.
        assert event.ends_at.date() != event.starts_at.date()

    def test_a_concert_keeps_its_own_single_evening(self):
        event, _ = SongkickEventMapper.to_domain(
            {
                "id": "39163167",
                "name": "Marina Sena at Distrito Anhembi",
                "event_type": "Concert",
                "start_date": "2025-09-05",
            },
            ["marina-sena"],
        )

        assert event.starts_at is not None

        # A concert has no range, so none is invented for it.
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
