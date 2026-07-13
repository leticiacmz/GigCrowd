from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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