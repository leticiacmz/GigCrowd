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

        with pytest.raises(NotImplementedError):
            matches({"a": 1}, {"a": {"$regex": "b"}})


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


class TestDatabase:
    def test_attribute_and_item_access_return_the_same_collection(self):
        database = FakeDatabase()

        assert database.activities is database["activities"]

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
