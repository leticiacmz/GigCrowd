"""Identifier helpers shared by the repositories and services.

Historic rows in this database store identifiers inconsistently: some documents
keep them as plain strings, others as `ObjectId`. Every lookup therefore has to
match both representations, otherwise relationships silently disappear. These
helpers are the single place that knowledge lives.
"""
from typing import Any, Optional

from bson import ObjectId


def to_object_id(value: Any) -> Optional[ObjectId]:
    """Best-effort conversion of an identifier to an ObjectId."""
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def object_id_variants(value: Any) -> list[Any]:
    """Return both the string and ObjectId form of an id.

    Historic rows store identifiers inconsistently (some as strings, some as
    ObjectId), so every lookup has to match both representations.
    """
    variants: list[Any] = [value]
    oid = to_object_id(value)
    if oid is not None and oid != value:
        variants.append(oid)
    return variants


def id_matches(field: str, value: Any) -> dict:
    """Build a query matching `field` against either storage form of `value`.

    Used where a relationship is looked up by a single id, for example a
    follow between two users.
    """
    return {
        field: {
            "$in": object_id_variants(value),
        }
    }


def ids_match(field: str, values: Any) -> dict:
    """Build a query matching `field` against a set of ids in either form.

    Used where many ids are resolved at once, so the caller never has to issue
    one query per id.
    """
    variants: list[Any] = []

    for value in values or []:
        for variant in object_id_variants(value):
            if variant not in variants:
                variants.append(variant)

    return {
        field: {
            "$in": variants,
        }
    }