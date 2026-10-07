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


def _comparable(actual: Any, operand: Any) -> bool:
    """Whether two values can be ordered against each other.

    `datetime` and `date` are related types but not intercomparable, and neither
    can be ordered against a string. Rather than raising, this reports the pair
    as not comparable so the caller can treat it as "does not match", which is
    what Mongo's type-bracketed comparison rules amount to in practice.
    """

    if isinstance(actual, datetime) or isinstance(operand, datetime):
        try:
            actual < operand
        except TypeError:
            return False

        return True

    if isinstance(actual, str) != isinstance(operand, str):
        return False

    return True


def matches(document: dict, query: Optional[dict]) -> bool:
    """Evaluate the supported Mongo query subset against a document.

    A key in a query is either a logical operator (`$or`, `$and`, `$nor`) or a
    field path whose value is either an equality operand or a dict of field
    operators (`$in`, `$ne`, `$exists`, `$regex`, `$not`).
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
                    # Array-aware, as Mongo is: `{"tags": {"$in": ["a"]}}`
                    # matches a document whose `tags` *contains* "a". Treating
                    # it as scalar equality would make every query that filters
                    # an array field - artist slugs, genres - silently match
                    # nothing in the double while working in production.
                    if not _in(actual if actual_found else None, operand):
                        return False
                elif field_operator == "$nin":
                    if actual_found and _in(actual, operand):
                        return False
                elif field_operator == "$ne":
                    if actual_found and actual == operand:
                        return False
                elif field_operator == "$exists":
                    if actual_found is not bool(operand):
                        return False
                elif field_operator in (
                    "$lt",
                    "$lte",
                    "$gt",
                    "$gte",
                ):
                    # Mongo orders across types; every real use here is a
                    # datetime against a datetime, and a missing field cannot
                    # satisfy a bound. Comparing only like with like keeps a
                    # mismatched pair from raising mid-test instead of failing
                    # an assertion.
                    if not actual_found or not _comparable(actual, operand):
                        return False

                    if field_operator == "$lt" and not actual < operand:
                        return False
                    if field_operator == "$lte" and not actual <= operand:
                        return False
                    if field_operator == "$gt" and not actual > operand:
                        return False
                    if field_operator == "$gte" and not actual >= operand:
                        return False
                elif field_operator == "$regex":
                    # Matched the way Mongo does with a string pattern: a
                    # `re.search`, so `^` is what makes a pattern anchored
                    # rather than every pattern silently behaving like one.
                    if not actual_found:
                        return False

                    if not _regex_matches(
                        actual, operand, value.get("$options")
                    ):
                        return False
                elif field_operator == "$options":
                    # Carried alongside `$regex`, which is where the behaviour
                    # lives. Reaching this branch alone is a malformed query.
                    continue
                elif field_operator == "$elemMatch":
                    # At least one element of the array satisfies the clause.
                    # Needed for a whole-word match inside an array of strings,
                    # which is what "this artist carries exactly this genre"
                    # is.
                    if not isinstance(actual, list):
                        return False

                    # `$options` lives *inside* the `$elemMatch` clause, as a
                    # sibling of `$regex`, not beside `$elemMatch` itself.
                    inner_options = (
                        operand.get("$options")
                        if isinstance(operand, dict)
                        else None
                    )

                    if not any(
                        matches(item, operand)
                        if isinstance(item, dict)
                        else _matches_scalar(
                            item, operand, inner_options
                        )
                        for item in actual
                    ):
                        return False
                elif field_operator == "$all":
                    if not isinstance(actual, list):
                        return False

                    for required in operand:
                        if not any(
                            matches(item, required)
                            if isinstance(item, dict)
                            else _matches_scalar(
                                item, required, value.get("$options")
                            )
                            for item in actual
                        ):
                            return False
                elif field_operator == "$not":
                    # Negated field operand, e.g. `{"$not": {"$regex": ...}}`.
                    if matches(document, {key: operand}):
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


def _in(actual: Any, operand: Any) -> bool:
    """Whether a value satisfies `$in`, with Mongo's array semantics.

    A list field matches when *any* of its elements is in the operand list; a
    scalar matches when it is. Getting this wrong is silent - a filter on an
    array field returns nothing rather than raising - so it is spelled out here.
    """

    if isinstance(actual, list):
        return any(item in operand for item in actual)

    return actual in operand


def _regex_matches(
    actual: Any,
    pattern: Any,
    options: Optional[str] = None,
) -> bool:
    """A string pattern against a stored value, honouring `$options`.

    `i` is honoured rather than ignored, because a case-insensitive whole-word
    match is exactly how a genre filter decides "the reader asked for `post-punk`
    and this artist says `Post-Punk`". Ignoring the flag would make that
    comparison fail in the double and pass in production, which is the one
    direction a test double must never lie in.
    """

    flags = re.IGNORECASE if options and "i" in options else 0

    text = actual if isinstance(actual, str) else str(actual)

    return re.search(str(pattern), text, flags) is not None


def _matches_scalar(
    value: Any,
    query: dict,
    options: Optional[str] = None,
) -> bool:
    """An operator clause applied to one array element rather than a document.

    Mongo lets `$elemMatch` hold a field query; against a bare scalar the only
    shape that means anything is a pattern, so that is what is honoured and
    anything else is refused rather than guessed at.

    `options` is threaded in from the enclosing clause because `$options` is a
    sibling of `$regex` inside `$elemMatch`, not a key of it - reading it from
    the wrong dict makes every case-insensitive pattern in an array fail here
    while passing in production.
    """

    for operator, operand in query.items():

        if operator == "$regex":
            if not _regex_matches(value, operand, options):
                return False

            continue

        if operator == "$options":
            continue

        if operator == "$eq":
            if value != operand:
                return False

            continue

        raise NotImplementedError(
            "FakeMongo cannot apply "
            f"{operator!r} to an array element"
        )

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


def _sort_key(field: str):
    """A sort key that matches Mongo's treatment of a missing field.

    Mongo sorts a missing or null field *before* every present value in ascending
    order, because null is the lowest value in its comparison order. This used to
    sort them last, which silently inverted any query whose correctness depends on
    "the rows with no timestamp come first" - a scheduled job selecting the rows
    that have waited longest would appear to work here and select the opposite rows
    against a real database.

    The presence flag is compared first so a missing field never has to be ordered
    against a real value of a different type.
    """

    def key(document: dict):
        value = document.get(field)

        return (
            value is not None,
            value,
        )

    return key


class FakeCursor:
    def __init__(self, documents: list[dict]):
        self._documents = documents
        self._sort: list[tuple[str, int]] = []
        self._skip = 0
        self._limit: Optional[int] = None

    def sort(
        self,
        field: str | list[tuple[str, int]],
        direction: int = 1,
    ) -> "FakeCursor":
        """Sort by one field, or by an ordered list of fields.

        PyMongo's cursor accepts both forms, so this does too. Supporting only the
        single-field form would mean any multi-key sort raised here while working
        against a real database - which is the worst way for a test double to lie.
        """

        if isinstance(field, list):
            self._sort.extend(field)
        else:
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
                key=_sort_key(field),
                reverse=direction < 0,
            )

        documents = documents[self._skip:]

        if self._limit is not None:
            documents = documents[: self._limit]
        elif length is not None:
            documents = documents[:length]

        return copy.deepcopy(documents)


class FakeAggregateCursor:
    """Async iterator over the result of a `$match` → `$group` pipeline."""

    def __init__(
        self,
        documents: list[dict],
        pipeline: list[dict],
    ):
        self._documents = documents
        self._pipeline = pipeline

    def __aiter__(self) -> "FakeAggregateCursor":
        return self

    async def to_list(self, length: Optional[int] = None):
        """Every row at once.

        Motor exposes this on an aggregate cursor as well as a find cursor, and a
        repository that reads its grouping in one call has to work against the
        double too - otherwise the grouping query is only ever exercised against a
        live database.
        """

        rows = _run_aggregate(
            self._documents,
            self._pipeline,
        )

        if length is not None:
            return rows[:length]

        return rows

    async def __anext__(self) -> dict:
        if not hasattr(self, "_result"):
            self._result = await self.to_list()
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

    `$match` → `$group` → `$sort` → `$limit`, which is what every grouping
    aggregation in this codebase uses. The `$sort` and `$limit` stages are
    applied because a group-by that cannot be ordered or bounded is not something
    a repository can actually ship, and a double that quietly ignored them would
    let an unsorted result pass a test that only happens to want the first row.

    `$sum: 1` counts rows. `$sum` on an expression is also supported, because the
    grouped count is stored under whatever name the caller chose and a test that
    read `.count` would be asserting on the double's naming rather than on the
    code's behaviour.
    """

    stages = list(pipeline)

    while stages and set(stages[0]) == {"$unwind"}:
        field = str(
            stages[0]["$unwind"]
        ).lstrip("$")

        unwound: list[dict] = []

        for document in documents:

            found, value = resolve_path(document, field)

            if not found:
                continue

            items = value if isinstance(value, list) else [value]

            for item in items:
                unwound.append({**document, field: item})

        documents = unwound
        stages.pop(0)

    while stages and set(stages[0]) == {"$match"}:
        documents = [
            document
            for document in documents
            if matches(document, stages[0]["$match"])
        ]

        stages.pop(0)

    if not stages or set(stages[0]) != {"$group"}:
        raise NotImplementedError(
            "FakeMongo implements $match -> $group -> $sort -> $limit, "
            f"got {[list(stage) for stage in stages]}"
        )

    group_stage = stages.pop(0)["$group"]

    accumulator_name = next(
        (
            name
            for name, field_spec in group_stage.items()
            if name != "_id" and isinstance(field_spec, dict)
        ),
        "count",
    )

    groups: dict[Any, dict] = {}

    for document in documents:

        key = _group_key(document, group_stage["_id"])

        if key is _UNGROUPABLE:
            continue

        entry = groups.setdefault(
            key,
            {"_id": key, accumulator_name: 0},
        )

        entry[accumulator_name] += 1

    rows = [groups[key] for key in groups]

    for stage in stages:

        if set(stage) == {"$sort"}:

            for field, direction in reversed(
                list(stage["$sort"].items())
            ):
                path = field.lstrip("$")

                rows.sort(
                    key=lambda document, path=path: (
                        resolve_path(document, path)[1]
                    ),
                    reverse=direction < 0,
                )

            continue

        if set(stage) == {"$limit"}:

            rows = rows[: stage["$limit"]]

            continue

        raise NotImplementedError(
            "FakeMongo implements $match, $group, $sort and $limit; "
            f"got {sorted(stage)}"
        )

    return rows


# Returned by `_group_key` for a document the grouping expression cannot place.
# Distinct from `None`, which is a legitimate group key.
_UNGROUPABLE = object()


def _group_key(document: dict, specification: Any) -> Any:
    """The group key for one document.

    Supports the two shapes this codebase groups by: a field path, and `$year` of
    a date - which is what "which years does this profile have shows in" is
    actually asking, and which cannot be answered by grouping on the raw
    datetime.
    """

    if isinstance(specification, str):
        return resolve_path(
            document, specification.lstrip("$")
        )[1]

    if isinstance(specification, dict):
        for operator, argument in specification.items():

            if operator != "$year":
                raise NotImplementedError(
                    "FakeMongo only groups by a field path or "
                    f"{{'$year': ...}}, got {operator!r}"
                )

            value = resolve_path(
                document, str(argument).lstrip("$")
            )[1]

            if not isinstance(value, datetime):
                return _UNGROUPABLE

            return value.year

    raise NotImplementedError(
        "FakeMongo does not understand this $group _id: "
        f"{specification!r}"
    )


class FakeCollection:
    def __init__(
        self,
        name: str,
        documents: Optional[list[dict]] = None,
        on_first_write=None,
    ):
        self.name = name
        self.documents: list[dict] = documents or []

        #: Called the first time a document is written.
        #:
        #: Exists because reaching a collection is not the same as it existing.
        #: In MongoDB, `database.events` hands back a handle and creates nothing;
        #: only a write creates the collection. The double keeps the same
        #: distinction, so a caller that asks which tables are present is not
        #: told about tables it merely mentioned.
        self._on_first_write = on_first_write

    def _written(self) -> None:
        if self._on_first_write is not None:
            self._on_first_write()
            self._on_first_write = None

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
        self._written()
        return InsertResult(stored["_id"])

    async def update_one(self, query: dict, update: dict) -> UpdateResult:
        for document in self.documents:
            if matches(document, query):
                before = copy.deepcopy(document)
                _apply_update(document, update)
                modified = int(before != document)
                self._written()
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

    async def delete_many(self, query: Optional[dict] = None) -> DeleteResult:
        kept = [
            document
            for document in self.documents
            if not matches(document, query)
        ]

        deleted = len(self.documents) - len(kept)

        self.documents[:] = kept

        return DeleteResult(deleted)


class FakeDatabase:
    def __init__(self, documents: Optional[dict[str, Iterable[dict]]] = None):
        self._collections: dict[str, FakeCollection] = {}

        # Which collections *exist*, as distinct from which handles have been
        # handed out. Motor does not conflate the two - `database.events` returns
        # a handle and creates nothing - and code that reads
        # `list_collection_names()` to decide whether a table is present depends
        # on the difference.
        self._existing: set[str] = set()

        for name, rows in (documents or {}).items():
            self._collections[name] = FakeCollection(
                name,
                list(rows),
                on_first_write=lambda name=name: self._existing.add(name),
            )
            self._existing.add(name)

    def __getitem__(self, name: str) -> FakeCollection:
        collection = self._collections.get(name)

        if collection is None:
            collection = FakeCollection(
                name,
                on_first_write=lambda name=name: self._existing.add(name),
            )
            self._collections[name] = collection

        return collection

    def __getattr__(self, name: str) -> FakeCollection:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __contains__(self, name: str) -> bool:
        return name in self._collections

    async def list_collection_names(self, **kwargs) -> list[str]:
        return list(self._existing)


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
