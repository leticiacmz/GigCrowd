from typing import Optional
from pydantic import BaseModel


class AttendanceResponse(BaseModel):

    going: int

    maybe: int

    user_status: Optional[str] = None