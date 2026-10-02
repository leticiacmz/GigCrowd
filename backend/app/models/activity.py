from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ActivityType(str, Enum):
    """Types of activity that can appear in the unified feed timeline."""

    FOLLOW = "follow"
    ATTEND_EVENT = "attend_event"
    CREATE_POST = "create_post"
    LIKE_POST = "like_post"
    COMMENT_POST = "comment_post"
    CREATE_COMMUNITY_POST = "create_community_post"
    CREATE_REVIEW = "create_review"


class NotificationType(str, Enum):
    """Types of notification a user can receive about their own content."""

    FOLLOW = "follow"
    LIKE = "like"
    COMMENT = "comment"
    REPLY = "reply"


class ActivityBase(BaseModel):
    activity_type: ActivityType
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    metadata: Optional[Dict] = None


class ActivityCreate(ActivityBase):
    pass


class ActivityInDB(ActivityBase):
    model_config = ConfigDict(populate_by_name=True)

    # Stored as Mongo's `_id`, but the API contract exposes it as `id` so
    # clients never have to know about the storage detail.
    id: str = Field(alias="_id", serialization_alias="id")
    user_id: str
    created_at: datetime


class NotificationBase(BaseModel):
    """A notification is always addressed to exactly one recipient."""

    recipient_id: str
    actor_id: str
    type: NotificationType
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    context: Optional[Dict] = None


class NotificationCreate(NotificationBase):
    pass


class NotificationInDB(NotificationBase):
    model_config = ConfigDict(populate_by_name=True)

    # Read from Mongo's `_id`, written to clients as `id`.
    id: str = Field(alias="_id", serialization_alias="id")
    read: bool = False
    created_at: datetime


class NotificationActor(BaseModel):
    """Public information about the user that triggered the notification."""

    id: str
    username: Optional[str] = None
    avatar_url: Optional[str] = None


class NotificationResponse(NotificationInDB):
    """Notification enriched with the actor and a ready-to-use target."""

    actor: NotificationActor
    target: Optional[Dict] = None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
    total: int
