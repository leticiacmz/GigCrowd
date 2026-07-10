from abc import ABC, abstractmethod

from app.domain.artist import Artist
from app.schemas.artist_search import ArtistSearchItem


class BaseProvider(ABC):

    @abstractmethod
    async def search_artist(
        self,
        query: str,
    ) -> list[ArtistSearchItem]:
        """
        Search artists in the provider.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_artist(
        self,
        artist_id: str,
    ) -> Artist:
        """
        Return a domain Artist.
        """
        raise NotImplementedError