"""What does a Songkick artist page say it is about?

Reading this is more delicate than it looks, and getting it wrong is a bug in
both directions at once - so both directions are handled explicitly here.

**Reading the wrong artist.** An artist page is not about one entity. It
describes the artist, and then it describes every recommended artist, every
similar artist, every artist appearing in the photographs, and every performer
named in an upcoming gig. Songkick wraps all of that in JSON-LD, and the block
for the artist the page is *about* is not reliably the first one. Taking the
first entity block therefore reports a fact about the document rather than about
who was served, and the failure is invisible: the page loads, the answer looks
reasonable, and it belongs to somebody else.

The cure is not "read a different element". It is to demand that the statement
**names the artist being asked about**. Every source consulted below is either
matched against the artist id or is unambiguous on its own, and nothing is
accepted merely because it was first.

**Refusing a real artist.** The other direction is the one that costs the most
and is easiest to miss. Songkick does not render every artist page the same way.
Most carry an `<h1>` naming the artist; some do not - The Coronas and The
Stranglers, checked against the live site, have no `<h1>` anywhere on the page and
state their name only in structured data and in the document title. A reader that
treats the heading as mandatory does not report "this page names its artist
differently". It reports "this is not an artist page", and a real, announced,
touring artist is written off as not real.

That failure is silent in the worst way: it loses data instead of corrupting it,
so nothing downstream looks wrong. A validation rule that has only been seen
rejecting obviously-bad input has not been tested.

So the sources are consulted strongest-first, and the *first* one is not
load-bearing:

1. **The page's heading.** Unambiguous - it is the page naming itself - and the
   clearest statement of intent.
2. **The structured block that names this artist.** Matched on the id inside the
   block's own URL, so a page describing forty other acts cannot contribute the
   wrong one. This is the source that saves the artists with no heading.
3. **`og:title`, when `og:url` says the page is this artist.** Both are the
   site's own summary of the page it is on, so the pair is self-consistent.
4. **The document title, minus Songkick's decoration.** "The Coronas Tickets,
   Tour Dates & Concerts 2027 & 2026 – Songkick" is a sentence about the artist
   wearing a hat. Weakest, but the artist name is still in it, and reaching for
   it costs nothing that the stronger sources did not already establish.

`names_this_artist` is kept separate from `name` on purpose. "This page states a
name" and "this page states that name *about the artist I asked for*" are
different claims, and a caller deciding whether it has been served an artist page
needs the second one.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterator, Optional

# Structured-data types that describe a performing act.
#
# `MusicGroup` is what Songkick emits. The rest are accepted because the spec
# allows several spellings for the same thing, and refusing an artist over a
# vocabulary difference is the wrong trade.
ARTIST_TYPES = frozenset(
    {
        "musicgroup",
        "person",
        "performer",
        "musicalartist",
        "artist",
        "band",
    }
)

# Songkick's decoration on the document title.
#
# "<name> Tickets, Tour Dates & Concerts 2027 & 2026 – Songkick". Each part is
# optional, so the pattern is built from the pieces rather than as one literal:
# a page whose title omits the years, or lists only one, or says "Tour Dates"
# without "Tickets", still reduces to the artist's name. The result is only used
# if something is actually left over - if the whole title is decoration, there is
# no name in it and the caller is told so.
_TITLE_DECORATION = re.compile(
    r"""
    \s*
    (?:tickets?,?\s*)?
    (?:tour\s+dates?\s*)?
    (?:[&|]?\s*concerts?\s*)?
    (?:\d{4}(?:\s*(?:[&|,-]|\band\b)\s*\d{4})*\s*)?
    [-–—|]\s*
    songkick\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _flatten(value: Any) -> Iterator[dict]:
    """Every entity in a JSON-LD payload, whatever shape it arrives in.

    Songkick wraps its structured data in a list, sometimes a list inside that
    list, and sometimes a `@graph` — so a caller should hand over whatever the
    parser produced rather than having to know the shape.
    """

    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _flatten(item)

        return

    if not isinstance(value, dict):
        return

    graph = value.get("@graph")

    if isinstance(graph, (list, tuple)):
        for item in graph:
            yield from _flatten(item)

    yield value


def _types_of(block: dict) -> set[str]:
    declared = block.get("@type")

    values = declared if isinstance(declared, (list, tuple)) else [declared]

    return {str(value).lower() for value in values if value}


def _jsonld_blocks(soup) -> Iterator[dict]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            yield json.loads(tag.string or "")
        except (TypeError, ValueError):
            # A malformed block is not evidence about anything. Skipping it is
            # right; failing the whole page over it is not.
            continue


def _mentions_artist(block: dict, artist_id: str) -> bool:
    """Whether this structured block is about `artist_id`.

    Matched on the id inside the block's own URL rather than on its name, because
    names are not unique, are spelled inconsistently, and are exactly the thing
    under question.
    """

    url = str(block.get("url") or block.get("@id") or "")

    return f"/artists/{artist_id}" in url


def _meta(soup, key: str) -> Optional[str]:
    """A `<meta>` value by `property` or `name`."""

    for attribute in ("property", "name"):

        tag = soup.find("meta", attrs={attribute: key})

        if tag is not None:
            content = str(tag.get("content") or "").strip()

            if content:
                return content

    return None


def _name_from_structured_data(soup, artist_id: str) -> Optional[str]:
    """The name from the block that names this artist."""

    for payload in _jsonld_blocks(soup):
        for block in _flatten(payload):
            if not _types_of(block) & ARTIST_TYPES:
                continue

            if not _mentions_artist(block, artist_id):
                continue

            name = str(block.get("name") or "").strip()

            if name:
                return name

    return None


def _name_from_social_metadata(soup, artist_id: str) -> Optional[str]:
    """`og:title`, but only when `og:url` says this page is that artist.

    Both tags describe the page they are on, so the pair is self-consistent — and
    the URL is what makes it usable as identity evidence rather than as text that
    happens to be near the right answer.
    """

    url = _meta(soup, "og:url")

    if not url or f"/artists/{artist_id}" not in url:
        return None

    return _meta(soup, "og:title")


def _name_from_document_title(soup) -> Optional[str]:
    """The artist name inside the document title."""

    tag = soup.find("title")

    if tag is None:
        return None

    title = tag.get_text(strip=True)

    if not title:
        return None

    # Suffix first, then any leading "Songkick - " style prefix.
    stripped = _TITLE_DECORATION.sub("", title).strip(" -–—|").strip()

    if not stripped:
        return None

    # A title that is *only* decoration leaves the whole thing behind; if what
    # remains is indistinguishable from what was there, there is no name here.
    if stripped.casefold() == title.casefold():
        return None

    return stripped


@dataclass(frozen=True)
class ArtistPageStatement:
    """What the page states, and how firmly."""

    #: The artist's own name as the page gives it, or None if it gives none.
    name: Optional[str] = None

    #: Whether some statement on the page was explicitly about this artist.
    #:
    #: False means the name, if any, came from the weakest source - the document
    #: title - and a caller treating the page as an artist profile should weigh
    #: that accordingly. It does not mean the page is *not* an artist page: the
    #: served URL already established that it is one.
    names_this_artist: bool = False

    #: Which source decided it, so a caller can log the evidence rather than
    #: just the answer.
    source: Optional[str] = None

    def __bool__(self) -> bool:
        return bool(self.name)


def artist_page_statement(
    html: str,
    artist_id: str,
) -> ArtistPageStatement:
    """Read `artist_id`'s name from its Songkick page.

    Returns an empty statement — no name, `names_this_artist` False — for a page
    that is blank, unparseable, or states nothing that could be an artist's name.
    """

    if not html or not artist_id:
        return ArtistPageStatement()

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # 1. The page's own heading. Unambiguous, and the clearest answer to "who
    #    is this page about".
    heading = soup.select_one("h1")

    if heading is not None:
        text = heading.get_text(strip=True)

        if text:
            return ArtistPageStatement(
                name=text, names_this_artist=True, source="heading"
            )

    # 2. The structured block that names this artist. This is what saves the
    #    artists Songkick renders without a heading.
    structured = _name_from_structured_data(soup, artist_id)

    if structured:
        return ArtistPageStatement(
            name=structured,
            names_this_artist=True,
            source="structured_data",
        )

    # 3. The social card, when its URL says the page is this artist.
    social = _name_from_social_metadata(soup, artist_id)

    if social:
        return ArtistPageStatement(
            name=social, names_this_artist=True, source="og_title"
        )

    # 4. The document title. The artist name is in it under Songkick's
    #    decoration; nothing has been established by this route beyond "this page
    #    mentions an artist", which is why `names_this_artist` stays False.
    titled = _name_from_document_title(soup)

    return ArtistPageStatement(
        name=titled, names_this_artist=False, source="document_title"
    )
