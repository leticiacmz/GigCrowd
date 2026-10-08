"""One query, answered in both of the ways this catalogue can answer it.

The application has always been able to answer two questions: "what is on" (the
events catalogue) and "who is this act" (artist discovery through Songkick).
They lived behind two boxes because they had two sources, but a reader typing
"Marina Sena" or "Mada" does not know that, and should not have to choose a
source before asking.

This is deliberately *not* a universal search engine. It carries the results of
two existing services side by side and lets the reader see which is which:

* `artists` - artist discovery, Songkick's answer, annotated with whether the
  act is already in GigCrowd (so a known act opens instead of being imported).
* `events` - the catalogue's own rows, the same rows `GET /events` returns,
  with the same cursor and the same `total`.

Nothing else is invented here. In particular there is no venue list: GigCrowd
has no venue page to open and no venue endpoint, so a venue query is answered
with whatever events mention it, and `artists_unavailable` says honestly when
the artist half could not be asked at all rather than showing an empty list
that looks like "no such artist".
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.artist_response import ArtistResponse
from app.schemas.event_search import (
    EventSearchCursor,
    EventSearchRow,
)


class UnifiedSearchResponse(BaseModel):
    """Both halves of one query, each typed by its own field."""

    query: str = Field(
        description="The query this answer belongs to."
    )

    artists: List[ArtistResponse] = Field(
        default_factory=list,
        description=(
            "Artist discovery results. Empty when the query named no act, "
            "and empty (with `artists_unavailable`) when Songkick could "
            "not be reached - two different facts, kept apart on purpose."
        ),
    )

    artists_unavailable: bool = Field(
        default=False,
        description=(
            "True when the artist half of the search was asked for and "
            "failed. The event half is unaffected: a provider outage "
            "should not blank the catalogue out of a search box."
        ),
    )

    events: List[EventSearchRow] = Field(
        default_factory=list,
        description=(
            "Catalogue rows matching the query. A row with a `festival` "
            "block is a festival edition; a row without one is a show. "
            "The type is read from the data rather than declared here."
        ),
    )

    total: int = Field(
        default=0,
        description="How many events match, over the same query as `events`."
    )

    next_cursor: Optional[EventSearchCursor] = Field(
        default=None,
        description="Where the next page of events starts, or null.",
    )

    genre: Optional[str] = Field(
        default=None,
        description="The genre filter that was applied, if any.",
    )
