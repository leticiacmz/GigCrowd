from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.schemas.venue_response import VenueResponse


class LineupEntryResponse(BaseModel):
    """One performer on a festival event, as the client needs it.

    `songkick_id` and `slug` are what let the client decide whether an entry is
    already a GigCrowd artist or is still only a name from the source. They are
    never fabricated to make an entry look resolvable.
    """

    name: str

    songkick_id: Optional[str] = None

    slug: Optional[str] = None

    url: Optional[str] = None

    image: Optional[str] = None

    genres: List[str] = Field(
        default_factory=list,
    )

    order: int = 0

    # The GigCrowd artist page for this performer, when one exists.
    #
    # A festival announces far more artists than the catalogue has imported, so
    # most lineup entries have no page to link to. Resolving this server-side,
    # in one query for the whole lineup, is what lets the client show a real
    # link where one exists and stay quiet where it does not, instead of
    # creating an artist on the spot to make the link work.
    artist_slug: Optional[str] = None


class EventResponse(BaseModel):

    id: Optional[str] = None

    title: str

    starts_at: Optional[datetime] = None

    ends_at: Optional[datetime] = None

    # Resolved once on the server from `starts_at`/`ends_at`, because those
    # fields are optional and imported events are inconsistent about them.
    # The client must not have to re-derive "is this over?" from a date that
    # may simply be missing.
    is_past: bool = Field(
        default=False,
        description=(
            "Whether the event has already happened. False "
            "when the event carries no date."
        ),
    )

    event_type: str = "Concert"

    # How the dates above were resolved. "unavailable" means the source exposed
    # no date, which is a real state the client has to render honestly rather
    # than guessing a date of its own.
    date_status: Optional[str] = None

    ticket_url: Optional[str] = None

    free: Optional[bool] = None

    sold_out: Optional[bool] = None

    venue_slug: str

    # Venue can be missing for legacy/orphaned events.
    venue: Optional[VenueResponse] = None

    # ============================================================
    # ARTISTS
    # ============================================================

    artist_slugs: List[str] = Field(
        default_factory=list,
        description=(
            "List of artist slugs for this event "
            "(supports festivals)"
        ),
    )

    # Backward compatibility
    artist_slug: Optional[str] = Field(
        default=None,
        description=(
            "Primary artist slug "
            "(transitional field for backward compatibility)"
        ),
    )

    # ============================================================
    # FESTIVAL
    # ============================================================

    festival: Optional[dict] = Field(
        default=None,
        description=(
            "Festival metadata"
        ),
    )

    # ============================================================
    # LINEUP
    # ============================================================

    lineup: List[LineupEntryResponse] = Field(
        default_factory=list,
        description=(
            "Performers announced for this event, in source "
            "order. Empty when the source names no one."
        ),
    )

    # ============================================================
    # LOCATION
    # ============================================================

    location: Optional[dict] = Field(
        default=None,
        description=(
            "Event location metadata"
        ),
    )

    # ============================================================
    # SOURCE
    # ============================================================

    source: Optional[dict] = Field(
        default=None,
        description=(
            "Event source metadata"
        ),
    )

    # ============================================================
    # ATTENDANCE
    # ============================================================

    going_count: int = 0

    maybe_count: int = 0

    went_count: int = 0
