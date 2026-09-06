from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Event(BaseModel):

    id: Optional[str] = None

    external_ids: dict[str, str] = Field(
        default_factory=dict,
    )

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
    artist_slug: str = Field(
        default="",
        description=(
            "Primary artist slug "
            "(transitional field for backward compatibility)"
        ),
    )

    # ============================================================
    # VENUE
    # ============================================================

    venue_slug: str

    # ============================================================
    # EVENT
    # ============================================================

    title: str

    starts_at: Optional[datetime] = None

    ends_at: Optional[datetime] = Field(
        default=None,
        description="End date for multi-day events and festivals",
    )

    event_type: str = Field(
        default="Concert",
        description=(
            "Event type such as Concert, FestivalInstance "
            "or Livestream"
        ),
    )

    # ============================================================
    # FESTIVAL
    # ============================================================

    festival: Optional[dict] = Field(
        default=None,
        description=(
            "Festival metadata such as series, edition, "
            "name and tracking count"
        ),
    )

    # ============================================================
    # LOCATION
    # ============================================================

    location: Optional[dict] = Field(
        default=None,
        description=(
            "Event location metadata such as city, country "
            "and geographic coordinates"
        ),
    )

    # ============================================================
    # SOURCE
    # ============================================================

    source: Optional[dict] = Field(
        default=None,
        description=(
            "Provider/source metadata for the event"
        ),
    )

    # ============================================================
    # TICKETS / STATUS
    # ============================================================

    sold_out: bool = False

    free: bool = False

    ticket_url: Optional[str] = None

    # ============================================================
    # ATTENDANCE
    # ============================================================

    going_count: int = 0

    maybe_count: int = 0

    went_count: int = 0