"""A resync must never erase what enrichment recovered.

The importer re-reads the same listing on every sync, and that listing can
carry no date at all even when the stored event does - the date may have
come from the event's own page during enrichment, which is a different
read of a different page. The provider update path therefore writes only
fields the incoming event actually has: a None in the payload means "this
listing said nothing", not "the date is gone".

These tests pin the overwrite rule at the repository, where it lives, so a
future refactor of the upsert cannot quietly reintroduce a full `$set`.
"""
from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.domain.event import Event
from app.repositories.event_repository import EventRepository
from tests.support.fake_mongo import FakeDatabase


SONGKICK_ID = "23537708"

SOURCE_URL = (
    "https://www.songkick.com/festivals/91231-harvest/"
    "id/23537708-harvest-festival-2015"
)

RECOVERED_START = datetime(2015, 5, 31, tzinfo=UTC)


def stored_event() -> dict:
    """An event whose date enrichment already recovered from the source page."""

    return {
        "_id": ObjectId("6ac5d823147149ffe667e9fd"),
        "external_ids": {"songkick": SONGKICK_ID},
        "artist_slugs": ["alt-j"],
        "artist_slug": "alt-j",
        "venue_slug": "unknown-venue",
        "title": "alt-J Harvest Festival 2015",
        "starts_at": RECOVERED_START,
        "ends_at": RECOVERED_START,
        "event_type": "FestivalInstance",
        "festival": None,
        "lineup": [],
        "date_status": "source",
        "location": None,
        "source": {
            "provider": "songkick",
            "external_id": SONGKICK_ID,
            "url": SOURCE_URL,
        },
        "sold_out": False,
        "free": False,
        "ticket_url": None,
        "going_count": 0,
        "maybe_count": 0,
        "went_count": 0,
        "created_at": datetime(2026, 10, 7, 5, 26, 59),
        "updated_at": datetime(2026, 10, 7, 5, 32, 0),
    }


def listing_payload_dateless() -> Event:
    """The same event as an undated gigography listing arrives it.

    No start date, no end date, no date_status: the listing states none of
    them, and the mapper leaves them unset rather than guessing.
    """

    return Event(
        external_ids={"songkick": SONGKICK_ID},
        artist_slugs=["alt-j"],
        artist_slug="alt-j",
        venue_slug="unknown-venue",
        title="alt-J Harvest Festival 2015",
        starts_at=None,
        ends_at=None,
        event_type="FestivalInstance",
        date_status=None,
        source={
            "provider": "songkick",
            "external_id": SONGKICK_ID,
            "url": SOURCE_URL,
        },
    )


async def stored_document():
    database = FakeDatabase({"events": [stored_event()]})
    repository = EventRepository(database)

    document = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    return database, repository, document


@pytest.mark.asyncio
async def test_a_resync_without_a_date_does_not_erase_a_recovered_one():
    """The case that would silently undo enrichment on every resync."""

    database, repository, before = await stored_document()

    created = await repository.upsert_event_by_provider(
        listing_payload_dateless(),
        "songkick",
    )

    # It was an update, not an insert: the event already existed.
    assert created is False

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    # The recovered date, its end and its provenance all survive.
    assert after["starts_at"] == RECOVERED_START
    assert after["ends_at"] == RECOVERED_START
    assert after["date_status"] == "source"

    # And nothing was duplicated.
    assert await database["events"].count_documents({}) == 1


@pytest.mark.asyncio
async def test_a_resync_still_delivers_values_the_source_does_state():
    """Protection is for missing values, not for freezing the record."""

    database, repository, before = await stored_document()

    corrected_start = datetime(2015, 6, 1, tzinfo=UTC)

    incoming = listing_payload_dateless()
    incoming.starts_at = corrected_start
    incoming.date_status = "source"

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    # A resync that carries a date still updates the stored one.
    assert after["starts_at"] == corrected_start
    assert after["date_status"] == "source"
