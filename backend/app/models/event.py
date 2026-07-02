from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal


class EventStatus:
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    PAST = "past"
    CANCELLED = "cancelled"


EventStatusLiteral = Literal["upcoming", "ongoing", "past", "cancelled"]


class EventType:
    PAST = "past"
    FUTURE = "future"


EventTypeLiteral = Literal["past", "future"]


class EventSearchParams(BaseModel):
    """Parameters for searching events"""
    query: str = Field(..., description="Search query (artist name, venue, or city)")
    event_type: EventTypeLiteral = Field("future", description="Type of events: 'past' or 'future'")
    start_date: Optional[datetime] = Field(None, description="Start date for search range")
    end_date: Optional[datetime] = Field(None, description="End date for search range")
    skip: int = Field(0, ge=0, description="Number of results to skip")
    limit: int = Field(20, ge=1, le=100, description="Maximum number of results to return")


class EventBase(BaseModel):
    title: str
    artist_name: str
    venue_name: str
    date: datetime
    location: str
    city: str
    country: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    ticket_url: Optional[str] = None
    status: str = EventStatus.UPCOMING
    setlist: Optional[list] = None
    setlist_count: Optional[int] = None


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
    created_at: datetime
    updated_at: datetime
    going_count: int = 0
    maybe_count: int = 0
    went_count: int = 0
    is_cached: bool = False
    cached_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class EventResponse(EventBase):
    id: str
    created_at: datetime
    updated_at: datetime
    going_count: int = 0
    maybe_count: int = 0
    went_count: int = 0
    is_cached: bool = False
    cached_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
