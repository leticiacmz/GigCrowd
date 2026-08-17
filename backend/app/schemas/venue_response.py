from pydantic import BaseModel
from typing import Optional


class VenueResponse(BaseModel):

    id: Optional[str] = None

    slug: str

    name: str

    city: str

    country: str

    latitude: Optional[float] = None

    longitude: Optional[float] = None