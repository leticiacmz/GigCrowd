from pydantic import BaseModel


class UserProfileResponse(BaseModel):

    username: str

    full_name: str | None = None

    bio: str | None = None

    avatar_url: str | None = None

    followers_count: int

    following_count: int