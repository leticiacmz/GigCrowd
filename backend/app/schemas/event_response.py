from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.schemas.venue_response import VenueResponse


class EventResponse(BaseModel):

    id: Optional[str] = None

    title: str

    starts_at: Optional[datetime] = None

    ends_at: Optional[datetime] = None

    event_type: str = "Concert"

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