from datetime import datetime
from typing import Optional

from pydantic import Field

from app.domain.entity import Entity


class Event(Entity):

    provider: str

    provider_event_id: str

    artist_ids: list[str] = Field(default_factory=list)

    venue_id: Optional[str] = None

    title: str

    description: Optional[str] = None

    starts_at: datetime

    url: Optional[str] = None

    image: Optional[str] = None

    status: str = "scheduled"

    last_synced_at: Optional[datetime] = None