from typing import Optional

from pydantic import BaseModel, Field


class ArtistSearchItem(BaseModel):
    """
    Standard search result returned to the frontend,
    regardless of the provider.
    """

    provider: str

    provider_artist_id: str

    name: str

    followers: Optional[int] = None

    image: Optional[str] = None

    popularity: Optional[int] = None

    verified: bool = False

    genres: list[str] = Field(default_factory=list)