from typing import Optional

from pydantic import BaseModel


class UserUpdateRequest(BaseModel):

    full_name: Optional[str] = None

    bio: Optional[str] = None

    location: Optional[str] = None