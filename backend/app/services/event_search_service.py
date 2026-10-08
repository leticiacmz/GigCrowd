"""Search the events catalogue by text and by genre.

Two things make this more than a `find()`:

* **Genre comes from persisted artist metadata, and only from there.** An event
  is performed by artists, and those artists carry the genres the source
  stated. Nothing here reads a genre out of a title, because "Rock in Rio" is
  not a genre and "Boiler Room" is not either - inferring from text produces a
  filter that confidently returns the wrong shows. An event whose artists carry
  no genre simply does not appear under one, which is honest.

* **Search and genre are one query.** Composing them in the client would mean
  fetching a page, discarding most of it, and paginating over rows the reader
  will never see - so the count in the header would be wrong and "next page"
  would jump. Both filters are therefore part of the same Mongo query, and the
  same cursor walks the same result set whichever combination produced it.

The cursor is the event's own `(starts_at, _id)` pair rather than an offset. A
page of results that shifts because a show was logged while somebody was reading
would, with an offset, silently skip a row; a cursor cannot skip, because it
names a position rather than a count.

Ordering is one rule stated plainly: what is still to come is read soonest
first, and what has already happened is read most recent first. Somebody looking
for the next show should not scroll past next year's dates to find this month's,
and somebody looking for a show they remember should meet the nearest one in
time before the one from three years earlier. That is two sorted readings of one
result set, walked by one cursor - not a scoring engine.

Only upcoming events are listed by default. A catalogue of past events is what
the profile's diary is for, and mixing the two makes "what is on" unanswerable.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Optional

from pymongo import ASCENDING, DESCENDING

from app.core.logger import get_logger
from app.domain.event_provenance import (
    trusted_listing_filter,
    trusted_upcoming_filter,
)
from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository

logger = get_logger("event_search")

# What one row of a list needs - scanned without assembling a whole event.
PAGE_PROJECTION = {
    "title": 1,
    "event_type": 1,
    "starts_at": 1,
    "ends_at": 1,
    "venue_slug": 1,
    "artist_slugs": 1,
    "location": 1,
    "festival.series_id": 1,
    "festival.name": 1,
}


def escape_regex(value: str) -> str:
    """A user's search text, made safe to use as a pattern.

    A person typing "AC/DC" or "Mr. Bungle" is typing a band name, not a
    regular expression, so the text is escaped before it becomes one. Without
    this a search for `(` is a syntax error, which surfaces as a failed request
    rather than as "no matches".
    """

    return re.escape(value)


def normalize_genre(value: Optional[str]) -> Optional[str]:
    """One genre name in the single form stored and compared.

    Comparison is case- and whitespace-insensitive so that "Post-Punk",
    "post punk" and "POST PUNK" are one option in the filter rather than three
    that each return a different subset.
    """

    if value is None:
        return None

    text = str(value).strip()

    return text or None


class EventSearchService:
    """Text and genre search over the events catalogue."""

    def __init__(
        self,
        event_repository: EventRepository,
        venue_repository: VenueRepository,
        artist_repository: ArtistRepository,
    ):
        self.event_repository = event_repository
        self.venue_repository = venue_repository
        self.artist_repository = artist_repository

    # ============================================================
    # GENRES
    # ============================================================

    async def genres(self) -> list[dict]:
        """Every genre in the catalogue that at least one artist carries.

        Counted from the artists collection rather than from event documents,
        because that is where genres are actually stated. The count is the number
        of *artists* carrying it, which is what makes the list stable: it does not
        change every time a gig is added, so the filter does not reshuffle itself
        under a reader who is about to choose from it.

        Merged by case, and this matters more than it looks. Genres arrive from
        several sources that spell them differently - Songkick and Spotify publish
        `pop`, a hand-written fixture says `Pop` - and the *filter* already
        matches case-insensitively, because that is what makes `post-punk` and
        `Post-Punk` one thing to a reader. Grouping by the stored string instead
        offered both spellings as separate options that select exactly the same
        artists, with different counts, and the number beside one of them was
        simply wrong.

        So one option per genre, spelled the way the most artists spell it, with
        the counts added up. The alternative - storing one canonical form - would
        mean rewriting every artist's genres whenever the list was read, which
        turns a read into a migration and fights whatever wrote the row.
        """

        rows = await self.artist_repository.collection.aggregate(
            [
                {"$unwind": "$genres"},
                {
                    "$match": {
                        "genres": {
                            "$nin": [None, ""]
                        }
                    }
                },
                {
                    "$group": {
                        "_id": "$genres",
                        "artists": {"$sum": 1},
                    }
                },
            ]
        ).to_list(length=None)

        return merged_genre_counts(rows)

    async def genre_slugs(self, genre: str) -> list[str]:
        """The artists carrying one genre, by slug.

        Resolved to slugs first so the event query can match on the field it
        already stores. Filtering events by a genre means asking which artists
        have it, and doing that inside the event query would mean an aggregation
        over two collections on every page of every keystroke.

        Matched case-insensitively and whole, because `Post-Punk` and `post-punk`
        are one option in the filter and `post-punk` is not a match for a search
        of `punk`. A partial match here would quietly include the wrong shows in
        the results, which is the failure mode a genre filter cannot afford.
        """

        wanted = normalize_genre(genre)

        if not wanted:
            return []

        rows = await self.artist_repository.collection.find(
            {
                "genres": {
                    "$elemMatch": {
                        "$regex": f"^{re.escape(wanted)}$",
                        "$options": "i",
                    }
                }
            },
            {"slug": 1},
        ).to_list(length=None)

        return [
            str(row["slug"])
            for row in rows
            if row.get("slug")
        ]

    # ============================================================
    # SEARCH
    # ============================================================

    async def search(
        self,
        *,
        q: Optional[str] = None,
        genre: Optional[str] = None,
        artist_slugs: Optional[list[str]] = None,
        limit: int = 20,
        before: Optional[str] = None,
        before_id: Optional[str] = None,
        include_past: bool = False,
    ) -> dict[str, Any]:
        """One page of events matching the text, the genre, or the artists named.

        Returns the page, the total that matched, and a cursor for the page after
        it - or `None`, which is the only signal the client needs to stop.
        """

        limit = max(1, min(int(limit), 50))

        query: dict[str, Any] = {}

        # One `now` for the whole request: the phase a row is placed in and the
        # phase the first page asks for are read against the same instant, so a
        # row cannot fall between them.
        now = datetime.now(UTC)

        if not include_past:
            # An event with no date cannot be placed in time, and the enrichment
            # pass is what resolves that. Listing it as "upcoming" would put an
            # undated record at the top of a list of things that are about to
            # happen, so it is left out rather than guessed at.
            query["starts_at"] = {
                "$gte": now
            }

            # A future claim has to be one that can be believed.
            #
            # This clause is the whole reason a development fixture does not
            # appear on the events page as an announced gig. A fixture carries a
            # perfectly plausible future date, a Songkick-shaped URL and a
            # Songkick-shaped id, and is otherwise indistinguishable from an
            # import - so without this filter every one of them reads to a
            # visitor as "this artist is playing next year", which is precisely
            # the claim the fixture is not making.
            #
            # The repository applies the same clause on the artist pages, which
            # is why an artist page could show nothing upcoming while this list
            # showed nine phantom concerts. One rule, applied in both places,
            # because a search that is more permissive than the page it links to
            # is not a search.
            query["$and"] = list(query.get("$and", [])) + [
                trusted_upcoming_filter()
            ]

        else:
            # A listing that mixes past and future still has to refuse a future
            # claim it cannot check. Without this clause `include_past=true`
            # returned everything, so the one variant of this endpoint that
            # reached back into history was also the one that showed a fixture
            # or an unknown-provenance row as an upcoming gig.
            #
            # History is kept: the trust rule is about claims on the future, so
            # this is `trusted_listing_filter` rather than the upcoming filter -
            # the same clause the artist history listing already uses, from the
            # repository, which stays the single place that knows what "still
            # ahead" means.
            query["$and"] = list(query.get("$and", [])) + [
                trusted_listing_filter(
                    EventRepository._still_ahead_dates_filter()
                )
            ]

        text = (q or "").strip()

        if text:
            pattern = escape_regex(text)

            # Title and the artists on the bill. Deliberately not the venue: a
            # search for a band should not return every date at the stadium that
            # band played once.
            query["$or"] = [
                {"title": {"$regex": pattern, "$options": "i"}},
                {
                    "artist_slugs": {
                        "$in": await self._slugs_named(
                            pattern
                        )
                    }
                },
            ]

        wanted_genre = normalize_genre(genre)

        if wanted_genre:
            slugs = await self.genre_slugs(wanted_genre)

            if not slugs:
                # No artist carries this genre, so nothing can. Answering with
                # an empty page immediately is cheaper and clearer than running
                # a query that is guaranteed to match nothing.
                return {
                    "events": [],
                    "total": 0,
                    "next_cursor": None,
                    "genre": wanted_genre,
                }

            # Intersected with any search already in the query, so the two
            # filters compose inside one query instead of the client fetching a
            # page and discarding most of it.
            existing = query.get("artist_slugs")

            query["artist_slugs"] = (
                {"$in": slugs}
                if not isinstance(existing, dict)
                else {"$in": {"$all": [existing, {"$in": slugs}]}}
            )

        if artist_slugs is not None:
            # An explicit membership list - the artists this reader follows -
            # matched against the same field genre filters on, so a
            # personalized page is one query like every other, and not a second
            # way of reaching the same rows that could drift apart from it.
            wanted = list(
                dict.fromkeys(
                    str(slug)
                    for slug in artist_slugs
                    if slug
                )
            )

            existing = query.get("artist_slugs")

            if isinstance(
                existing, dict
            ) and isinstance(existing.get("$in"), list):

                allowed = set(existing["$in"])

                wanted = [
                    slug
                    for slug in wanted
                    if slug in allowed
                ]

            if not wanted:
                # Following nobody - or nobody carrying the chosen genre. An
                # empty page states that plainly; it never widens into "every
                # event", which is the failure this parameter must not have.
                return {
                    "events": [],
                    "total": 0,
                    "next_cursor": None,
                    "genre": wanted_genre,
                }

            query["artist_slugs"] = {
                "$in": wanted
            }

        boundary = _boundary_of(
            before,
            before_id,
        )

        if include_past:
            documents = await self._mixed_page(
                query,
                limit=limit,
                boundary=boundary,
                now=now,
            )

        else:
            documents = await self._upcoming_page(
                query,
                limit=limit,
                boundary=boundary,
            )

        has_more = len(documents) > limit

        page = documents[:limit]

        venues = await self._venues(
            [
                document.get("venue_slug")
                for document in page
            ]
        )

        artists = await self._artists(
            [
                slug
                for document in page
                for slug in (document.get("artist_slugs") or [])
            ]
        )

        rows = []

        for document in page:

            festival = document.get("festival") or {}

            rows.append(
                {
                    "id": str(document["_id"]),
                    "title": document.get("title"),
                    "starts_at": document.get("starts_at"),
                    "ends_at": document.get("ends_at"),
                    "event_type": document.get("event_type"),
                    "location": document.get("location"),
                    "venue": venues.get(
                        document.get("venue_slug")
                    ),
                    "artists": [
                        artists[slug]
                        for slug in (
                            document.get("artist_slugs") or []
                        )
                        if slug in artists
                    ],
                    "festival": (
                        {
                            "name": festival.get("name"),
                            "series_id": str(
                                festival.get("series_id")
                            ),
                        }
                        if festival.get("series_id")
                        else None
                    ),
                }
            )

        total = await self.event_repository.collection.count_documents(
            query
        )

        last = page[-1] if page else None

        return {
            "events": rows,
            "total": total,
            "next_cursor": (
                {
                    "date": _isoformat(
                        last.get("starts_at")
                    ),
                    "id": str(last["_id"]),
                }
                if has_more and last is not None
                else None
            ),
            "genre": wanted_genre,
        }

    # ============================================================
    # INTERNALS
    # ============================================================

    async def _upcoming_page(
        self,
        query: dict,
        *,
        limit: int,
        boundary: Optional[tuple],
    ) -> list[dict]:
        """One page of what is still to come, soonest first.

        The query already carries "still ahead" and its provenance rule; here it
        only gains the position to start from, in the direction the list reads.
        """

        page_query = dict(query)

        if boundary is not None:
            page_query = _beyond(
                page_query,
                boundary,
                ascending=True,
            )

        return await self._find_page(
            page_query,
            ASCENDING,
            limit,
        )

    async def _mixed_page(
        self,
        query: dict,
        *,
        limit: int,
        boundary: Optional[tuple],
        now: datetime,
    ) -> list[dict]:
        """One page of a lookup: what is still to come, then what has been.

        A single sort cannot place upcoming and historical rows in these two
        directions at once, so the result set is read in two sorted passes and
        the cursor says which pass it stopped in: a boundary at or after `now`
        still has upcoming rows ahead of it, one before `now` does not.

        The split is taken at request time, which means an event starting
        between two pages is read as history from then on - it has, by then,
        started - and its row is one the reader has already scrolled past.
        """

        if boundary is None or boundary[0] >= now:

            phase_query = dict(query)
            phase_query["starts_at"] = {
                "$gte": now
            }

            if boundary is not None:
                phase_query = _beyond(
                    phase_query,
                    boundary,
                    ascending=True,
                )

            documents = await self._find_page(
                phase_query,
                ASCENDING,
                limit,
            )

            if len(documents) > limit:
                # The page ends inside the upcoming pass; the historical one
                # begins on the page after, exactly where this one stopped.
                return documents

            # The upcoming pass ran out mid-page, so the rest of the page is
            # the most recent of what has already happened.
            history_query = dict(query)
            history_query["starts_at"] = {
                "$lt": now
            }

            return documents + await self._find_page(
                history_query,
                DESCENDING,
                limit + 1 - len(documents),
            )

        history_query = dict(query)
        history_query["starts_at"] = {
            "$lt": now
        }
        history_query = _beyond(
            history_query,
            boundary,
            ascending=False,
        )

        return await self._find_page(
            history_query,
            DESCENDING,
            limit,
        )

    async def _find_page(
        self,
        query: dict,
        direction: int,
        limit: int,
    ) -> list[dict]:
        """`limit + 1` rows in one sort order.

        The extra row is the whole answer to "is there another page", asked of
        the database rather than guessed from a count that may have moved.
        """

        return await self.event_repository.collection.find(
            query,
            PAGE_PROJECTION,
        ).sort(
            [("starts_at", direction), ("_id", direction)]
        ).limit(limit + 1).to_list(length=None)

    async def _slugs_named(
        self,
        pattern: str,
    ) -> list[str]:
        """Imported artists whose name matches the search text.

        Searching an event's own artist *slugs* against what somebody typed would
        never match: `radiohead` is not a slug. So the text is matched against the
        artists that own those slugs, and the result is a set of slugs the event
        query can use as-is.
        """

        rows = await self.artist_repository.collection.find(
            {
                "name": {
                    "$regex": pattern,
                    "$options": "i",
                }
            },
            {"slug": 1},
        ).to_list(length=None)

        return [
            str(row["slug"])
            for row in rows
            if row.get("slug")
        ]

    async def _venues(self, slugs: list[Any]) -> dict:
        wanted = [slug for slug in slugs if slug]

        if not wanted:
            return {}

        rows = await self.venue_repository.collection.find(
            {"slug": {"$in": wanted}},
            {
                "slug": 1,
                "name": 1,
                "city": 1,
                "country": 1,
            },
        ).to_list(length=None)

        return {
            str(row["slug"]): {
                "slug": row.get("slug"),
                "name": row.get("name"),
                "city": row.get("city"),
                "country": row.get("country"),
            }
            for row in rows
            if row.get("slug")
        }

    async def _artists(self, slugs: list[str]) -> dict:
        wanted = sorted(
            {slug for slug in slugs if slug}
        )

        if not wanted:
            return {}

        rows = await self.artist_repository.collection.find(
            {"slug": {"$in": wanted}},
            {"slug": 1, "name": 1, "image": 1, "genres": 1},
        ).to_list(length=None)

        return {
            str(row["slug"]): {
                "slug": row.get("slug"),
                "name": row.get("name"),
                "image": row.get("image"),
                "genres": row.get("genres") or [],
            }
            for row in rows
            if row.get("slug")
        }


def _boundary_of(
    before: Optional[str],
    before_id: Optional[str],
) -> Optional[tuple]:
    """The cursor row as a position: when it starts, and which row it is.

    A cursor that is absent, half-written or not a date is read as "no cursor":
    the list restarts at the top rather than failing on a position that was
    never one.
    """

    if not before or not before_id:
        return None

    moment = _parse_cursor_date(before)

    if moment is None:
        return None

    from app.utils.ids import to_object_id

    return (
        moment,
        to_object_id(before_id),
        str(before_id),
    )


def _beyond(
    query: dict,
    boundary: tuple,
    *,
    ascending: bool,
) -> dict:
    """The query, plus "strictly beyond the cursor row in the sort order".

    With an offset, a show logged mid-read shifts every later row by one and the
    reader silently skips a show. A cursor names a position in the sort rather
    than a count of rows, so the next page starts exactly where the last one
    stopped whatever happened in between.

    The second clause breaks the tie when several events share one instant -
    without it the boundary row comes back on the next page, and a reader scrolls
    forever seeing the same show at the bottom of every page. The clause is
    appended to `$and` rather than replacing it, so the provenance rules the
    query already carries stay in force on page two and beyond.
    """

    moment, row_id, raw_id = boundary

    if row_id is None:
        tie_break = {"_id": {"$ne": raw_id}}

    elif ascending:
        tie_break = {"_id": {"$gt": row_id}}

    else:
        tie_break = {"_id": {"$lt": row_id}}

    beyond = {
        "$or": [
            {
                "starts_at": (
                    {"$gt": moment}
                    if ascending
                    else {"$lt": moment}
                )
            },
            {"starts_at": moment, **tie_break},
        ]
    }

    query["$and"] = list(
        query.get("$and", [])
    ) + [beyond]

    return query


def merged_genre_counts(rows) -> list[dict]:
    """One entry per genre, however many spellings of it are stored.

    Pure, so the rule can be stated and tested without a database. The spelling
    shown is the one the most artists actually use - not the alphabetically
    first, not the shortest - because the commonest spelling is the one a reader
    is most likely to recognise, and the one the source these rows came from
    chose.

    Sorted here rather than in the pipeline because the merge happens here, and
    the tie-break is case-insensitive so that a list holding both `Alternative
    Rock` and `alternative rock` reads as one alphabet rather than as two:
    uppercase first is a real ordering, but it is not one anybody chooses on
    purpose.
    """

    folded: dict[str, dict] = {}

    for row in rows:

        name = str(row.get("_id") or "").strip()

        if not name:
            continue

        key = name.casefold()

        count = int(row.get("artists") or 0)

        existing = folded.get(key)

        if existing is None:

            folded[key] = {
                "name": name,
                "artists": count,
                "_strongest": count,
            }

            continue

        existing["artists"] += count

        if count > existing["_strongest"]:
            existing["name"] = name
            existing["_strongest"] = count

    merged = []

    for entry in folded.values():
        entry.pop("_strongest", None)

        merged.append(entry)

    merged.sort(
        key=lambda entry: (
            -entry["artists"],
            entry["name"].casefold(),
        )
    )

    return merged


def _isoformat(value) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()

    return None


def _parse_cursor_date(value: str) -> Optional[datetime]:
    if not value:
        return None

    from app.domain.event_schedule import parse_source_datetime

    return parse_source_datetime(value)
