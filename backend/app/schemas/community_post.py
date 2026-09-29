from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CommunityPostCreate(BaseModel):
    artist_slug: str
    content: str = Field(..., min_length=1, max_length=2000)
    image_url: Optional[str] = None


class CommunityPostResponse(BaseModel):
    id: str
    artist_slug: str
    user_id: str
    content: str
    image_url: Optional[str] = None
    likes_count: int = 0
    comments_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Optional: include user info in response
    username: Optional[str] = None
    user_avatar_url: Optional[str] = None