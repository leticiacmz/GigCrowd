from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class VenueBase(BaseModel):
    name: str
    city: Optional[str] = None
    country: Optional[str] = None


class VenueCreate(VenueBase):
    pass


class VenueInDB(VenueBase):
    id: str = Field(alias="_id")
    created_at: datetime

    class Config:
        populate_by_name = True