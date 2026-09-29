from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.domain.feed_activity import ActivityObjectType, ActivityType


class FeedActor(BaseModel):
    id: str
    username: Optional[str] = None
    avatar_url: Optional[str] = None


class FeedActivityResponse(BaseModel):
    id: str
    actor: FeedActor

    activity_type: ActivityType

    object_type: ActivityObjectType
    object_id: str

    target_type: Optional[ActivityObjectType] = None
    target_id: Optional[str] = None

    payload: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime


class FeedPage(BaseModel):
    items: list[FeedActivityResponse]
    limit: int
    skip: int
    total: int
    has_more: bool
    next_skip: Optional[int] = None
