"""The events catalogue as a searchable list.

Separate from `EventResponse` on purpose. A search result is a row: enough to
say what an event is, when it is, where it is and who is on, and no more. The
full event response carries attendance, provenance and a festival block that a
list row would never read, and assembling one per row to render twenty rows is
work nobody asked for.

The genre filter's provenance is stated in the field descriptions because it is
the part most likely to be got wrong later: genres come from artist metadata,
and never from an event's title. Titles contain places ("Rock in Rio") and
festival names as often as they contain genres, so inferring from them produces
a filter that confidently returns the wrong shows.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class EventSearchGenre(BaseModel):
    """One genre in the catalogue, with how many artists carry it."""

    name: str

    artists: int = Field(
        default=0,
        description=(
            "Artists that state this genre. Counted from artist metadata, "
            "never from event titles."
        ),
    )


class EventSearchVenue(BaseModel):
    """The place an event happens, as far as a list row needs."""

    slug: Optional[str] = None

    name: Optional[str] = None

    city: Optional[str] = None

    country: Optional[str] = None


class EventSearchArtist(BaseModel):
    """An artist performing at an event, as far as a list row needs."""

    slug: str

    name: Optional[str] = None

    image: Optional[str] = None

    genres: List[str] = Field(default_factory=list)


class EventSearchRow(BaseModel):
    """One event as a search result."""

    id: str

    title: str

    starts_at: Optional[datetime] = None

    ends_at: Optional[datetime] = None

    event_type: Optional[str] = None

    location: Optional[dict] = None

    venue: Optional[EventSearchVenue] = None

    artists: List[EventSearchArtist] = Field(
        default_factory=list
    )

    festival: Optional[dict] = None


class EventSearchCursor(BaseModel):
    """Where the next page starts.

    Opaque to the client, like every other cursor in this project: it names a
    position in the sort rather than a row count, so a show logged while
    somebody is reading cannot make the next page skip one.
    """

    date: str

    id: str


class EventSearchResponse(BaseModel):
    """One page of events, and everything needed to ask for the next."""

    events: List[EventSearchRow] = Field(
        default_factory=list
    )

    total: int = Field(
        default=0,
        description=(
            "How many events match the search and genre together. Counted "
            "over the same query the page came from, so the header figure and "
            "the list never disagree."
        ),
    )

    next_cursor: Optional[EventSearchCursor] = Field(
        default=None,
        description=(
            "Where the next page starts, or null on the last page. Null is "
            "the only signal a client needs to stop."
        ),
    )

    genre: Optional[str] = Field(
        default=None,
        description=(
            "The genre that was applied, normalised. Absent when no genre "
            "filter was asked for."
        ),
    )

    following_count: Optional[int] = Field(
        default=None,
        description=(
            "How many artists the reader follows. Only the personalized "
            "endpoint reports it, and it is reported even on an empty page: "
            "the page reads it to tell 'follows nobody' apart from 'follows "
            "nobody with no show ahead', which are two different things to "
            "say. Absent everywhere else."
        ),
    )


class EventSearchGenresResponse(BaseModel):
    """Every genre the catalogue can be filtered by."""

    genres: List[EventSearchGenre] = Field(default_factory=list)
