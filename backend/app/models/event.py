from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class EventStatus(str, Enum):
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CANCELLED = "cancelled"
    PAST = "past"


class EventBase(BaseModel):
    title: str = Field(..., min_length=1)
    artist_id: str
    venue_name: str
    venue_id: Optional[str] = None
    date: datetime
    location: str  # City, Country
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    ticket_url: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: Optional[str] = None
    venue_name: Optional[str] = None
    venue_id: Optional[str] = None
    date: Optional[datetime] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    ticket_url: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    status: Optional[EventStatus] = None


class EventInDB(EventBase):
    id: str = Field(alias="_id")
    status: EventStatus = EventStatus.UPCOMING
    attendees_count: int = 0
    going_count: int = 0
    maybe_count: int = 0
    went_count: int = 0
    is_cached: bool = False  # True if from cache, False if permanent
    cached_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    source: Optional[str] = None  # Where the event was ingested from
    external_id: Optional[str] = None  # External API ID for deduplication

    class Config:
        populate_by_name = True


class EventResponse(BaseModel):
    id: str
    title: str
    artist_id: str
    venue_name: str
    venue_id: Optional[str] = None
    date: datetime
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    ticket_url: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    status: EventStatus
    attendees_count: int
    going_count: int
    maybe_count: int
    went_count: int
    is_cached: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
