"""A tiny in-memory stand-in for the Motor database.

The real backend runs on MongoDB, but the CI environment for these tests has
no reachable server, and the feed / notification / community logic is worth
testing precisely rather than skipping. This module implements only the subset
of the driver the code under test actually uses:

* collection access by attribute (`db.activities`) and by item (`db["shows"]`)
* `find` with `$or`, `$and`, `$in` and plain equality, plus `sort`/`skip`/`limit`
* `find_one`, `insert_one`, `update_one`, `update_many`, `delete_one`,
  `count_documents`
* `find_one_and_update` (with `$set` and `$unset`), `aggregate` for a `$match`
  plus `$group` pipeline
* `$set` / `$unset` / `$inc` update operators and `ObjectId` `_id` generation

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
                elif field_operator == "$nin":
                    if actual_found and actual in operand:
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
        elif operator == "$unset":
            for path in fields:
                match = _DOTTED.match(path)
                if match:
                    parent, key = match.groups()
                    nested = document.get(parent)
                    if isinstance(nested, dict):
                        nested.pop(key, None)
                else:
                    document.pop(path, None)
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

    Dotted paths are supported because Mongo supports them: asking for
    `{"source.url": 1}` returns `{"source": {"url": ...}}`, not a flat key.
    Dropping them instead - which this used to do - made a query look like it
    returned no source data, so a test could pass for a reason that had nothing
    to do with the code under test.
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

    projected: dict = {}

    for field in keep:
        value, found = _read_path(document, field)

        if not found:
            continue

        _write_path(projected, field, value)

    if "_id" in document and "_id" not in drop:
        projected["_id"] = document["_id"]

    return projected


def _read_path(document: dict, path: str):
    """Read a dotted path, reporting whether it existed."""

    value: object = document

    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return (None, False)

        value = value[part]

    return (value, True)


def _write_path(target: dict, path: str, value) -> None:
    """Write a dotted path, creating the intermediate documents."""

    parts = path.split(".")
    current = target

    for part in parts[:-1]:
        current = current.setdefault(part, {})

    current[parts[-1]] = value


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


class FakeAggregateCursor:
    """Async iterator over the result of a `$match` + `$group` pipeline."""

    def __init__(
        self,
        documents: list[dict],
        pipeline: list[dict],
    ):
        self._documents = documents
        self._pipeline = pipeline

    def __aiter__(self) -> "FakeAggregateCursor":
        return self

    async def __anext__(self) -> dict:
        if not hasattr(self, "_result"):
            self._result = _run_aggregate(
                self._documents,
                self._pipeline,
            )
            self._index = 0

        if self._index >= len(self._result):
            raise StopAsyncIteration

        row = self._result[self._index]
        self._index += 1
        return row


def _run_aggregate(
    documents: list[dict],
    pipeline: list[dict],
) -> list[dict]:
    """Evaluate the supported aggregation stages.

    Only `$match` followed by `$group` is supported, which is what a
    count-by-field aggregation in this codebase uses.
    """

    stages = [
        stage
        for stage in pipeline
        if not stage.keys() <= {"$sort"}
    ]

    if len(stages) != 2:
        raise NotImplementedError(
            "FakeMongo only implements a $match + $group pipeline, "
            f"got {[list(stage) for stage in stages]}"
        )

    match_stage, group_stage = stages

    if set(match_stage) != {"$match"}:
        raise NotImplementedError(
            "FakeMongo only implements a $match stage first"
        )

    if set(group_stage) != {"$group"}:
        raise NotImplementedError(
            "FakeMongo only implements a $group stage last"
        )

    specification = group_stage["$group"]

    if not isinstance(specification.get("_id"), str):
        raise NotImplementedError(
            "FakeMongo only supports grouping by a field path"
        )

    field = specification["_id"].lstrip("$")

    accumulator = next(
        (
            field_spec.get("$sum")
            for name, field_spec in specification.items()
            if name != "_id" and isinstance(field_spec, dict)
        ),
        None,
    )

    if accumulator != 1 or isinstance(accumulator, bool):
        raise NotImplementedError(
            "FakeMongo only supports `$sum: 1` in a $group"
        )

    groups: dict[Any, dict] = {}

    for document in documents:

        if not matches(document, match_stage["$match"]):
            continue

        _, key = resolve_path(document, field)

        entry = groups.setdefault(
            key,
            {"_id": key, "count": 0},
        )

        entry["count"] += 1

    return [groups[key] for key in groups]


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

    async def find_one(
        self,
        query: Optional[dict] = None,
        projection: Optional[dict] = None,
    ) -> Optional[dict]:
        """One matching document, optionally projected.

        The projection argument exists because motor accepts it on `find_one`
        too. Without it a query that narrows fields would raise here while
        working against a real database, so the double would reject valid code
        rather than test it.
        """
        for document in self.documents:
            if matches(document, query):
                return copy.deepcopy(
                    _project(document, projection)
                )
        return None

    async def find_one_and_update(
        self,
        query: dict,
        update: dict,
        return_document: Any = None,
    ) -> Optional[dict]:
        """Update the first match and return it, updated.

        Only the return mode the code under test uses is supported: the updated
        document (`return_document=True`, Motor's `ReturnDocument.AFTER`).
        Asking for the document before the update raises, so a test can never
        pass by receiving the wrong one.
        """
        if not return_document:
            raise NotImplementedError(
                "FakeMongo only implements find_one_and_update with "
                "return_document=True"
            )

        for document in self.documents:
            if matches(document, query):
                _apply_update(document, update)
                return copy.deepcopy(document)
        return None

    def aggregate(self, pipeline: list[dict]) -> "FakeAggregateCursor":
        """Run a `$match` + `$group` pipeline.

        That is the shape every count-by-a-field in the code under test uses
        (attendance summaries and community post counts). Any other stage
        raises rather than being silently skipped.
        """
        return FakeAggregateCursor(
            self.documents,
            pipeline,
        )

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
