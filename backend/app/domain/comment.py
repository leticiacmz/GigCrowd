from datetime import datetime
from typing import Optional
from pydantic import Field

from .entity import Entity


class Comment(Entity):
    """Comment on a community post"""

    post_id: str
    user_id: str
    content: str

    # Nullable for replies
    parent_comment_id: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    class Config:
        collection = "comments"
