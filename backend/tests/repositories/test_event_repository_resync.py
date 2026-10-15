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
from app.domain.lineup import LineupEntry
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


# ============================================================
# FESTIVAL AND LINEUP SURVIVE A BARE LISTING
# ============================================================
#
# The mapper has no way to say "this listing had no lineup" other than `[]`,
# and no way to say "no festival" other than `None`. A gigography listing
# routinely carries neither while the stored event may hold both, so an empty
# incoming value has to count as absence rather than as a correction - or
# every resync would erase what the previous run recovered.

STORED_FESTIVAL = {
    "series_id": "91231",
    "name": "Harvest Festival",
    "url": "https://www.songkick.com/festivals/91231-harvest",
    "edition": "2015",
    "artist_ids": [],
    "artists": [],
}

STORED_LINEUP = [
    {
        "name": "Demi Lovato",
        "songkick_id": "520117",
        "url": "https://www.songkick.com/artists/520117-demi-lovato",
        "slug": "demi-lovato",
        "image": None,
        "genres": [],
        "order": 0,
    },
]


def stored_event_with_identity() -> dict:
    """An event whose festival block and lineup enrichment already recovered."""

    document = stored_event()
    document["artist_slugs"] = ["alt-j", "demi-lovato"]
    document["festival"] = dict(STORED_FESTIVAL)
    document["lineup"] = [dict(entry) for entry in STORED_LINEUP]

    return document


async def identity_document():
    database = FakeDatabase(
        {"events": [stored_event_with_identity()]}
    )
    repository = EventRepository(database)

    return database, repository


@pytest.mark.asyncio
async def test_a_resync_without_a_festival_block_does_not_erase_one():
    """The listing says nothing about the festival; the stored block stands."""

    database, repository = await identity_document()

    await repository.upsert_event_by_provider(
        listing_payload_dateless(),
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["festival"] == STORED_FESTIVAL


@pytest.mark.asyncio
async def test_a_resync_with_an_empty_lineup_does_not_erase_a_stored_one():
    """`[]` is how the mapper spells "no lineup stated", not "no lineup"."""

    database, repository = await identity_document()

    await repository.upsert_event_by_provider(
        listing_payload_dateless(),
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["lineup"] == STORED_LINEUP


@pytest.mark.asyncio
async def test_a_resync_that_carries_a_lineup_still_corrects_it():
    """Protection is for absent values, not for freezing the record."""

    database, repository = await identity_document()

    corrected_lineup = [
        LineupEntry(
            name="Alt-J",
            songkick_id="394516",
            url="https://www.songkick.com/artists/394516-alt-j",
            slug="alt-j",
            order=0,
        )
    ]

    incoming = listing_payload_dateless()
    incoming.lineup = corrected_lineup

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["lineup"] == [
        {
            "name": "Alt-J",
            "songkick_id": "394516",
            "url": "https://www.songkick.com/artists/394516-alt-j",
            "slug": "alt-j",
            "image": None,
            "genres": [],
            "order": 0,
        }
    ]


@pytest.mark.asyncio
async def test_a_resync_that_carries_a_festival_block_still_corrects_it():
    """A listing that does state the festival writes what it states."""

    database, repository = await identity_document()

    corrected = dict(STORED_FESTIVAL)
    corrected["name"] = "Harvest Festival 2015"

    incoming = listing_payload_dateless()
    incoming.festival = corrected

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["festival"] == corrected


# ============================================================
# ARTIST SLUGS MERGE, NEVER SHRINK
# ============================================================
#
# A gigography listing names the artist being browsed and often nobody else,
# while the stored record may hold that artist plus lineup members resolved
# on an earlier run. Replacing the list would shed those associations on
# every sync; an empty incoming list would shed all of them.


@pytest.mark.asyncio
async def test_a_resync_naming_fewer_artists_does_not_shed_the_others():
    """The incoming list is the initiating artist's; the stored set is wider."""

    database, repository = await identity_document()

    incoming = listing_payload_dateless()
    incoming.artist_slugs = ["alt-j"]

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    # Both the initiating artist and the lineup member resolved earlier are
    # still on the record.
    assert after["artist_slugs"] == ["alt-j", "demi-lovato"]


@pytest.mark.asyncio
async def test_a_resync_with_no_artists_at_all_keeps_the_stored_ones():
    """An empty incoming list must not empty the stored one."""

    database, repository = await identity_document()

    incoming = listing_payload_dateless()
    incoming.artist_slugs = []

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["artist_slugs"] == ["alt-j", "demi-lovato"]


@pytest.mark.asyncio
async def test_a_resync_adding_an_artist_grows_the_list():
    """The union is additive: a newly resolvable artist joins the record."""

    database, repository = await identity_document()

    incoming = listing_payload_dateless()
    incoming.artist_slugs = ["alt-j", "new-artist"]

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["artist_slugs"] == [
        "alt-j",
        "demi-lovato",
        "new-artist",
    ]


@pytest.mark.asyncio
async def test_an_insert_still_writes_the_incoming_artist_list():
    """The union rule is an update rule; a new event writes what it carries."""

    database = FakeDatabase({"events": []})
    repository = EventRepository(database)

    created = await repository.upsert_event_by_provider(
        listing_payload_dateless(),
        "songkick",
    )

    assert created is True

    stored = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert stored["artist_slugs"] == ["alt-j"]
