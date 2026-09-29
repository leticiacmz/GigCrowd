from datetime import datetime
from typing import Optional
from pydantic import Field

from .entity import Entity


class FeedActivity(Entity):
    """Social feed activity item"""
    
    actor_id: str  # User who performed the action
    actor_username: str
    actor_avatar_url: Optional[str] = None
    
    activity_type: str  # "followed_user", "followed_artist", "attended_event", "reviewed_event", "posted_community", etc.
    
    # Target entities (depending on activity type)
    target_user_id: Optional[str] = None
    target_user_username: Optional[str] = None
    target_artist_slug: Optional[str] = None
    target_artist_name: Optional[str] = None
    target_event_id: Optional[str] = None
    target_event_title: Optional[str] = None
    target_post_id: Optional[str] = None
    target_post_content: Optional[str] = None
    
    # Activity metadata
    metadata: dict = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        collection = "feed_activities"