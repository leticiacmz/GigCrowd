from typing import Optional, Dict, Any

from pydantic import BaseModel


class ArtistImportRequest(BaseModel):

    provider: str

    provider_artist_id: str

    artist_data: Optional[Dict[str, Any]] = None

    image: Optional[str] = None