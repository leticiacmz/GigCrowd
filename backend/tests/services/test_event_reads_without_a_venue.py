"""An event whose venue row is missing is still an event.

The venue document is written by a lookup separate from the event's, so an
event can outlive it - or never have had one. An import that matched the
venue by name last month may not match it by id this month, an older row can
carry a slug no venue ever used, and a merge can fold two venues into one.

Reading such an event used to return nothing at all: the detail route 404'd a
record that exists, and every artist listing skipped the row. The same event
was therefore reachable by id and invisible in a list, which is a disagreement
no client can work around - and the events themselves are fine. They have a
title, a date, a lineup and, since this work, a description, a photograph and
a status.

The response schema has always modelled `venue` as optional. The service now
behaves as though it meant it, and the client is given `venue: null` to
render rather than a missing event to explain.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.services.event_service import EventService
from tests.support.fake_mongo import FakeDatabase


ARTIST_SLUG = "the-strokes"

VENUELESS_EVENT = {
    "_id": ObjectId("64b7f0c0a1b2c3d4e5f60040"),
    "title": "The Strokes at a venue nobody stored",
    "event_type": "Concert",
    "starts_at": datetime(2027, 3, 25, 19, 0, tzinfo=UTC),
    "ends_at": None,
    "date_status": "source",
    "venue_slug": "a-venue-nobody-stored",
    "artist_slugs": [ARTIST_SLUG],
    "artist_slug": ARTIST_SLUG,
    "lineup": [],
    "festival": None,
    "location": None,
    "external_ids": {"songkick": "43155855"},
    "source": {
        "provider": "songkick",
        "external_id": "43155855",
        "url": (
            "https://www.songkick.com/concerts/"
            "43155855-strokes-at-a-venue"
        ),
    },
    # The presentation fields this import now carries end to end.
    "description": "A description that reached storage.",
    "image_url": "https://images.sk-static.com/events/43155855.jpg",
    "event_status": "https://schema.org/EventScheduled",
    "sold_out": False,
    "free": False,
    "ticket_url": None,
    "going_count": 0,
    "maybe_count": 0,
    "went_count": 0,
}

DATED_EVENT = {
    "_id": ObjectId("64b7f0c0a1b2c3d4e5f60041"),
    "title": "The Strokes at The O2",
    "event_type": "Concert",
    "starts_at": datetime(2027, 4, 2, 19, 0, tzinfo=UTC),
    "ends_at": None,
    "date_status": "source",
    "venue_slug": "the-o2",
    "artist_slugs": [ARTIST_SLUG],
    "artist_slug": ARTIST_SLUG,
    "lineup": [],
    "festival": None,
    "location": {"city": "London", "country": "United Kingdom"},
    "external_ids": {"songkick": "43155856"},
    "source": {
        "provider": "songkick",
        "external_id": "43155856",
        "url": (
            "https://www.songkick.com/concerts/"
            "43155856-strokes-at-the-o2"
        ),
    },
    "description": None,
    "image_url": None,
    "event_status": None,
    "sold_out": False,
    "free": False,
    "ticket_url": None,
    "going_count": 0,
    "maybe_count": 0,
    "went_count": 0,
}

VENUE = {
    "_id": ObjectId("64b7f0c0a1b2c3d4e5f60042"),
    "name": "The O2",
    "slug": "the-o2",
    "city": "London",
    "country": "United Kingdom",
    "external_ids": {"songkick": "12345"},
}


def world() -> FakeDatabase:
    return FakeDatabase(
        {
            "events": [dict(VENUELESS_EVENT), dict(DATED_EVENT)],
            "venues": [dict(VENUE)],
            "artists": [],
        }
    )


def service(database: FakeDatabase) -> EventService:
    return EventService(
        EventRepository(database),
        VenueRepository(database),
        ArtistRepository(database),
    )


class TestAnEventWithoutAVenueRowIsStillReadable:

    @pytest.mark.asyncio
    async def test_the_event_page_loads_and_says_the_venue_is_missing(self):
        response = await service(world()).get_event(
            str(VENUELESS_EVENT["_id"])
        )

        assert response is not None
        assert response.venue is None
        assert response.venue_slug == "a-venue-nobody-stored"
        assert response.title == (
            "The Strokes at a venue nobody stored"
        )

    @pytest.mark.asyncio
    async def test_the_event_page_still_carries_its_presentation_fields(self):
        """The venue is optional; the rest of the record is not.

        These three used to be written straight onto the document by
        enrichment and never read back into the response, so a client rendered
        an event page whose description and photograph it had never been
        given.
        """

        response = await service(world()).get_event(
            str(VENUELESS_EVENT["_id"])
        )

        assert response.description == (
            "A description that reached storage."
        )
        assert response.image_url == (
            "https://images.sk-static.com/events/43155855.jpg"
        )
        assert response.event_status == (
            "https://schema.org/EventScheduled"
        )

    @pytest.mark.asyncio
    async def test_an_event_with_a_venue_still_reports_its_venue(self):
        """Only the gap became optional, not the field.

        Otherwise this change would trade one bug for its opposite and the
        venue-less read would pass by quietly dropping venues everywhere.
        """

        response = await service(world()).get_event(
            str(DATED_EVENT["_id"])
        )

        assert response.venue is not None
        assert response.venue.name == "The O2"
        assert response.venue.city == "London"

    @pytest.mark.asyncio
    async def test_a_truly_unknown_id_still_returns_nothing(self):
        """Not found stays not found; only a present record is protected."""

        assert (
            await service(world()).get_event(
                str(ObjectId("64b7f0c0a1b2c3d4e5f60099"))
            )
            is None
        )


class TestItIsNotDroppedFromTheListings:

    @pytest.mark.asyncio
    async def test_the_artist_event_list_keeps_it(self):
        responses = await service(world()).get_artist_events(
            ARTIST_SLUG
        )

        titles = [response.title for response in responses]

        assert (
            "The Strokes at a venue nobody stored" in titles
        )
        assert "The Strokes at The O2" in titles

    @pytest.mark.asyncio
    async def test_the_upcoming_list_keeps_it(self):
        responses = await service(
            world()
        ).get_upcoming_artist_events(ARTIST_SLUG)

        assert any(
            response.venue is None for response in responses
        )

    @pytest.mark.asyncio
    async def test_the_full_history_list_keeps_it(self):
        responses = await service(
            world()
        ).get_all_artist_events(ARTIST_SLUG)

        assert any(
            response.venue is None for response in responses
        )
