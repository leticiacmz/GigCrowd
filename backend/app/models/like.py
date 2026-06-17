from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class LikeTargetType(str, Enum):
    POST = "post"
    COMMENT = "comment"


class LikeBase(BaseModel):
    target_id: str
    target_type: LikeTargetType


class LikeCreate(LikeBase):
    pass


class LikeInDB(LikeBase):
    id: str = Field(alias="_id")
    user_id: str
    created_at: datetime

    class Config:
        populate_by_name = True


class LikeResponse(BaseModel):
    id: str
    user_id: str
    target_id: str
    target_type: LikeTargetType
    created_at: datetime

    class Config:
        populate_by_name = True
