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

    event_id: Optional[str] = Field(
        default=None,
        description=(
            "The most recent edition the user logged, so the row can "
            "lead to the festival page behind it"
        ),
    )

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

    # Whether this show carries the person's own opinion of it, and how highly
    # they rated it.
    #
    # The diary needs this so an attended show they wrote about can be marked as
    # such without opening every review: a row that has been rated is not the
    # same as a row they merely remember attending.
    has_review: bool = False

    rating: Optional[int] = None


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


class SeenArtist(BaseModel):
    """An artist this person has actually seen.

    The one number here is the point of the section: how many distinct shows
    they attended where this artist performed. It is deliberately the only
    figure, because a community post count or a follower count answers a
    different question and invites reading this list as popularity.
    """

    slug: str

    name: str

    image: Optional[str] = None

    shows_count: int = Field(
        default=0,
        description=(
            "Distinct attended events where this artist performed"
        ),
    )

    resolved: bool = Field(
        default=False,
        description=(
            "Whether an imported artist page exists for this slug. An "
            "unresolved artist is still listed, because the person did see "
            "them, but it has no page to link to."
        ),
    )


class ProfileArtistsSeenResponse(BaseModel):
    """Artists I have seen, most seen first."""

    username: str

    artists: list[SeenArtist] = Field(
        default_factory=list,
    )

    total: int = 0


class ProfileEventsResponse(BaseModel):
    """One state of a user's shows.

    `events` holds the state that was asked for and `total` is how many rows
    that state holds. `counts` carries all three states on every response, so
    the breakdown can be drawn from a single request and a figure can never
    disagree with the list behind it.
    """

    username: str

    events: list[ProfileEvent] = Field(
        default_factory=list,
    )

    total: int = 0

    status: Optional[str] = Field(
        default=None,
        description=(
            "The attendance state this list holds: `attended`, "
            "`want-to-go` or `maybe`. Null when the list holds "
            "every logged show."
        ),
    )

    counts: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "How many shows the user has in each of the three "
            "attendance states, keyed by the same words the "
            "`status` filter accepts"
        ),
    )

    limit: int = 0

    skip: int = 0


class ProfileEventCursor(BaseModel):
    """An opaque position in a user's show history.

    A client passes this back exactly as it was given. It is deliberately not
    interpreted anywhere in the client: reading a date out of it and recomposing
    one is how a paging scheme quietly starts skipping rows.
    """

    date: str = Field(
        description="ISO timestamp of the last row on the page just read",
    )

    id: str = Field(
        description=(
            "Identity of that row. Needed because several shows "
            "routinely share one date."
        ),
    )


class ProfileEventsPageResponse(BaseModel):
    """One page of a user's show history, read by cursor.

    Same rows and same states as `ProfileEventsResponse`; the difference is only
    how the next page is addressed, so scrolling to the past does not re-read the
    pages before it.

    `next_cursor` is null on the last page, which is how a client knows to stop
    rather than requesting the same rows again.
    """

    username: str

    events: list[ProfileEvent] = Field(
        default_factory=list,
    )

    total: int = 0

    status: Optional[str] = None

    counts: dict[str, int] = Field(
        default_factory=dict,
    )

    limit: int = 0

    next_cursor: Optional[ProfileEventCursor] = None


class ProfileShowCalendarResponse(BaseModel):
    """One month of days on which this user went to a show.

    `days` maps an ISO date to how many shows they attended on it, so a day with
    two festivals in one room can show a small count rather than a single mark.

    Only shows logged as `went` appear. The key is the date in the user's own
    timezone at the point the log was written, which is what a reader means by
    "the night of the 14th".
    """

    username: str

    year: int

    month: int

    days: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "ISO date to the number of shows attended that day, for "
            "shows logged as `went`"
        ),
    )

    total: int = 0

    has_any: bool = Field(
        default=True,
        description=(
            "Whether this profile has any attended show at all, so a "
            "client can present an empty month without a second request"
        ),
    )


class ProfileShowYear(BaseModel):
    """One calendar year and how many shows were attended in it."""

    year: int

    shows: int = 0


class ProfileShowYearResponse(BaseModel):
    """The years this user has attended shows in, newest first.

    Exists so a calendar's year selector can offer the years that actually have
    something in them. Without it, reaching 2021 from today means sixty clicks of
    the next-month arrow, which is a calendar that assumes the reader only ever
    cares about now.
    """

    username: str

    years: list[ProfileShowYear] = Field(
        default_factory=list,
        description=(
            "Years with attended shows, newest first. The current year is "
            "always present, with a count of 0 when nothing has been logged "
            "in it yet."
        ),
    )

    current_year: int

    has_any: bool = Field(
        default=False,
        description=(
            "Whether any year carries a show, so a client can tell an "
            "empty history from an empty month."
        ),
    )


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
