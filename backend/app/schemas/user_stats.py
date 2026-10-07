from pydantic import BaseModel
from typing import List, Any


class UserStatsResponse(BaseModel):

    followers_count: int

    following_count: int


    shows_attended: int

    shows_going: int

    shows_maybe: int


    # The distinct artists this person has been to a show of, counting only
    # attendance and reading a festival date's lineup. This is what the profile
    # header shows under "Artists"; `followed_artists_count` stays available but
    # is not that section's meaning.
    artists_seen: int

    upcoming_events: int


    total_posts: int


    # The concert profile's figures. Each one is counted from the collection
    # that backs it, so none of them can be a figure without a row behind it.
    reviews_count: int = 0

    festivals_count: int = 0

    followed_artists_count: int = 0


    class Config:

        populate_by_name = True