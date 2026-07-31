from pydantic import BaseModel, Field


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

    followers: int | None = None

    popularity: int | None = None

    verified: bool = False

    events: ArtistEventStats