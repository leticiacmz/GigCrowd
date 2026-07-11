from typing import Optional

from app.domain.entity import Entity


class Venue(Entity):

    provider: str

    provider_venue_id: Optional[str] = None

    name: str

    slug: str

    city: str

    country: str

    latitude: Optional[float] = None

    longitude: Optional[float] = None