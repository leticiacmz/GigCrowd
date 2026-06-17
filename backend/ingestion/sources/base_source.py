from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime


class BaseSource(ABC):
    """Base class for event data sources"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
    
    @abstractmethod
    async def fetch_events(self, artist_name: str, date_from: datetime, date_to: datetime) -> List[Dict]:
        """Fetch events for an artist within a date range"""
        pass
    
    @abstractmethod
    async def fetch_artist_info(self, artist_name: str) -> Optional[Dict]:
        """Fetch artist information"""
        pass
    
    def get_source_name(self) -> str:
        """Return the name of the source"""
        return self.__class__.__name__
