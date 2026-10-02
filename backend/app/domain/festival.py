"""What counts as the same festival.

A festival has many editions and one edition can span many shows, so a profile
that counted show logs would report one "festival" per ticket. Imported events
carry festival metadata in a few shapes, so identity is resolved from the
strongest signal down:

1. `festival.series_id` - the provider's identifier for the series.
2. The normalised `festival.name` - the same series imported twice.
3. The event title - for imported events with no festival metadata at all.

Years are never stripped from a title to fake a match. "Gigcrowd Fest 2025" and
"Gigcrowd Fest 2026" are adjacent editions, and collapsing them would report a
figure that does not exist.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any, Optional

from app.domain.event_schedule import as_utc

# Prefix that separates the kind of identity from its value, so a series id
# can never collide with a normalised name or a title.
SERIES_KEY_PREFIX = "series:"
NAME_KEY_PREFIX = "name:"
TITLE_KEY_PREFIX = "title:"


def _normalize(value: Any) -> str:
    """Reduce a name to a comparable form.

    Case, accents, punctuation and repeated whitespace are all noise when
    asking whether two spellings name the same festival, so "Rock in Rio" and
    "Rock In Rio!" are one festival.
    """

    if not value:
        return ""

    decomposed = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )

    cleaned = "".join(
        character if character.isalnum() else " "
        for character in without_accents.casefold()
    )

    return " ".join(cleaned.split())


def festival_metadata(event: Any) -> Optional[dict]:
    """The festival metadata of an event, if it has any."""

    if isinstance(event, dict):

        metadata = event.get("festival")

    else:

        metadata = getattr(event, "festival", None)

    if not isinstance(metadata, dict):
        return None

    return metadata


def festival_key(event: Any) -> Optional[str]:
    """The identity of the festival an event belongs to."""

    metadata = festival_metadata(event)

    if metadata:

        series_id = metadata.get("series_id")

        if series_id:
            return f"{SERIES_KEY_PREFIX}{series_id}"

        name = _normalize(metadata.get("name"))

        if name:
            return f"{NAME_KEY_PREFIX}{name}"


    title = event.get("title") if isinstance(event, dict) else getattr(
        event,
        "title",
        None,
    )

    normalized_title = _normalize(title)

    if not normalized_title:
        return None

    # Only an event that looks like a festival is identified by its own title.
    # An ordinary concert is not a festival with one edition, and treating it
    # as one would put every show on every profile in the festival count.
    if _is_festival_event(event):
        return f"{TITLE_KEY_PREFIX}{normalized_title}"


def festival_name(event: Any) -> Optional[str]:
    """The name to show for an event's festival."""

    metadata = festival_metadata(event)

    if metadata:

        name = metadata.get("name")

        if name:
            return name

    if festival_key(event):
        return (
            event.get("title")
            if isinstance(event, dict)
            else getattr(event, "title", None)
        )

    return None


def _is_festival_event(event: Any) -> bool:
    """Whether an event is itself a festival.

    `event_type` is the primary signal. `FestivalInstance` and `Festival` are
    the values the importer writes.
    """

    if isinstance(event, dict):

        event_type = event.get("event_type")

    else:

        event_type = getattr(event, "event_type", None)

    if not event_type:
        return False

    return "festival" in str(event_type).casefold()


def festival_image(event: Any) -> Optional[str]:
    """The festival's image, when the metadata carries one."""

    metadata = festival_metadata(event)

    if not metadata:
        return None

    for field in ("image_url", "image"):

        value = metadata.get(field)

        if value:
            return value

    return None


def festival_date(event: Any) -> Optional[datetime]:
    """The date the festival edition starts."""

    if isinstance(event, dict):

        starts_at = event.get("starts_at")

    else:

        starts_at = getattr(event, "starts_at", None)

    return as_utc(starts_at)
