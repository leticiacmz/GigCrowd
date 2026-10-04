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
from typing import List, Optional

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

    # The lineup of the selected edition. Empty when that edition's source
    # named no one, which is different from a lineup that could not be read.
    lineup: List[LineupEntryResponse] = Field(
        default_factory=list,
    )