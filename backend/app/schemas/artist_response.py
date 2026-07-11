from pydantic import BaseModel, Field


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