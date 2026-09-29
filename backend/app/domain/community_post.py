from datetime import datetime
from typing import Optional
from pydantic import Field

from .entity import Entity


class CommunityPost(Entity):
    """Community post for an artist"""
    
    artist_slug: str
    user_id: str
    content: str
    
    # Optional fields for future enhancement
    image_url: Optional[str] = None
    likes_count: int = Field(default=0)
    comments_count: int = Field(default=0)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    class Config:
        collection = "community_posts"