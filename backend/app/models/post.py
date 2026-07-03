from pydantic import BaseModel, Field
from typing import Optional
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
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True