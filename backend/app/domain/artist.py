from typing import Optional

from pydantic import Field

from .entity import Entity


class Artist(Entity):

    name: str

    normalized_name: str

    slug: str

    external_ids: dict[str, str] = Field(default_factory=dict)

    followers: Optional[int] = None

    image: Optional[str] = None

    genres: list[str] = Field(default_factory=list)

    popularity: Optional[int] = None

    verified: bool = False