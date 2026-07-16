from pydantic import BaseModel
from typing import List, Any


class UserStatsResponse(BaseModel):

    followers_count: int

    following_count: int


    shows_attended: int

    shows_going: int

    shows_maybe: int


    artists_seen: int

    upcoming_events: int


    total_posts: int


    class Config:

        populate_by_name = True