from datetime import datetime

from pydantic import Field

from .entity import Entity


class Artist(Entity):

    name: str

    normalized_name: str

    slug: str

    external_ids: dict[str, str] = Field(
        default_factory=dict,
    )

    image: str | None = None

    genres: list[str] = Field(
        default_factory=list,
    )

    popularity: int | None = None

    verified: bool = False

    sync_status: str | None = None

    last_synced_at: datetime | None = None

    #: When this record was last written.
    #: 
    #: Carried on the domain object because it is the only record of when a
    #: *failed* fetch was attempted - `last_synced_at` is deliberately not written
    #: on failure, since a timestamp is what makes an artist look initialized. It
    #: is what lets a retry back off instead of happening on every page view.
    updated_at: datetime | None = None

    followers_count: int = Field(default=0)
