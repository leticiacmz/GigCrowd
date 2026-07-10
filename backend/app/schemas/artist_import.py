from pydantic import BaseModel


class ArtistImportRequest(BaseModel):

    provider: str

    provider_artist_id: str