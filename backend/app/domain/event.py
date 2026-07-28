from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Event(BaseModel):

    id: Optional[str] = None

    external_ids: dict[str, str] = Field(
        default_factory=dict,
    )

    artist_slug: str

    venue_slug: str

    title: str

    starts_at: Optional[datetime] = None

    sold_out: bool = False

    free: bool = False

    ticket_url: Optional[str] = None

    going_count: int = 0

    maybe_count: int = 0

    went_count: int = 0