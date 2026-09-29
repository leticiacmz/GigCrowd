from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class FeedActivityResponse(BaseModel):
    id: str
    actor_id: str
    actor_username: str
    actor_avatar_url: Optional[str] = None
    activity_type: str
    target_user_id: Optional[str] = None
    target_user_username: Optional[str] = None
    target_artist_slug: Optional[str] = None
    target_artist_name: Optional[str] = None
    target_event_id: Optional[str] = None
    target_event_title: Optional[str] = None
    target_post_id: Optional[str] = None
    target_post_content: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime