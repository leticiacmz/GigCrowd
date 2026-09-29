from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional

from pydantic import Field

from .entity import Entity


class ActivityType(str, Enum):
    """Types of activities that can appear in the feed"""

    USER_FOLLOWED_USER = "user_followed_user"
    USER_FOLLOWED_ARTIST = "user_followed_artist"
    COMMUNITY_POST_CREATED = "community_post_created"

    # Reserved for upcoming social features
    EVENT_ATTENDANCE = "event_attendance"
    REVIEW_CREATED = "review_created"
    COMMENT_CREATED = "comment_created"
    REACTION_CREATED = "reaction_created"


class ActivityObjectType(str, Enum):
    """Types of entities an activity can point to"""

    USER = "user"
    ARTIST = "artist"
    COMMUNITY_POST = "community_post"
    EVENT = "event"
    REVIEW = "review"
    COMMENT = "comment"


class FeedActivity(Entity):
    """
    Generic feed activity.

    An activity is always produced by an actor and points to an object.
    Nested activities (a comment on a post, a reaction to a review) also
    reference the parent entity through `target_type` / `target_id`, so new
    activity types can be added without changing the storage shape.
    """

    actor_id: str
    activity_type: ActivityType

    object_type: ActivityObjectType
    object_id: str

    target_type: Optional[ActivityObjectType] = None
    target_id: Optional[str] = None

    payload: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )

    class Config:
        collection = "feed_activities"
