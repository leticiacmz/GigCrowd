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

The two levels are kept apart on purpose:

FESTIVAL IDENTITY
    The series itself: Songkick series id, canonical URL and name.

CONCRETE EVENT / EDITION
    One dated instance: its own Songkick event id, title, URL, date range,
    venue and lineup. Several of these belong to one identity.

The identity never absorbs an edition's dates and an edition never invents a
name for the series, so a festival page can list every date without any single
date pretending to be the festival as a whole.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

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


def http_url_or_none(
    value: Any,
) -> Optional[str]:
    """The value only when it is an absolute http(s) address.

    A festival identity may carry a URL from any parse that ever ran, including
    ones that stored a relative path (`/festivals/238588-...`) or a malformed
    string. The page renders this as an `<a href>` to the official site, and a
    relative path would silently become a link into GigCrowd itself while a
    `javascript:` scheme would be a hole. So a URL is exposed only in the shape
    a browser can actually open; anything else is treated as absent rather
    than repaired, because inventing a host for a path is a guess about where
    the festival lives.
    """

    if not value:
        return None

    text = str(value).strip()

    if not text:
        return None

    parsed = urlparse(text)

    if parsed.scheme in ("http", "https") and parsed.netloc:
        return text

    return None


def _artist_names(event: Any) -> list[str]:
    """The names the event's own artists are known by.

    Two sources, both already stored on the record: the lineup's stated names,
    and the artist slugs (`demi-lovato` reads as its words). The initiating
    artist of a gigography import is reliably in one of the two even when the
    lineup was never obtained, so a title shaped after that artist can be
    recognised without any external lookup.
    """

    if isinstance(event, dict):
        lineup = event.get("lineup")
        slugs = event.get("artist_slugs")
    else:
        lineup = getattr(event, "lineup", None)
        slugs = getattr(event, "artist_slugs", None)

    names: list[str] = []

    for entry in lineup or []:

        if isinstance(entry, dict):
            name = entry.get("name")
        else:
            name = getattr(entry, "name", None)

        if name:
            names.append(str(name))

    for slug in slugs or []:
        words = str(slug).replace("-", " ").strip()
        if words:
            names.append(words)

    return names


def _is_artist_prefixed(
    event: Any,
    text: Any,
) -> bool:
    """Whether text begins with the name of one of the event's own artists.

    The prefix rule only. A festival's own name may legitimately contain
    ` @ ` ("Reading Festival 2026 @ Richfield Avenue" is how Songkick names
    the edition), so the separator rule that refuses an event *title* does
    not apply to a value being considered as the festival's name.
    """

    normalized_text = _normalize(text)

    if not normalized_text:
        return False

    for name in _artist_names(event):

        normalized_name = _normalize(name)

        if not normalized_name:
            continue

        if (
            normalized_text == normalized_name
            or normalized_text.startswith(
                f"{normalized_name} "
            )
        ):
            return True

    return False


def _is_artist_shaped_title(
    event: Any,
    title: Any,
) -> bool:
    """Whether a title names an artist's appearance rather than the festival.

    Songkick addresses a festival date from the artist's own page, and the
    title it publishes there is about the artist: "Demi Lovato Rock In Rio
    2022" is how Demi Lovato's page states the show, not the festival's name,
    and "Demi Lovato @ Barra Olympic Park" is the same representation for a
    plain concert. Used as a festival's name either would introduce the artist
    as if they were the festival, so a title in one of these shapes is refused
    rather than displayed.

    Two shapes are refused, both decided from data already on the record:
    a title containing ` @ `, and a title that begins with the name of one of
    the event's own artists. Years and venue words after the name are left
    alone, so "Rock In Rio 2022" is unaffected.
    """

    text = str(title).strip()

    if not text:
        return False

    if " @ " in text:
        return True

    return _is_artist_prefixed(event, text)


def festival_name(event: Any) -> Optional[str]:
    """The name to show for an event's festival.

    The metadata's own name wins, because it was read off the festival rather
    than inferred. The event title is a fallback only, and only when it is not
    shaped after one of the event's artists: an artist-prefixed title names the
    appearance, not the festival, so this returns `None` and the caller shows a
    generic label instead of the artist's name as if it were the festival's.
    """

    metadata = festival_metadata(event)

    if metadata:

        name = metadata.get("name")

        # The metadata name wins only when it names the festival. A name
        # written from the artist's own appearance page - Songkick's artist
        # pages embed a microformat naming the date "Charli XCX @ Autódromo
        # ..." - introduces the performer as if they were the festival, so
        # it is refused here and the caller shows a generic label instead.
        if name and not _is_artist_prefixed(event, name):
            return name

    if festival_key(event):

        title = (
            event.get("title")
            if isinstance(event, dict)
            else getattr(event, "title", None)
        )

        if title and not _is_artist_shaped_title(
            event,
            title,
        ):
            return title

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


def festival_data_from_url(
    url: Any,
) -> Optional[dict[str, Any]]:
    """Read the festival series id and event id out of a Songkick URL.

    Songkick addresses a concrete festival date as
    `/festivals/{series_id}-{slug}/id/{event_id}-{slug}`, so one URL carries
    both levels: the series the festival is and the edition this date is.
    """

    if not url:
        return None

    text = str(url)

    series_match = re.search(
        r"/festivals/(\d+)(?:-[^/?#]+)?",
        text,
    )

    if not series_match:
        return None

    event_match = re.search(
        r"/id/(\d+)",
        text,
    )

    return {
        "series_id": series_match.group(1),
        "event_id": (
            event_match.group(1)
            if event_match
            else None
        ),
    }


def songkick_artist_reference(
    url: Any,
) -> tuple[Optional[str], Optional[str]]:
    """Read a Songkick artist id and slug out of an artist URL.

    Songkick addresses an artist as `/artists/{id}-{slug}`, and that URL is the
    only place the numeric id appears on a lineup entry. It is parsed here
    rather than guessed from the artist's name.

    Returns `(songkick_id, slug)`; either may be `None` when the URL does not
    carry it. Nothing is inferred when the source is silent.
    """

    if not url:
        return (None, None)

    match = re.search(
        r"/artists/(\d+)(?:-([^/?#]+))?",
        str(url),
    )

    if not match:
        return (None, None)

    return (
        match.group(1),
        match.group(2),
    )


def event_source_url(
    event: Any,
) -> Optional[str]:
    """The address the event itself was imported from.

    Provenance rather than festival metadata: every imported event records
    where it came from, and a festival date's Songkick address carries the
    series (`/festivals/{series}/id/{event}`) whether or not a festival block
    was stored beside it. An ordinary concert's address has no series segment,
    so this widens nothing for events that are not festival dates.
    """

    if isinstance(event, dict):
        source = event.get("source")
    else:
        source = getattr(event, "source", None)

    if isinstance(source, dict):
        url = source.get("url")
    else:
        url = getattr(source, "url", None)

    return str(url) if url else None


def festival_identity(
    event: Any,
) -> Optional[dict[str, Any]]:
    """The festival series an event belongs to, or `None` when it is not one.

    This is the identity half only: who runs the festival and where it lives.
    Dates, venue and lineup belong to the concrete event and are deliberately
    left out, so a page cannot mistake one night for the whole festival.

    The series id always comes from structured source data - the event's own
    metadata, or the series segment of a Songkick URL: the metadata's own URL
    first, then the event's own source address, which states the series even
    when no festival block was ever written beside the event. A name is
    carried through for display but never used to decide that two events are
    the same festival, because two festivals can share a name across cities
    and years.
    """

    metadata = festival_metadata(event)

    series_id = None
    name = None
    url = None
    official_url = None
    edition = None
    tracking = None

    if isinstance(metadata, dict):

        series_id = metadata.get("series_id")
        name = metadata.get("name")
        url = metadata.get("url")
        official_url = metadata.get("official_url")
        edition = metadata.get("edition")
        tracking = metadata.get("tracking_count")

    # The name is carried for display, and what it must never display is the
    # artist as if they were the festival. Songkick's artist pages embed a
    # microformat naming the date after the performer ("Charli XCX @
    # Autódromo ..."); a name in that shape is dropped here while the series
    # id - which came from the official address and decides the identity -
    # is kept untouched.
    if name and _is_artist_prefixed(event, name):
        name = None

    if not series_id:

        for candidate in (
            url,
            official_url,
        ):

            from_url = festival_data_from_url(
                candidate
            )

            if from_url:
                series_id = from_url.get(
                    "series_id"
                )
                break

    # The event's own address answers the case this function used to refuse:
    # an imported festival date whose festival block was never written still
    # states its series in its own Songkick URL. It is the same parse the
    # candidates above go through, so the rule remains "a series id parsed
    # from source data" - never a name, never a title, never a guess about
    # which festivals are the same. The address is remembered as the URL of
    # record so the page it powers still links back to where it came from.
    if not series_id:

        own_url = event_source_url(
            event
        )

        from_url = festival_data_from_url(
            own_url
        )

        if from_url:
            series_id = from_url.get(
                "series_id"
            )
            url = url or own_url

    if not series_id:
        return None

    # Validation happens at the point of exposure, not before the parse: a
    # stored relative path still states its series and is still structured
    # source data, but what the page renders as an "official site" link must
    # be an address a browser can open. A malformed value degrades to no link
    # rather than to a broken one.
    identity: dict[str, Any] = {
        "series_id": str(series_id),
        "name": name,
        "url": http_url_or_none(url),
        "official_url": http_url_or_none(official_url),
        "edition": edition,
    }

    if tracking is not None:
        identity["tracking_count"] = tracking

    return identity
