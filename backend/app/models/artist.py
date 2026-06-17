from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ArtistBase(BaseModel):
    name: str = Field(..., min_length=1)
    spotify_id: Optional[str] = None
    image_url: Optional[str] = None
    genres: Optional[List[str]] = None
    bio: Optional[str] = None


class ArtistCreate(ArtistBase):
    pass


class ArtistUpdate(BaseModel):
    name: Optional[str] = None
    spotify_id: Optional[str] = None
    image_url: Optional[str] = None
    genres: Optional[List[str]] = None
    bio: Optional[str] = None


class ArtistInDB(ArtistBase):
    id: str = Field(alias="_id")
    followers_count: int = 0
    events_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class ArtistResponse(BaseModel):
    id: str
    name: str
    spotify_id: Optional[str] = None
    image_url: Optional[str] = None
    genres: Optional[List[str]] = None
    bio: Optional[str] = None
    followers_count: int
    events_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
