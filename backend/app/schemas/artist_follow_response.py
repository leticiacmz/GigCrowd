from pydantic import BaseModel



class ArtistFollowResponse(BaseModel):

    following: bool