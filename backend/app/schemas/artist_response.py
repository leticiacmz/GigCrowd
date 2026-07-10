from typing import Optional

from pydantic import BaseModel, Field


class ArtistResponse(BaseModel):

    id: str

    name: str

    slug: str

    followers: Optional[int] = None

    image: Optional[str] = None

    genres: list[str] = Field(default_factory=list)

    popularity: Optional[int] = None

    verified: bool = False

    is_imported: bool = True