from typing import Optional

from pydantic import BaseModel, Field

# Imported for the forward reference in `ArtistProfileResponse.sync`, and
# aliased so the two schemas do not have to be defined in a particular order.
from app.schemas.artist_response import ArtistSyncOutcome


class ArtistEventStats(BaseModel):

    upcoming: int

    total: int


class ArtistProfileResponse(BaseModel):

    id: str

    slug: str

    name: str

    image: str | None = None

    genres: list[str] = Field(
        default_factory=list
    )

    external_ids: dict[str, str] = Field(
        default_factory=dict
    )

    followers_count: int = Field(
        default=0,
        description=(
            "Number of GigCrowd users "
            "following this artist."
        ),
    )

    popularity: int | None = None

    verified: bool = False

    events: ArtistEventStats

    # Present when this request performed a synchronization, and absent when it
    # did not.
    #
    # Two routes can set it and only two: an explicit import, and the first open
    # of a pending artist. Both answer the same question - "did this request go
    # and get the shows?" - so they report it the same way. An initialized artist's
    # ordinary page leaves it absent, which is the honest answer: nothing was
    # fetched, so there is no outcome to report.
    sync: Optional["ArtistSyncOutcome"] = Field(
        default=None,
        description=(
            "The outcome of synchronizing this artist's events as part of "
            "this request. Present only when the request performed the "
            "synchronization, so a caller can tell a complete import from one "
            "that created the artist and stopped, and a read from a write."
        ),
    )