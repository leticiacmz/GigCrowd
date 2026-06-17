from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CommentBase(BaseModel):
    post_id: str
    content: str = Field(..., min_length=1, max_length=1000)


class CommentCreate(CommentBase):
    pass


class CommentUpdate(BaseModel):
    content: Optional[str] = None


class CommentInDB(CommentBase):
    id: str = Field(alias="_id")
    user_id: str
    likes_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class CommentResponse(BaseModel):
    id: str
    post_id: str
    user_id: str
    content: str
    likes_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
