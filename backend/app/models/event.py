from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class EventStatus(str, Enum):
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    PAST = "past"
    CANCELLED = "cancelled"

class EventBase(BaseModel):
    title: str
    artist_id: Optional[str] = None
    artist_name: str

    venue_id: Optional[str] = None
    venue_name: str

    date: datetime
    location: str
    city: str
    country: str

    description: Optional[str] = None
    image_url: Optional[str] = None
    ticket_url: Optional[str] = None

    status: str = EventStatus.UPCOMING

    setlist: Optional[List[str]] = None


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: Optional[str] = None
    artist_name: Optional[str] = None
    venue_name: Optional[str] = None
    date: Optional[datetime] = None
    location: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    ticket_url: Optional[str] = None
    status: Optional[str] = None


class EventInDB(EventBase):
    id: str = Field(alias="_id")

    going_count: int = 0
    maybe_count: int = 0
    went_count: int = 0

    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class EventResponse(EventInDB):
    pass