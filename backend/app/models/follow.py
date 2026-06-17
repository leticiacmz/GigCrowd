from pydantic import BaseModel, Field
from datetime import datetime


class FollowBase(BaseModel):
    following_id: str


class FollowCreate(FollowBase):
    pass


class FollowInDB(FollowBase):
    id: str = Field(alias="_id")
    follower_id: str
    created_at: datetime

    class Config:
        populate_by_name = True


class FollowResponse(BaseModel):
    id: str
    follower_id: str
    following_id: str
    created_at: datetime

    class Config:
        populate_by_name = True
