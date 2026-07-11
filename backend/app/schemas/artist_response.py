from typing import Optional

from pydantic import BaseModel, Field


class ArtistResponse(BaseModel):

    provider: str

    provider_artist_id: str

    name: str

    followers: int | None

    image: str | None

    genres: list[str]

    popularity: int | None

    verified: bool

    is_imported: bool

    slug: str | None = None

    id: str | None = None