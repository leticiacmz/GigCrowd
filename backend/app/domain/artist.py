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
