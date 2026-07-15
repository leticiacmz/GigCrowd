from fastapi import HTTPException

from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository

from app.schemas.artist_profile_response import (
    ArtistProfileResponse,
    ArtistEventStats,
)

from app.schemas.artist_list_response import (
    ArtistListResponse,
)

class ArtistService:

    def __init__(
        self,
        artist_repository: ArtistRepository,
        event_repository: EventRepository,
    ):

        self.artist_repository = artist_repository

        self.event_repository = event_repository

    async def get_artist_profile(
        self,
        slug: str,
    ) -> ArtistProfileResponse:

        artist = await self.artist_repository.get_by_slug(
            slug
        )

        if not artist:

            raise HTTPException(
                status_code=404,
                detail="Artist not found.",
            )

        upcoming = (
            await self.event_repository.count_upcoming_by_artist_slug(
                slug
            )
        )

        total = (
            await self.event_repository.count_by_artist_slug(
                slug
            )
        )

        return ArtistProfileResponse(

            id=artist.id,

            slug=artist.slug,

            name=artist.name,

            image=artist.image,

            genres=artist.genres,

            events=ArtistEventStats(

                upcoming=upcoming,

                total=total,
            ),
        )

    async def get_artists(
        self,
        limit: int = 20,
        skip: int = 0,
    ) -> list[ArtistListResponse]:

        artists = await self.artist_repository.get_all(
            limit=limit,
            skip=skip,
        )


        return [

            ArtistListResponse(

                id=artist.id,

                slug=artist.slug,

                name=artist.name,

                image=artist.image,

                genres=artist.genres,

            )

            for artist in artists

        ]