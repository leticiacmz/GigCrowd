from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class FollowBase(BaseModel):
    """
    Base fields for follow relationship.
    """

    following_id: str



class FollowCreate(FollowBase):
    """
    Data required to create a follow.
    """

    pass



class FollowInDB(FollowBase):
    """
    Follow document stored in MongoDB.
    """

    id: str = Field(alias="_id")

    follower_id: str

    created_at: datetime


    class Config:
        populate_by_name = True



class FollowResponse(BaseModel):

    id: str = Field(alias="_id")

    follower_id: str

    following_id: str

    created_at: Optional[datetime] = None


    class Config:
        populate_by_name = True