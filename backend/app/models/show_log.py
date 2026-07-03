from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class AttendanceStatus(str, Enum):
    GOING = "going"
    MAYBE = "maybe"
    WENT = "went"
    NOT_GOING = "not_going"


class ShowLogBase(BaseModel):
    event_id: str
    status: AttendanceStatus
    notes: Optional[str] = None


class ShowLogCreate(ShowLogBase):
    pass


class ShowLogUpdate(BaseModel):
    status: Optional[AttendanceStatus] = None
    notes: Optional[str] = None


class ShowLogInDB(ShowLogBase):
    id: str = Field(alias="_id")

    user_id: str

    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class ShowLogResponse(ShowLogInDB):
    pass