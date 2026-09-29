from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CommentCreate(BaseModel):
    post_id: str
    content: str = Field(..., min_length=1, max_length=2000)
    parent_comment_id: Optional[str] = None


class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class CommentResponse(BaseModel):
    id: str
    post_id: str
    user_id: str
    content: str
    parent_comment_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Enriched fields
    username: Optional[str] = None
    user_avatar_url: Optional[str] = None
    replies: list["CommentResponse"] = Field(default_factory=list)
    replies_count: int = 0
