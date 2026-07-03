from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime
from enum import Enum


class ActivityType(str, Enum):
    FOLLOW = "follow"
    ATTEND_EVENT = "attend_event"
    CREATE_POST = "create_post"
    LIKE_POST = "like_post"
    COMMENT_POST = "comment_post"


class ActivityBase(BaseModel):
    activity_type: ActivityType
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    metadata: Optional[Dict] = None


class ActivityCreate(ActivityBase):
    pass


class ActivityInDB(ActivityBase):
    id: str = Field(alias="_id")
    user_id: str
    created_at: datetime

    class Config:
        populate_by_name = True


class ActivityResponse(ActivityInDB):
    pass