from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Event(BaseModel):

    id: Optional[str] = None

    external_ids: dict[str, str] = Field(
        default_factory=dict,
    )

    # NEW: Complete artist relationship support
    artist_slugs: List[str] = Field(
        default_factory=list,
        description="List of artist slugs for this event (supports festivals)"
    )

    # PRESERVE: Backward compatibility during transition
    artist_slug: str = Field(
        default="",
        description="Primary artist slug (transitional field for backward compatibility)"
    )

    venue_slug: str

    title: str

    starts_at: Optional[datetime] = None

    # NEW: Support multi-day festivals
    ends_at: Optional[datetime] = Field(
        default=None,
        description="End date for multi-day festivals"
    )

    # NEW: Event classification
    event_type: str = Field(
        default="Concert",
        description="Event type: Concert, FestivalInstance, etc."
    )

    sold_out: bool = False

    free: bool = False

    ticket_url: Optional[str] = None

    going_count: int = 0

    maybe_count: int = 0

    went_count: int = 0