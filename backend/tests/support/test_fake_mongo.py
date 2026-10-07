"""Guard rails for the in-memory Mongo double.

A broken test double makes the tests that depend on it pass for the wrong
reason, so the matcher itself is covered directly.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Optional

import pytest
from bson import ObjectId

from tests.support.fake_mongo import FakeDatabase, matches

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class TestMatcher:
    def test_empty_query_matches_everything(self):
        assert matches({"a": 1}, None) is True
        assert matches({"a": 1}, {}) is True

    def test_equality_requires_the_field_to_exist(self):
        assert matches({"a": 1}, {"a": 1}) is True
        assert matches({"a": 1}, {"a": 2}) is False
        assert matches({}, {"a": None}) is False

    def test_dotted_path(self):
        document = {"metadata": {"artist_slug": "nova"}}

        assert matches(document, {"metadata.artist_slug": "nova"}) is True
        assert matches(document, {"metadata.artist_slug": "other"}) is False
        assert matches(document, {"metadata.missing": "nova"}) is False

    def test_in_operator(self):
        assert matches({"a": 2}, {"a": {"$in": [1, 2]}}) is True
        assert matches({"a": 3}, {"a": {"$in": [1, 2]}}) is False

    def test_or_operator(self):
        query = {"$or": [{"a": 1}, {"b": 2}]}

        assert matches({"a": 1}, query) is True
        assert matches({"b": 2}, query) is True
        assert matches({"c": 3}, query) is False

    def test_unimplemented_operator_raises(self):
        with pytest.raises(NotImplementedError):
            matches({"a": 1}, {"$where": "true"})

        # Still unsupported, so that raising remains the signal that this double
        # has drifted behind the operators production queries actually use.
        with pytest.raises(NotImplementedError):
            matches({"a": 1}, {"a": {"$mod": [2, 0]}})

    def test_comparison_operators(self):
        assert matches({"a": 5}, {"a": {"$gt": 4}}) is True
        assert matches({"a": 5}, {"a": {"$gte": 5}}) is True
        assert matches({"a": 5}, {"a": {"$lt": 6}}) is True
        assert matches({"a": 5}, {"a": {"$lte": 5}}) is True

        assert matches({"a": 5}, {"a": {"$gt": 5}}) is False
        assert matches({"a": 5}, {"a": {"$gte": 6}}) is False
        assert matches({"a": 5}, {"a": {"$lt": 5}}) is False
        assert matches({"a": 5}, {"a": {"$lte": 4}}) is False

    def test_comparison_on_a_missing_field_does_not_match(self):
        # Mongo does not satisfy a bound against an absent field.
        assert matches({}, {"a": {"$gte": 1}}) is False

    def test_comparison_between_incomparable_types_does_not_match(self):
        # Should decide rather than raise, so a type mistake surfaces as a
        # failed assertion naming the query.
        assert matches({"a": "2026-01-01"}, {"a": {"$gte": NOW}}) is False

    def test_regex_is_a_search_not_a_full_match(self):
        # Matches Mongo: unanchored, so `^` is what anchors a pattern.
        assert matches({"a": "abc9900def"}, {"a": {"$regex": "9900"}})
        assert not matches({"a": "abc"}, {"a": {"$regex": "9900"}})
        assert matches({"a": "9900abc"}, {"a": {"$regex": "^9900"}})
        assert not matches({"a": "x9900"}, {"a": {"$regex": "^9900"}})

    def test_regex_against_a_missing_field_does_not_match(self):
        assert matches({}, {"a": {"$regex": "x"}}) is False

    def test_not_negates_the_operator(self):
        assert matches({"a": "x"}, {"a": {"$not": {"$regex": "^y"}}})
        assert not matches({"a": "y"}, {"a": {"$not": {"$regex": "^y"}}})
        assert not matches({"a": "y"}, {"a": {"$not": {"$exists": True}}})


class TestCollection:
    @pytest.fixture
    def collection(self):
        database = FakeDatabase(
            {
                "items": [
                    {"_id": 1, "kind": "a", "score": 5},
                    {"_id": 2, "kind": "b", "score": 1},
                    {"_id": 3, "kind": "a", "score": 9},
                ]
            }
        )
        return database["items"]

    @pytest.mark.asyncio
    async def test_find_and_filter(self, collection):
        found = await collection.find({"kind": "a"}).to_list()

        assert [document["_id"] for document in found] == [1, 3]

    @pytest.mark.asyncio
    async def test_sort_skip_limit(self, collection):
        cursor = collection.find().sort("score", -1).skip(1).limit(1)

        found = await cursor.to_list()

        assert [document["_id"] for document in found] == [1]

    @pytest.mark.asyncio
    async def test_inclusion_projection_keeps_only_named_fields(self, collection):
        found = await collection.find(
            {"kind": "a"}, {"score": 1}
        ).to_list()

        assert all(set(document) == {"_id", "score"} for document in found)
        assert {document["score"] for document in found} == {5, 9}

    @pytest.mark.asyncio
    async def test_exclusion_projection_drops_named_fields(self, collection):
        found = await collection.find(
            {"_id": 1}, {"score": 0}
        ).to_list()

        assert set(found[0]) == {"_id", "kind"}

    @pytest.mark.asyncio
    async def test_insert_assigns_object_id(self, collection):
        result = await collection.insert_one({"kind": "c"})

        assert isinstance(result.inserted_id, ObjectId)
        assert await collection.find_one({"kind": "c"}) is not None

    @pytest.mark.asyncio
    async def test_update_one_only_touches_matches(self, collection):
        result = await collection.update_one(
            {"kind": "a"}, {"$set": {"score": 100}}
        )

        assert result.matched_count == 1

        remaining = await collection.find_one({"_id": 3})
        assert remaining["score"] == 9

    @pytest.mark.asyncio
    async def test_update_many_reports_modified_count(self, collection):
        result = await collection.update_many(
            {}, {"$set": {"seen": True}}
        )

        assert result.matched_count == 3
        assert result.modified_count == 3

    @pytest.mark.asyncio
    async def test_count_documents(self, collection):
        assert await collection.count_documents({"kind": "a"}) == 2
        assert await collection.count_documents({}) == 3

    @pytest.mark.asyncio
    async def test_reads_are_copies(self, collection):
        found = await collection.find_one({"_id": 1})
        found["score"] = 1000

        original: Optional[dict] = await collection.find_one({"_id": 1})

        assert original is not None
        assert original["score"] == 5


class TestDeletes:
    @pytest.mark.asyncio
    async def test_delete_one_removes_only_the_first_match(self):
        database = FakeDatabase(
            {
                "verdicts": [
                    {"songkick_id": "1", "valid": False},
                    {"songkick_id": "2", "valid": False},
                    {"songkick_id": "3", "valid": True},
                ]
            }
        )

        result = await database.verdicts.delete_one({"valid": False})

        assert result.deleted_count == 1

        kept = await database.verdicts.find({}).to_list(length=None)

        assert [row["songkick_id"] for row in kept] == ["2", "3"]

    @pytest.mark.asyncio
    async def test_delete_many_removes_every_match(self):
        """An audit that discards refusals needs this, and a partial
        implementation would leave the very rows it meant to clear."""

        database = FakeDatabase(
            {
                "verdicts": [
                    {"songkick_id": "1", "valid": False},
                    {"songkick_id": "2", "valid": True},
                    {"songkick_id": "3", "valid": False},
                ]
            }
        )

        result = await database.verdicts.delete_many({"valid": False})

        assert result.deleted_count == 2

        kept = await database.verdicts.find({}).to_list(length=None)

        assert [row["songkick_id"] for row in kept] == ["2"]

    @pytest.mark.asyncio
    async def test_delete_many_with_no_query_empties_the_collection(self):
        database = FakeDatabase({"verdicts": [{"_id": 1}, {"_id": 2}]})

        result = await database.verdicts.delete_many({})

        assert result.deleted_count == 2
        assert await database.verdicts.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_delete_many_reports_zero_rather_than_raising(self):
        database = FakeDatabase({"verdicts": [{"_id": 1}]})

        result = await database.verdicts.delete_many({"_id": 999})

        assert result.deleted_count == 0
        assert await database.verdicts.count_documents({}) == 1


class TestDatabase:
    def test_attribute_and_item_access_return_the_same_collection(self):
        database = FakeDatabase()

        assert database.activities is database["activities"]

    @pytest.mark.asyncio
    async def test_list_collection_names_reports_what_exists(self):
        """Scripts read this to learn which tables are present.

        It matters that a collection is *absent* rather than empty: a fresh
        database has no `artist_follows`, and a caller that assumes the table is
        there fails on exactly the deployment it was written for.
        """

        database = FakeDatabase({"artists": [], "events": []})

        names = await database.list_collection_names()

        assert set(names) == {"artists", "events"}
        assert "artist_follows" not in names

    @pytest.mark.asyncio
    async def test_reading_a_collection_does_not_make_it_exist(self):
        """`__getattr__` hands back a handle; it must not create the table.

        Otherwise asking what exists would be enough to make the answer true,
        and a caller checking for a table would find one the moment it looked.
        """

        database = FakeDatabase({"artists": []})

        _ = database.events

        assert "events" not in await database.list_collection_names()

    @pytest.mark.asyncio
    async def test_writing_to_a_collection_makes_it_exist(self):
        """The other half: reaching it is not enough, but writing is.

        A seed script that inserts into a fresh database leaves collections
        behind, and a later reader must see them.
        """

        database = FakeDatabase()

        await database.artists.insert_one({"name": "Tim Bernardes"})

        assert "artists" in await database.list_collection_names()

    @pytest.mark.asyncio
    async def test_an_empty_database_lists_nothing(self):
        assert await FakeDatabase().list_collection_names() == []

    def test_datetimes_sort(self):
        database = FakeDatabase(
            {
                "rows": [
                    {"_id": 1, "at": datetime(2026, 1, 1, tzinfo=UTC)},
                    {"_id": 2, "at": datetime(2026, 3, 1, tzinfo=UTC)},
                ]
            }
        )

        found = asyncio.run(
            database.rows.find().sort("at", -1).to_list()
        )

        assert [document["_id"] for document in found] == [2, 1]
