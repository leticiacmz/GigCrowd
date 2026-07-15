from pydantic import BaseModel, Field


class ArtistListResponse(BaseModel):

    id: str

    slug: str

    name: str

    image: str | None = None

    genres: list[str] = Field(
        default_factory=list
    )