from typing import Optional

from pydantic import BaseModel, Field


class ArtistSyncOutcome(BaseModel):
    """What the import actually did about this artist's events.

    Reported rather than assumed, because "the artist was created" and "the
    artist's shows are now in the database" are different facts and only the
    first one used to be observable. A caller that cannot see the second has no
    way to tell a working import from one that stopped halfway.
    """

    attempted: bool = Field(
        default=False,
        description=(
            "Whether a synchronization was run at all. False means "
            "synchronization was not configured for this process."
        ),
    )

    succeeded: bool = Field(
        default=False,
        description=(
            "Whether the synchronization completed without raising."
        ),
    )

    events_received: int = Field(
        default=0,
        description=(
            "Events the provider returned for this artist. Zero is a "
            "legitimate answer - an artist with nothing announced has no "
            "upcoming shows - and is not an error."
        ),
    )

    events_created: int = 0

    events_existing: int = 0

    reason: Optional[str] = Field(
        default=None,
        description=(
            "Why no synchronization ran, when one was expected."
        ),
    )


class ArtistResponse(BaseModel):

    provider: str

    provider_artist_id: str

    name: str

    followers: int | None = None

    image: str | None = None

    genres: list[str] = Field(default_factory=list)

    popularity: int | None = None

    verified: bool

    is_imported: bool

    slug: str | None = None

    id: str | None = None

    sync: Optional[ArtistSyncOutcome] = Field(
        default=None,
        description=(
            "The outcome of synchronizing this artist's events as part of "
            "the import. Present so the caller can tell a complete import "
            "from one that only created the artist record."
        ),
    )