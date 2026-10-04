"""Reading an event document that was stored in an older shape.

Most events carry a structured location. One early document stored it as a bare
string, and because the domain field is typed as a mapping the whole event failed
to validate - which surfaced as a 500 on the event page and a "not found" message
to the reader, for a row that was readable the whole time.

These tests pin that a readable document always produces a readable event, and
that an unreadable field is reported as absent rather than crashing the page.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.mappers.event_document_mapper import (
    EventDocumentMapper,
)


LEGACY = {
    "_id": ObjectId("6abc0172218d4658f4b02977"),
    "title": "Rock Festival 2026",
    "date": "2026-07-15T20:00:00Z",
    "location": "Central Park, NY",
    "image_url": "https://example.com/event.jpg",
    "created_at": datetime(2026, 9, 29, 18, 20, tzinfo=UTC),
}

MODERN = {
    "_id": ObjectId("6abc0172218d4658f4b02978"),
    "title": "Arctic Monkeys Primavera Sound",
    "starts_at": datetime(2022, 10, 31, tzinfo=UTC),
    "ends_at": datetime(2022, 11, 6, tzinfo=UTC),
    "event_type": "FestivalInstance",
    "artist_slug": "arctic-monkeys",
    "location": {
        "city": "São Paulo",
        "country": "Brazil",
    },
    "lineup": [
        {
            "name": "Arctic Monkeys",
            "songkick_id": "520117",
            "order": 0,
        }
    ],
    "date_status": "source",
    "festival": {
        "series_id": "3441108",
    },
}


class TestLegacyDocuments:
    def test_a_string_location_does_not_break_the_event(self):
        """The bug: this raised, and the page answered 500."""

        event = EventDocumentMapper.to_domain(LEGACY)

        assert event.title == "Rock Festival 2026"

    def test_a_string_location_is_kept_as_the_place_name(self):
        """Readable information is kept rather than dropped."""

        event = EventDocumentMapper.to_domain(LEGACY)

        assert event.location == {
            "name": "Central Park, NY"
        }

    def test_an_event_with_no_date_still_loads(self):
        """An event the source never dated is still a real event."""

        event = EventDocumentMapper.to_domain(LEGACY)

        assert event.starts_at is None

    def test_the_missing_date_is_recorded_as_unavailable(self):
        """Rather than left unrecorded, which makes it invisible to a re-read."""

        event = EventDocumentMapper.to_domain(LEGACY)

        assert event.date_status == "unavailable"

    def test_an_artist_is_optional(self):
        event = EventDocumentMapper.to_domain(LEGACY)

        assert event.artist_slug == ""


class TestLocationShapes:
    @pytest.mark.parametrize(
        ("stored", "expected"),
        [
            (None, None),
            ({}, None),
            ("   ", None),
            ("Central Park, NY", {"name": "Central Park, NY"}),
            (
                {"city": "São Paulo"},
                {"city": "São Paulo"},
            ),
            (42, None),
            ([1, 2], None),
        ],
    )
    def test_every_stored_shape_is_handled(self, stored, expected):
        assert (
            EventDocumentMapper._read_location(stored)
            == expected
        )


class TestModernDocuments:
    def test_a_structured_location_is_passed_through(self):
        event = EventDocumentMapper.to_domain(MODERN)

        assert event.location == {
            "city": "São Paulo",
            "country": "Brazil",
        }

    def test_dates_survive(self):
        event = EventDocumentMapper.to_domain(MODERN)

        assert event.starts_at == datetime(
            2022, 10, 31, tzinfo=UTC
        )
        assert event.ends_at == datetime(
            2022, 11, 6, tzinfo=UTC
        )

    def test_the_lineup_survives(self):
        event = EventDocumentMapper.to_domain(MODERN)

        assert [
            entry.songkick_id
            for entry in event.lineup
        ] == ["520117"]

    def test_the_festival_identity_survives(self):
        event = EventDocumentMapper.to_domain(MODERN)

        assert event.festival["series_id"] == "3441108"

    def test_the_date_provenance_survives(self):
        event = EventDocumentMapper.to_domain(MODERN)

        assert event.date_status == "source"

    def test_a_dated_event_without_a_recorded_status_reads_as_sourced(self):
        """Rows imported before the field existed still report honestly."""

        document = {
            key: value
            for key, value in MODERN.items()
            if key != "date_status"
        }

        event = EventDocumentMapper.to_domain(document)

        assert event.date_status == "source"