"""A tiny in-memory stand-in for the Motor database.

The real backend runs on MongoDB, but the CI environment for these tests has
no reachable server, and the feed / notification / community logic is worth
testing precisely rather than skipping. This module implements only the subset
of the driver the code under test actually uses:

* collection access by attribute (`db.activities`) and by item (`db["shows"]`)
* `find` with `$or`, `$and`, `$in` and plain equality, plus `sort`/`skip`/`limit`
* `find_one`, `insert_one`, `update_one`, `update_many`, `delete_one`,
  `count_documents`
* `$set` update operators and `ObjectId` `_id` generation

It is intentionally not a MongoDB emulator: anything beyond the subset above
raises, so a test can never silently pass because of unimplemented behaviour.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any, Iterable, Optional

from bson import ObjectId

_DOTTED = re.compile(r"^([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)$")


def resolve_path(document: dict, path: str) -> tuple[bool, Any]:
    """Resolve a possibly dotted field path, reporting whether it exists."""
    match = _DOTTED.match(path)
    if match:
        parent, key = match.groups()
        nested = document.get(parent)
        if isinstance(nested, dict) and key in nested:
            return True, nested[key]
        return False, None

    if path in document:
        return True, document[path]

    return False, None


def matches(document: dict, query: Optional[dict]) -> bool:
    """Evaluate the supported Mongo query subset against a document.

    A key in a query is either a logical operator (`$or`, `$and`, `$nor`) or a
    field path whose value is either an equality operand or a dict of field
    operators (`$in`, `$ne`, `$exists`).
    """
    if not query:
        return True

    for key, value in query.items():
        if key == "$or":
            if not any(matches(document, clause) for clause in value):
                return False
            continue

        if key == "$and":
            if not all(matches(document, clause) for clause in value):
                return False
            continue

        if key == "$nor":
            if any(matches(document, clause) for clause in value):
                return False
            continue

        if key.startswith("$"):
            raise NotImplementedError(
                f"FakeMongo does not implement query operator {key!r}"
            )

        if isinstance(value, dict) and any(
            operator.startswith("$") for operator in value
        ):
            actual_found, actual = resolve_path(document, key)

            for field_operator, operand in value.items():
                if field_operator == "$in":
                    if not actual_found or actual not in operand:
                        return False
                elif field_operator == "$ne":
                    if actual_found and actual == operand:
                        return False
                elif field_operator == "$exists":
                    if actual_found is not bool(operand):
                        return False
                else:
                    raise NotImplementedError(
                        f"FakeMongo does not implement {field_operator!r}"
                    )
        else:
            actual_found, actual = resolve_path(document, key)
            if not actual_found or actual != value:
                return False

    return True


def _apply_update(document: dict, update: dict) -> None:
    for operator, fields in update.items():
        if operator == "$set":
            for path, value in fields.items():
                match = _DOTTED.match(path)
                if match:
                    parent, key = match.groups()
                    document.setdefault(parent, {})[key] = value
                else:
                    document[path] = value
        elif operator == "$inc":
            for path, value in fields.items():
                document[path] = document.get(path, 0) + value
        else:
            raise NotImplementedError(
                f"FakeMongo does not implement update operator {operator!r}"
            )


class UpdateResult:
    def __init__(self, matched_count: int, modified_count: int):
        self.matched_count = matched_count
        self.modified_count = modified_count


class DeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


def _project(document: dict, projection: Optional[dict]) -> dict:
    """Apply an inclusion projection the way Motor does.

    Only `{field: 1}` projections are supported, which is all the code under
    test asks for. `_id` is kept unless it is explicitly excluded.
    """
    if not projection:
        return document

    keep = {field for field, flag in projection.items() if flag}
    drop = {field for field, flag in projection.items() if not flag}

    if not keep:
        return {
            field: value
            for field, value in document.items()
            if field not in drop
        }

    projected = {
        field: value for field, value in document.items() if field in keep
    }
    if "_id" in document and "_id" not in drop:
        projected["_id"] = document["_id"]

    return projected


class FakeCursor:
    def __init__(self, documents: list[dict]):
        self._documents = documents
        self._sort: list[tuple[str, int]] = []
        self._skip = 0
        self._limit: Optional[int] = None

    def sort(self, field: str, direction: int = 1) -> "FakeCursor":
        self._sort.append((field, direction))
        return self

    def skip(self, count: int) -> "FakeCursor":
        self._skip = count
        return self

    def limit(self, count: int) -> "FakeCursor":
        self._limit = count
        return self

    async def to_list(self, length: Optional[int] = None):
        documents = self._documents

        for field, direction in reversed(self._sort):
            documents.sort(
                key=lambda document, field=field: (
                    document.get(field) is None,
                    document.get(field),
                ),
                reverse=direction < 0,
            )

        documents = documents[self._skip:]

        if self._limit is not None:
            documents = documents[: self._limit]
        elif length is not None:
            documents = documents[:length]

        return copy.deepcopy(documents)


class FakeCollection:
    def __init__(self, name: str, documents: Optional[list[dict]] = None):
        self.name = name
        self.documents: list[dict] = documents or []

    # -- reads ---------------------------------------------------------------

    def find(
        self,
        query: Optional[dict] = None,
        projection: Optional[dict] = None,
    ) -> FakeCursor:
        return FakeCursor(
            [
                _project(document, projection)
                for document in self.documents
                if matches(document, query)
            ]
        )

    async def find_one(self, query: Optional[dict] = None) -> Optional[dict]:
        for document in self.documents:
            if matches(document, query):
                return copy.deepcopy(document)
        return None

    async def count_documents(self, query: Optional[dict] = None) -> int:
        return len([document for document in self.documents if matches(document, query)])

    # -- writes --------------------------------------------------------------

    async def insert_one(self, document: dict) -> InsertResult:
        stored = copy.deepcopy(document)
        stored.setdefault("_id", ObjectId())
        self.documents.append(stored)
        return InsertResult(stored["_id"])

    async def update_one(self, query: dict, update: dict) -> UpdateResult:
        for document in self.documents:
            if matches(document, query):
                before = copy.deepcopy(document)
                _apply_update(document, update)
                modified = int(before != document)
                return UpdateResult(1, modified)
        return UpdateResult(0, 0)

    async def update_many(self, query: dict, update: dict) -> UpdateResult:
        matched = 0
        modified = 0
        for document in self.documents:
            if matches(document, query):
                matched += 1
                before = copy.deepcopy(document)
                _apply_update(document, update)
                modified += int(before != document)
        return UpdateResult(matched, modified)

    async def delete_one(self, query: dict) -> DeleteResult:
        for index, document in enumerate(self.documents):
            if matches(document, query):
                self.documents.pop(index)
                return DeleteResult(1)
        return DeleteResult(0)


class FakeDatabase:
    def __init__(self, documents: Optional[dict[str, Iterable[dict]]] = None):
        self._collections: dict[str, FakeCollection] = {}

        for name, rows in (documents or {}).items():
            self._collections[name] = FakeCollection(name, list(rows))

    def __getitem__(self, name: str) -> FakeCollection:
        return self._collections.setdefault(name, FakeCollection(name))

    def __getattr__(self, name: str) -> FakeCollection:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __contains__(self, name: str) -> bool:
        return name in self._collections


def make_user(
    user_id: str,
    username: str,
    *,
    avatar_url: Optional[str] = None,
) -> dict:
    return {
        "_id": ObjectId(user_id),
        "username": username,
        "avatar_url": avatar_url,
        "full_name": username.title(),
        "created_at": datetime(2026, 1, 1),
    }
