from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseProvider(ABC):

    @abstractmethod
    async def search_artist(self, query: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_artist(self, artist_id: str) -> Dict[str, Any]:
        pass