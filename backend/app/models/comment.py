from pydantic import BaseModel, Field
from datetime import datetime


class CommentBase(BaseModel):
    post_id: str
    content: str = Field(..., min_length=1, max_length=1000)


class CommentCreate(CommentBase):
    pass


class CommentInDB(CommentBase):
    id: str = Field(alias="_id")
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True