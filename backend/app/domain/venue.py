from typing import Optional

from pydantic import BaseModel, Field


class Venue(BaseModel):

    id: Optional[str] = None

    external_ids: dict[str, str] = Field(
        default_factory=dict,
    )

    name: str

    normalized_name: str

    slug: str

    city: str

    country: str

    region: Optional[str] = None

    latitude: Optional[float] = None

    longitude: Optional[float] = None

    street_address: Optional[str] = None

    postal_code: Optional[str] = None