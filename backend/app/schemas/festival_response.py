"""A festival as the product needs it: identity, editions and lineup.

The two levels are kept apart because they answer different questions.

`FestivalIdentityResponse` is the series: one name, one Songkick series id, one
canonical URL. It holds no dates, because no single date stands for a festival
that runs over several days.

`FestivalEventResponse` is one concrete date of that festival: its own event id,
title, date range, venue and lineup. Several of these belong to one identity,
and a page shows them as separate entries.

Both are derived from stored events. Nothing is computed from a title, and no
edition is invented: an edition exists because an imported event carries it.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.event_response import (
    EventResponse,
    LineupEntryResponse,
)


class FestivalIdentityResponse(BaseModel):
    """The festival itself: who runs it and where it lives."""

    series_id: str = Field(
        description=(
            "Songkick's identifier for the festival series. "
            "Stable across editions and the only thing two "
            "editions are matched on."
        ),
    )

    name: Optional[str] = None

    # Songkick's own page for the series, when one is known.
    url: Optional[str] = None

    # The festival's own website, when the source states one.
    official_url: Optional[str] = None

    image_url: Optional[str] = None

    edition: Optional[str] = None

    tracking_count: Optional[int] = None

    # How many concrete dates GigCrowd holds for this series.
    editions_count: int = 0

    # The union of the dates of those editions, so the header can say when the
    # festival runs without pretending any one date is the festival.
    first_date: Optional[datetime] = None

    last_date: Optional[datetime] = None


class FestivalEventResponse(BaseModel):
    """One concrete festival date."""

    event: EventResponse

    lineup: List[LineupEntryResponse] = Field(
        default_factory=list,
    )

    # Whether performers are actually held for this date. `unknown` is the
    # only honest label for an empty list when nothing recorded the work:
    # the stored record cannot say whether the source named no one, the read
    # failed, or it never ran - so the response must not present an empty
    # list as "the festival announced no one".
    #
    # A row the lineup enrichment has touched carries its own answer instead,
    # and the states keep their literal meanings: `pending` and `active` are
    # the pass working, `partial` is a finished read where some artist
    # records could not be created, `complete` is a finished pass with a
    # lineup (`ok` keeps its old spelling for it, so existing clients read
    # no change), `failed` is retryable, and `empty` is a finished pass that
    # read a page announcing no one.
    lineup_state: Literal[
        "ok",
        "unknown",
        "pending",
        "active",
        "partial",
        "failed",
        "empty",
    ] = "unknown"

    # When that state was last written, so a page can tell a worker still
    # reading from one that died mid-read and left `active` behind.
    lineup_state_updated_at: Optional[datetime] = None


class FestivalResponse(BaseModel):
    """Everything a festival page needs, in one response.

    Assembled server-side so a page costs one request rather than one per
    edition and one per artist in the lineup.
    """

    identity: FestivalIdentityResponse

    # Every concrete date held for this series, most recent first.
    editions: List[FestivalEventResponse] = Field(
        default_factory=list,
    )

    # The edition the reader arrived from, resolved to a real id so the page can
    # mark which one they are looking at.
    selected_event_id: Optional[str] = None

    # The lineup of the selected edition. Empty when nothing is stored, which
    # the `lineup_state` beside it refuses to read as an empty bill.
    lineup: List[LineupEntryResponse] = Field(
        default_factory=list,
    )

    # The selected edition's lineup state, spelled exactly as the per-edition
    # `lineup_state` above: the same record, the same meanings.
    lineup_state: Literal[
        "ok",
        "unknown",
        "pending",
        "active",
        "partial",
        "failed",
        "empty",
    ] = "unknown"

    # When that state was last written, for the same staleness reading as
    # on the editions.
    lineup_state_updated_at: Optional[datetime] = None