from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MediaType(str, Enum):
    TEXT = "text"
    IMAGE = "image"


class PostBase(BaseModel):
    content: Optional[str] = None
    media_url: Optional[str] = None
    media_type: MediaType = MediaType.TEXT
    event_id: Optional[str] = None


class PostCreate(PostBase):
    pass


class PostUpdate(BaseModel):
    content: Optional[str] = None
    media_url: Optional[str] = None


class PostInDB(PostBase):
    id: str = Field(alias="_id")
    user_id: str
    likes_count: int = 0
    comments_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class PostResponse(BaseModel):
    id: str
    user_id: str
    content: Optional[str] = None
    media_url: Optional[str] = None
    media_type: MediaType
    event_id: Optional[str] = None
    likes_count: int
    comments_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
