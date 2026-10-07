"""Which Songkick artist is this, and how do we know?

A gigography is fetched per artist, and getting that artist wrong means importing
somebody else's concerts under this artist's name. The failure is quiet: the
events import cleanly, they just belong to a different act.

Songkick publishes search results that routinely contain several acts with the
same or near-identical names, so "pick the first result whose name looks close" is
not a resolution strategy. It is a coin toss that happens to look like a
decision. This module states the two acceptable strategies instead:

1. A trusted Songkick artist ID, which is authoritative and needs no name at all.
2. Failing that, an exact match on the artist name - not a fuzzy one, and never a
   first-result fallback.

Songkick's artist URLs are `/artists/{id}-{slug}`, and the slug is decorative: a
wrong slug redirects to the right artist. That was verified against the live site,
and it is what makes strategy 1 possible - a trusted ID is enough to reach an
artist with no search involved.

Spotify IDs must never be read as Songkick IDs. A Spotify artist ID is 22
base62 characters and a Songkick artist ID is numeric, so the shapes are
distinguishable, and this module refuses the former rather than trusting the
caller to have been careful.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# A Songkick artist URL carries the numeric ID before the slug.
_ARTIST_URL_ID = re.compile(r"/artists/(\d+)(?:-|/|$)")

# Songkick artist IDs are numeric, optionally behind the "Artist" prefix that the
# site's own URLs use.
_NUMERIC_ID = re.compile(r"^(?:Artist)?(\d+)$", re.IGNORECASE)

# A Spotify artist ID is exactly 22 base62 characters.
_SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{22}$")


def looks_like_spotify_id(value: Any) -> bool:
    """Whether this identifier looks like a Spotify artist ID.

    Only the shape is judged, never the value. The point is to refuse an
    identifier that came from the wrong provider before it is used to address a
    Songkick page, where it would silently mean some other artist entirely.
    """

    if value is None:
        return False

    text = str(value).strip()

    if not text:
        return False

    if _NUMERIC_ID.match(text):
        # Numeric, so it cannot be a Spotify ID whatever else it is.
        return False

    return bool(_SPOTIFY_ID.match(text))


def normalize_songkick_artist_id(
    value: Any,
) -> Optional[str]:
    """The numeric Songkick artist ID, or None when there is not a usable one.

    Returns None rather than guessing for anything that is not recognisably a
    Songkick artist ID - a Spotify ID, an empty string, or arbitrary text. A
    caller that gets None has no trusted identity and must say so, rather than
    proceeding with an identifier that will address the wrong artist.
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    if looks_like_spotify_id(text):
        return None

    match = _NUMERIC_ID.match(text)

    if match:
        return match.group(1)

    # A Songkick artist URL is an acceptable way to name an artist.
    from_url = _ARTIST_URL_ID.search(text)

    if from_url:
        return from_url.group(1)

    return None


def artist_id_from_url(url: Any) -> Optional[str]:
    """The numeric Songkick artist ID a URL points at, if any.

    Used to check that a page actually belongs to the artist that was asked for.
    Songkick redirects a decorative slug to the canonical one, and confirming the
    ID survived that redirect is what distinguishes "resolved the right artist"
    from "resolved some artist".
    """

    if not url:
        return None

    match = _ARTIST_URL_ID.search(str(url))

    if match:
        return match.group(1)

    return None


def slug_from_artist_url(url: Any) -> Optional[str]:
    """The slug part of a Songkick artist URL, if there is one.

    Songkick redirects a wrong or missing slug to the canonical one, so the final
    URL is the authoritative spelling of an artist's slug and is worth adopting.
    """

    if not url:
        return None

    match = re.search(
        r"/artists/\d+-([^/?#]+)",
        str(url),
    )

    if match:
        return match.group(1)

    return None


def _normalized_name(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip().casefold()


def _document_of(item: Any) -> dict:
    """The artist document inside a search entry.

    Songkick's universal search wraps each result in a `document`, but some
    callers pass the document directly. Both are accepted so neither shape has to
    be special-cased by every caller.
    """

    if not isinstance(item, dict):
        return {}

    document = item.get("document")

    if isinstance(document, dict):
        return document

    return item


def resolve_artist_from_search(
    artists: list,
    *,
    artist_name: str,
    artist_id: Any = None,
) -> tuple[Optional[dict], Optional[str]]:
    """Find one artist in Songkick's search results. Returns (document, reason).

    Resolution is ID-first and never falls back to position:

    * With a trusted `artist_id`, the entry whose Songkick ID matches is the
      answer. If no entry matches, the caller may still address the artist
      directly by ID - absence from a search result is not evidence the artist
      does not exist.
    * Without one, only an exact name match counts. Near matches are rejected
      deliberately: Songkick search surfaces tribute acts, side projects and
      festival-only entries under near-identical names, and picking one of those
      is worse than reporting that the artist was not found.

    `reason` says which rule decided the outcome, so a caller can log why an
    artist was or was not resolved instead of leaving a silent mismatch behind.
    """

    trusted = normalize_songkick_artist_id(artist_id)

    exact_name: Optional[dict] = None

    for item in artists or []:

        document = _document_of(item)

        if not document:
            continue

        found_id = normalize_songkick_artist_id(
            document.get("primary_key_id")
            or document.get("id")
        )

        if trusted and found_id and found_id == trusted:
            return document, "matched_by_songkick_id"

        if (
            exact_name is None
            and _normalized_name(document.get("name"))
            == _normalized_name(artist_name)
            and artist_name
        ):
            exact_name = document

    if trusted:
        # The caller knows who it wants. Not appearing in the results is not the
        # same as not existing, so the ID is still usable.
        return None, "not_in_search_results_but_id_known"

    if exact_name is not None:
        return exact_name, "matched_by_exact_name"

    return None, "no_trusted_id_and_no_exact_name_match"