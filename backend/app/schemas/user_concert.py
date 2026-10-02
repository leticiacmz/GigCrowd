"""The concert half of a profile.

A profile is not a list of analytics counters: it is what someone has seen,
what they said about it, and the people and artists they follow. These schemas
are the shape of those lists, and every field is either copied from a stored
document or derived from one, so nothing here can be a number without a row
behind it.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FestivalSummary(BaseModel):
    """One festival a user has been to.

    A festival is counted once, not once per edition: three days of the same
    festival is one festival, however many shows the user logged.
    """

    key: str = Field(
        description=(
            "Stable identity of the festival series, used to "
            "group its editions together"
        ),
    )

    name: str

    editions_count: int = Field(
        default=1,
        description="Distinct editions the user attended",
    )

    shows_count: int = Field(
        default=1,
        description="Shows the user logged for this festival",
    )

    first_date: Optional[datetime] = None

    last_date: Optional[datetime] = None

    image_url: Optional[str] = None


class ProfileEvent(BaseModel):
    """One event from a user's show log, with the event it refers to."""

    event_id: str

    title: str

    starts_at: Optional[datetime] = None

    ends_at: Optional[datetime] = None

    event_type: str = "Concert"

    venue_slug: Optional[str] = None

    venue_name: Optional[str] = None

    city: Optional[str] = None

    country: Optional[str] = None

    artist_slugs: list[str] = Field(
        default_factory=list,
    )

    artist_names: list[str] = Field(
        default_factory=list,
    )

    status: Optional[str] = None

    festival: Optional[FestivalSummary] = None


class ProfileReview(ProfileEvent):
    """A review, which is a show log that carries an opinion.

    A review always has a rating. The photo and the text are optional, and
    `reviewed_at` records when the opinion was written rather than when the
    show happened, so "recent reviews" can be ordered honestly.
    """

    rating: int

    review: Optional[str] = None

    photo_url: Optional[str] = None

    reviewed_at: Optional[datetime] = None


class ProfileArtist(BaseModel):
    """An artist the user follows.

    The follow is what makes the artist a community this user belongs to, so
    the row carries the community's activity alongside the artist's details.
    """

    slug: str

    name: str

    image: Optional[str] = None

    genres: list[str] = Field(
        default_factory=list,
    )

    followers_count: int = 0

    posts_count: int = Field(
        default=0,
        description="Posts in this artist's community",
    )

    is_following: bool = True


class ProfileReviewsResponse(BaseModel):

    username: str

    reviews: list[ProfileReview] = Field(
        default_factory=list,
    )

    total: int = 0


class ProfileEventsResponse(BaseModel):

    username: str

    events: list[ProfileEvent] = Field(
        default_factory=list,
    )

    total: int = 0


class ProfileFestivalsResponse(BaseModel):

    username: str

    festivals: list[FestivalSummary] = Field(
        default_factory=list,
    )

    total: int = 0


class ProfileArtistsResponse(BaseModel):

    username: str

    artists: list[ProfileArtist] = Field(
        default_factory=list,
    )

    total: int = 0
