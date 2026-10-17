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


@pytest.mark.asyncio
async def test_a_field_the_protection_does_not_cover_is_written_as_it_arrives():
    """Absence is only shielded for the protected fields, and the shield stops.

    The rules above protect a date, a festival, a lineup and their provenance.
    Every other field is corrected by whatever the resync states - including a
    deliberate `None`, which clears the stored value. Without this boundary the
    protection would silently freeze the whole record, and a venue, a title or
    a ticket link could never be corrected once first written.
    """

    database, repository, before = await stored_document()

    # The stored record has a ticket link; the new listing states none.
    await database["events"].update_one(
        {"external_ids.songkick": SONGKICK_ID},
        {"$set": {"ticket_url": "https://tickets.example/harvest"}},
    )

    incoming = listing_payload_dateless()
    incoming.title = "Harvest Festival 2015"
    incoming.ticket_url = None
    incoming.venue_slug = "harvest-grounds"

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    # The unprotected fields obey the incoming listing...
    assert after["title"] == "Harvest Festival 2015"
    assert after["venue_slug"] == "harvest-grounds"
    # ...including clearing: `None` here means the listing took the link back.
    assert after["ticket_url"] is None

    # While the protected date the same payload did not state still stands.
    assert after["starts_at"] == RECOVERED_START


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


@pytest.mark.asyncio
async def test_a_resync_that_states_no_festival_name_keeps_the_stored_one():
    """The block arrives whole, often with `name: None` after a refusal.

    Writing the block wholesale erased names that an earlier read had
    obtained - three Lollapalooza 2027 editions in the local database
    lost theirs to exactly this shape minutes after the refusal landed.
    Each key is therefore written under its own path only when the
    listing states it: the stored name and edition stand, while the
    series id and url the listing does state are still written.
    """

    database, repository = await identity_document()

    incoming = listing_payload_dateless()
    incoming.festival = {
        "series_id": "91231",
        "name": None,
        "url": STORED_FESTIVAL["url"],
        "edition": None,
        "artist_ids": [],
        "artists": [],
    }

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["festival"] == STORED_FESTIVAL


@pytest.mark.asyncio
async def test_a_resync_stating_a_festival_name_corrects_only_that():
    """Absence is shielded; a value the source states still lands."""

    database, repository = await identity_document()

    incoming = listing_payload_dateless()
    incoming.festival = {"name": "Harvest Festival 2015"}

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    expected = dict(STORED_FESTIVAL)
    expected["name"] = "Harvest Festival 2015"

    assert after["festival"] == expected


@pytest.mark.asyncio
async def test_an_empty_festival_block_writes_nothing_at_all():
    """A block that mentions nothing is not a correction of anything."""

    database, repository = await identity_document()

    incoming = listing_payload_dateless()
    incoming.festival = {}

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["festival"] == STORED_FESTIVAL


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


# ============================================================
# THE SOURCE ADDRESS SURVIVES A RESYNC THAT STATES NONE
# ============================================================
#
# The source block arrives whole from every parse, usually as just
# `{provider, event_id}` when the search document carried no URL. Written
# wholesale it erased the address an earlier enrichment stored - turning a
# verified future event back into one the provenance rule hides, which is
# exactly how the Lollapalooza 2027 rows went dark. It is therefore written
# key by key, like the festival block: a silence is skipped, a stated
# address still lands.


@pytest.mark.asyncio
async def test_a_resync_whose_source_states_no_address_keeps_the_stored_one():
    """The shape that erased the address: provider and id, no URL."""

    database, repository, _ = await stored_document()

    incoming = listing_payload_dateless()
    incoming.source = {
        "provider": "songkick",
        "external_id": SONGKICK_ID,
    }

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["source"]["url"] == SOURCE_URL
    assert after["source"]["provider"] == "songkick"


@pytest.mark.asyncio
async def test_a_resync_that_states_a_source_address_still_writes_it():
    """Absence is shielded; a value the source states still lands."""

    database, repository, _ = await stored_document()

    corrected = (
        "https://www.songkick.com/festivals/91231-harvest/"
        "id/23537708-harvest-festival-2015-edition"
    )

    incoming = listing_payload_dateless()
    incoming.source = {
        "provider": "songkick",
        "external_id": SONGKICK_ID,
        "url": corrected,
    }

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["source"]["url"] == corrected


# ============================================================
# THE LEGACY BANDSINTOWN PATH OBEYS THE SAME RULES
# ============================================================
#
# `update_event` is reachable only when a caller asks for the legacy provider
# explicitly, but reachable is enough: it shares `_merge_for_resync` with the
# provider path, and these tests pin that sharing so a later refactor cannot
# leave the legacy path writing a full `$set` while the provider path stays
# protected.

BANDSINTOWN_ID = "b1234"


def stored_event_bandsintown() -> dict:
    document = stored_event_with_identity()
    document["external_ids"] = {
        "songkick": SONGKICK_ID,
        "bandsintown": BANDSINTOWN_ID,
    }
    return document


def legacy_payload_dateless() -> Event:
    """The same event as a legacy listing that states neither festival nor lineup."""

    return Event(
        external_ids={
            "songkick": SONGKICK_ID,
            "bandsintown": BANDSINTOWN_ID,
        },
        artist_slugs=["alt-j"],
        artist_slug="alt-j",
        venue_slug="unknown-venue",
        title="alt-J Harvest Festival 2015",
        starts_at=None,
        ends_at=None,
        event_type="FestivalInstance",
        date_status=None,
        source={
            "provider": "bandsintown",
            "external_id": BANDSINTOWN_ID,
            "url": SOURCE_URL,
        },
    )


async def bandsintown_document():
    database = FakeDatabase({"events": [stored_event_bandsintown()]})
    repository = EventRepository(database)

    return database, repository


@pytest.mark.asyncio
async def test_a_legacy_resync_without_identity_does_not_erase_it():
    """The Bandsintown path must not blank the festival, lineup or artists."""

    database, repository = await bandsintown_document()

    await repository.update_event(legacy_payload_dateless())

    after = await database["events"].find_one(
        {"external_ids.bandsintown": BANDSINTOWN_ID}
    )

    assert after["festival"] == STORED_FESTIVAL
    assert after["lineup"] == STORED_LINEUP
    assert after["artist_slugs"] == ["alt-j", "demi-lovato"]

    # And the recovered date survives the same way it does on the provider path.
    assert after["starts_at"] == RECOVERED_START
    assert await database["events"].count_documents({}) == 1


@pytest.mark.asyncio
async def test_a_legacy_resync_that_carries_values_still_writes_them():
    """Protection is for absent values here too, not for freezing the record."""

    database, repository = await bandsintown_document()

    corrected = dict(STORED_FESTIVAL)
    corrected["name"] = "Harvest Festival 2015"

    incoming = legacy_payload_dateless()
    incoming.festival = corrected
    incoming.artist_slugs = ["alt-j", "demi-lovato", "legacy-add"]

    await repository.update_event(incoming)

    after = await database["events"].find_one(
        {"external_ids.bandsintown": BANDSINTOWN_ID}
    )

    assert after["festival"] == corrected
    # The union is additive on this path as well.
    assert after["artist_slugs"] == [
        "alt-j",
        "demi-lovato",
        "legacy-add",
    ]


@pytest.mark.asyncio
async def test_a_legacy_resync_that_states_no_festival_name_keeps_it():
    """The legacy path shares the merge; its silences are shielded too."""

    database, repository = await bandsintown_document()

    incoming = legacy_payload_dateless()
    incoming.festival = {
        "series_id": "91231",
        "name": None,
        "url": STORED_FESTIVAL["url"],
    }

    await repository.update_event(incoming)

    after = await database["events"].find_one(
        {"external_ids.bandsintown": BANDSINTOWN_ID}
    )

    assert after["festival"] == STORED_FESTIVAL


# ============================================================
# A FESTIVAL EDITION'S BILL IS NEVER SHRUNK BY A RESYNC
# ============================================================
#
# The listing a reimport carries names the appearances it holds - a
# gigography row for one artist on the bill states that artist alone - while
# the whole bill is what the edition's own page states, and that is the read
# the lineup enrichment stores. A one-name listing landing over an enriched
# bill is exactly how the 2027 Lollapalooza editions and the AMF Festival
# 2026 row were reduced to a single artist minutes after a pass had read
# their pages. A resync may therefore correct or grow a stored bill, never
# shrink it - the same stance `artist_slugs` already takes, for the same
# reason.
#
# The rule is scoped twice, and these tests pin both boundaries: it applies
# only to a festival edition, because a concert's lineup *is* its performers
# and a resync that corrects one down is taken at its word; and it only
# guards a non-empty stored value, because an empty stored bill is filled by
# whatever arrives.

ENRICHED_BILL = [
    {
        "name": "Charli XCX",
        "songkick_id": "2274326",
        "url": "https://www.songkick.com/artists/2274326-charli-xcx",
        "slug": "charli-xcx",
        "image": None,
        "genres": ["pop"],
        "order": 0,
    },
    {
        "name": "The Killers",
        "songkick_id": "11651",
        "url": "https://www.songkick.com/artists/11651-the-killers",
        "slug": "the-killers",
        "image": None,
        "genres": ["rock"],
        "order": 1,
    },
    {
        "name": "David Guetta",
        "songkick_id": "149066",
        "url": "https://www.songkick.com/artists/149066-david-guetta",
        "slug": "david-guetta",
        "image": None,
        "genres": ["electronic"],
        "order": 2,
    },
]

LOLLAPALOOZA_URL = (
    "https://www.songkick.com/festivals/1235-lollapalooza"
)


def enriched_festival_block() -> dict:
    return {
        "series_id": "1235",
        "name": "Lollapalooza",
        "url": LOLLAPALOOZA_URL,
        "edition": "2027",
        "artist_ids": ["2274326", "11651", "149066"],
        "artists": [dict(entry) for entry in ENRICHED_BILL],
    }


def stored_event_with_an_enriched_bill() -> dict:
    """An edition whose own page was read: the bill is stored in full."""

    document = stored_event()
    document["artist_slugs"] = [
        "charli-xcx",
        "the-killers",
        "david-guetta",
    ]
    document["festival"] = enriched_festival_block()
    document["lineup"] = [dict(entry) for entry in ENRICHED_BILL]

    return document


async def enriched_bill_document():
    database = FakeDatabase(
        {"events": [stored_event_with_an_enriched_bill()]}
    )
    repository = EventRepository(database)

    return database, repository


def bill_entries() -> list[LineupEntry]:
    return [
        LineupEntry(
            name=entry["name"],
            songkick_id=entry["songkick_id"],
            url=entry["url"],
            slug=entry["slug"],
            image=entry["image"],
            genres=list(entry["genres"]),
            order=entry["order"],
        )
        for entry in ENRICHED_BILL
    ]


def charli_listing() -> Event:
    """A reimport of one artist on the bill, as the listing carries it."""

    incoming = listing_payload_dateless()
    incoming.artist_slugs = ["charli-xcx"]
    incoming.lineup = [bill_entries()[0]]
    incoming.festival = {
        "series_id": "1235",
        "name": "Lollapalooza",
        "url": LOLLAPALOOZA_URL,
        "edition": "2027",
        "artist_ids": [],
        "artists": [dict(ENRICHED_BILL[0])],
    }

    return incoming


@pytest.mark.asyncio
async def test_a_one_name_resync_does_not_shrink_an_enriched_bill():
    """The incident itself: one artist reimported over a full stored bill."""

    database, repository = await enriched_bill_document()

    await repository.upsert_event_by_provider(
        charli_listing(),
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    # The stored bill - lineup and festival artists alike - stands whole.
    assert after["lineup"] == ENRICHED_BILL
    assert after["festival"]["artists"] == ENRICHED_BILL

    # While the association the listing did name merges in as always.
    assert after["artist_slugs"] == [
        "charli-xcx",
        "the-killers",
        "david-guetta",
    ]


@pytest.mark.asyncio
async def test_a_resync_naming_the_whole_bill_still_writes_it():
    """Protection is against shrinking, not for freezing the record."""

    database, repository = await identity_document()

    incoming = listing_payload_dateless()
    incoming.lineup = bill_entries()
    incoming.festival = {"artists": [dict(entry) for entry in ENRICHED_BILL]}

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["lineup"] == ENRICHED_BILL
    assert after["festival"]["artists"] == ENRICHED_BILL


@pytest.mark.asyncio
async def test_a_resync_of_an_equal_sized_bill_still_corrects_entries():
    """Only a shorter list is a silence; the same size is a correction."""

    database, repository = await enriched_bill_document()

    corrected = [
        LineupEntry(
            name="Charli XCX (US)",
            songkick_id="2274326",
            url="https://www.songkick.com/artists/2274326-charli-xcx",
            slug="charli-xcx",
            image=None,
            genres=["pop"],
            order=0,
        ),
        LineupEntry(
            name="The Killers",
            songkick_id="11651",
            url="https://www.songkick.com/artists/11651-the-killers",
            slug="the-killers",
            image=None,
            genres=["rock"],
            order=1,
        ),
        LineupEntry(
            name="David Guetta",
            songkick_id="149066",
            url="https://www.songkick.com/artists/149066-david-guetta",
            slug="david-guetta",
            image=None,
            genres=["electronic"],
            order=2,
        ),
    ]

    incoming = listing_payload_dateless()
    incoming.lineup = corrected

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["lineup"] == [
        entry.model_dump() for entry in corrected
    ]


@pytest.mark.asyncio
async def test_a_resync_fills_an_empty_festival_bill():
    """An empty stored bill is not a bill the rule protects."""

    database, repository = await identity_document()

    # The stored edition has no lineup of its own yet.
    await database["events"].update_one(
        {"external_ids.songkick": SONGKICK_ID},
        {"$set": {"lineup": []}},
    )

    incoming = listing_payload_dateless()
    incoming.lineup = [bill_entries()[0]]

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    assert after["lineup"] == [ENRICHED_BILL[0]]


@pytest.mark.asyncio
async def test_a_concert_resync_still_corrects_its_lineup_down():
    """The firewall: a concert's lineup is its performers, not a bill."""

    database, repository = await enriched_bill_document()

    await database["events"].update_one(
        {"external_ids.songkick": SONGKICK_ID},
        {"$set": {"event_type": "Concert", "festival": None}},
    )

    incoming = listing_payload_dateless()
    incoming.event_type = "Concert"
    incoming.festival = None
    incoming.lineup = [bill_entries()[0]]

    await repository.upsert_event_by_provider(
        incoming,
        "songkick",
    )

    after = await database["events"].find_one(
        {"external_ids.songkick": SONGKICK_ID}
    )

    # The shrinking correction is taken at its word on a concert.
    assert after["lineup"] == [ENRICHED_BILL[0]]
