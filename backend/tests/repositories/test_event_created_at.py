"""`created_at` on imported events.

The Songkick import path created events with no `created_at` at all, because the
stamp lived nowhere in `Event` and `insert_event` wrote only the domain's own
fields. The consequence was not cosmetic: without it there is no way to tell a
show imported last week from one imported when the catalogue was first built, and
no way to prove which rows the read-path bug created.

The rule is small and has to hold exactly: a new event gets a stamp, and no
update ever replaces one.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.domain.event import Event
from app.repositories.event_repository import EventRepository
from tests.support.fake_mongo import FakeDatabase

BEFORE = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def an_event(**overrides) -> Event:
    values = {
        "title": "A Show",
        "venue_slug": "a-venue",
        "artist_slug": "someone",
        "artist_slugs": ["someone"],
        "starts_at": datetime(2027, 1, 1, tzinfo=UTC),
        "external_ids": {"songkick": "40352877"},
        "source": {
            "provider": "songkick",
            "url": "https://www.songkick.com/concerts/40352877",
        },
        "date_status": "source",
    }

    values.update(overrides)

    return Event(**values)


@pytest.fixture
def repository():
    database = FakeDatabase({"events": []})

    return EventRepository(database), database


class TestANewEventIsStamped:
    @pytest.mark.asyncio
    async def test_created_at_is_written_on_insert(self, repository):
        event_repository, _ = repository

        await event_repository.insert_event(an_event())

        stored = await event_repository.get_by_external_id(
            "songkick", "40352877"
        )

        assert stored is not None

        document = await _.events.find_one({})

        assert "created_at" in document

    @pytest.mark.asyncio
    async def test_the_stamp_is_a_timezone_aware_datetime(
        self, repository
    ):
        # A naive datetime read back from Mongo is ambiguous, and every other
        # timestamp in this project is written aware.
        _, database = repository

        await repository[0].insert_event(an_event())

        document = await database.events.find_one({})

        assert isinstance(document["created_at"], datetime)
        assert document["created_at"].tzinfo is not None

    @pytest.mark.asyncio
    async def test_updated_at_is_written_too(self, repository):
        _, database = repository

        await repository[0].insert_event(an_event())

        document = await database.events.find_one({})

        assert document["updated_at"] == document["created_at"]

    @pytest.mark.asyncio
    async def test_the_stamp_cannot_be_supplied_by_the_caller(self, repository):
        # `Event` has no `created_at` field, so there is no route by which a mapper
        # or a test could claim an event was imported at a moment of its choosing.
        _, database = repository

        await repository[0].insert_event(an_event())

        document = await database.events.find_one({})

        assert document["created_at"] < datetime.now(UTC) + timedelta(
            seconds=5
        )

    def test_the_domain_model_has_no_created_at_field(self):
        assert "created_at" not in Event.model_fields

    @pytest.mark.asyncio
    async def test_every_inserted_row_is_stamped(self, repository):
        # Deliberately not asserting the stamps differ: on Windows the clock
        # resolution is coarse enough that two inserts in the same tick genuinely
        # share a timestamp, and pinning that would make this test flaky for a
        # reason that has nothing to do with the behaviour under test.
        event_repository, database = repository

        await event_repository.insert_event(
            an_event(external_ids={"songkick": "1"})
        )

        await event_repository.insert_event(
            an_event(external_ids={"songkick": "2"})
        )

        documents = await database.events.find(
            {}
        ).to_list(length=10)

        assert len(documents) == 2

        for document in documents:

            assert document["created_at"] is not None


class TestAnUpdateNeverReplacesTheStamp:
    @pytest.mark.asyncio
    async def test_a_resync_preserves_created_at(self, repository):
        event_repository, database = repository

        original = datetime(2025, 3, 1, tzinfo=UTC)

        await event_repository.insert_event(an_event())

        first = await database.events.find_one({})

        # Backdate it, so a re-stamp would be obvious rather than coincidental.
        await database.events.update_one(
            {"_id": first["_id"]}, {"$set": {"created_at": original}}
        )

        await event_repository.update_event_by_provider(
            an_event(title="A Renamed Show"),
            "songkick",
        )

        after = await database.events.find_one({})

        assert after["created_at"] == original
        assert after["title"] == "A Renamed Show"

    @pytest.mark.asyncio
    async def test_a_resync_does_move_updated_at(self, repository):
        # The pair has to mean something: a resync records that the data was read
        # again, without pretending the event is new.
        event_repository, database = repository

        await event_repository.insert_event(an_event())

        first = await database.events.find_one({})

        await database.events.update_one(
            {"_id": first["_id"]},
            {"$set": {"updated_at": datetime(2020, 1, 1, tzinfo=UTC)}},
        )

        await event_repository.update_event_by_provider(
            an_event(title="A Renamed Show"), "songkick"
        )

        after = await database.events.find_one({})

        assert after["updated_at"] > datetime(2020, 1, 1, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_the_upsert_creates_once_then_preserves(self, repository):
        # The path the importer actually uses. Second time round it must update
        # rather than insert, and must not restamp.
        event_repository, database = repository

        created = await event_repository.upsert_event_by_provider(
            an_event(), "songkick"
        )

        first = await database.events.find_one({})

        again = await event_repository.upsert_event_by_provider(
            an_event(title="Renamed"), "songkick"
        )

        after = await database.events.find_one({})

        assert created is True
        assert again is False
        assert after["created_at"] == first["created_at"]
        assert after["title"] == "Renamed"

        assert await database.events.count_documents({}) == 1

    @pytest.mark.asyncio
    async def test_the_legacy_bandsintown_update_preserves_it(
        self, repository
    ):
        # The legacy path is still reachable, so it has to obey the same rule.
        event_repository, database = repository

        await event_repository.insert_event(
            an_event(external_ids={"bandsintown": "12345"})
        )

        original = datetime(2024, 6, 1, tzinfo=UTC)

        first = await database.events.find_one({})

        await database.events.update_one(
            {"_id": first["_id"]}, {"$set": {"created_at": original}}
        )

        await event_repository.update_event(
            an_event(
                title="Legacy Show",
                external_ids={"bandsintown": "12345"},
            )
        )

        after = await database.events.find_one({})

        assert after["created_at"] == original

    @pytest.mark.asyncio
    async def test_an_update_does_not_invent_a_stamp(self, repository):
        # An event that predates this fix has no `created_at`. Updating it must
        # not fabricate one that implies it was first imported just now.
        event_repository, database = repository

        await event_repository.insert_event(an_event())

        first = await database.events.find_one({})

        await database.events.update_one(
            {"_id": first["_id"]}, {"$unset": {"created_at": ""}}
        )

        await event_repository.update_event_by_provider(
            an_event(title="Touched"), "songkick"
        )

        after = await database.events.find_one({})

        assert "created_at" not in after


class TestTheStampDoesNotLeakIntoResponses:
    def test_the_mapper_ignores_an_unknown_stamp(self):
        # Documents already in the database may or may not carry the field, and
        # every existing row must keep mapping to a valid `Event`.
        from app.mappers.event_document_mapper import (
            EventDocumentMapper,
        )

        document = {
            "_id": ObjectId("650000000000000000000001"),
            "title": "A Show",
            "venue_slug": "a-venue",
            "artist_slug": "someone",
            "artist_slugs": ["someone"],
            "starts_at": datetime(2027, 1, 1, tzinfo=UTC),
            "ends_at": None,
            "external_ids": {"songkick": "1"},
            "source": None,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
        }

        event = EventDocumentMapper.to_domain(document)

        assert event.title == "A Show"