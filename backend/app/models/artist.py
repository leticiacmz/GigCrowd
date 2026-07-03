from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ArtistBase(BaseModel):
    name: str
    normalized_name: Optional[str] = None
    bio: Optional[str] = None
    image_url: Optional[str] = None
    genre: Optional[str] = None


class ArtistCreate(ArtistBase):
    pass


class ArtistUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    image_url: Optional[str] = None
    genre: Optional[str] = None
    external_id: Optional[str] = None


class ArtistInDB(ArtistBase):
    id: str = Field(alias="_id")

    followers_count: int = 0
    events_count: int = 0

    source: Optional[str] = None
    external_id: Optional[str] = None

    sync_status: Optional[str] = None
    last_synced_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class ArtistResponse(ArtistBase):
    id: str

    followers_count: int
    events_count: int

    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True