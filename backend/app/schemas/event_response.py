from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EventResponse(BaseModel):

    id: Optional[str] = None

    title: str

    starts_at: Optional[datetime] = None

    ticket_url: Optional[str] = None

    free: Optional[bool] = None

    sold_out: Optional[bool] = None

    venue_slug: str