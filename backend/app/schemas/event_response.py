from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.venue_response import VenueResponse


class EventResponse(BaseModel):

    id: Optional[str] = None

    title: str

    starts_at: Optional[datetime] = None

    ticket_url: Optional[str] = None

    free: Optional[bool] = None

    sold_out: Optional[bool] = None

    venue_slug: str

    venue: VenueResponse

    going_count: int = 0

    maybe_count: int = 0

    went_count: int = 0