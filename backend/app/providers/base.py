from abc import ABC, abstractmethod

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
    ) -> dict:
        """
        Return complete provider artist payload.
        """
        raise NotImplementedError