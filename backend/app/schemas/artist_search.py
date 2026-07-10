from pydantic import BaseModel, Field
from typing import Optional


class ArtistSearchItem(BaseModel):

    provider: str

    provider_artist_id: str

    name: str

    followers: Optional[int] = None

    image: Optional[str] = None

    popularity: Optional[int] = None

    verified: bool = False

    genres: list[str] = Field(default_factory=list)

    is_imported: bool = False