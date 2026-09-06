from fastapi import HTTPException

from app.core.logger import get_logger

from app.repositories.artist_repository import (
    ArtistRepository,
)

from app.repositories.event_repository import (
    EventRepository,
)

from app.repositories.artist_follow_repository import (
    ArtistFollowRepository,
)

from app.services.synchronization_service import (
    SynchronizationService,
)

from app.schemas.artist_profile_response import (
    ArtistProfileResponse,
    ArtistEventStats,
)

from app.schemas.artist_list_response import (
    ArtistListResponse,
)


logger = get_logger("artist_service")


class ArtistService:

    def __init__(
        self,
        artist_repository: ArtistRepository,
        event_repository: EventRepository,
        artist_follow_repository: ArtistFollowRepository,
        synchronization_service: SynchronizationService,
    ):

        self.artist_repository = artist_repository

        self.event_repository = event_repository

        self.artist_follow_repository = (
            artist_follow_repository
        )

        self.synchronization_service = (
            synchronization_service
        )

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

        # --------------------------------------------------
        # Synchronization
        # --------------------------------------------------
        #
        # Songkick is the canonical provider for artists
        # and events.
        #
        # Spotify is only used as enrichment.
        # --------------------------------------------------

        sync = (
            await self.synchronization_service
            .synchronize_artist(
                artist,
                provider="songkick",
            )
        )

        logger.info(
            f"{artist.name} | {sync}"
        )

        # --------------------------------------------------
        # IMPORTANT:
        # Reload the artist after synchronization.
        #
        # The synchronization process may update:
        # image,
        # genres,
        # external_ids,
        # popularity,
        # etc.
        # --------------------------------------------------

        refreshed_artist = (
            await self.artist_repository.get_by_slug(
                slug
            )
        )

        if refreshed_artist:

            artist = refreshed_artist

        # --------------------------------------------------
        # Event statistics
        # --------------------------------------------------

        upcoming = (
            await self.event_repository
            .count_upcoming_by_artist_slug(
                slug
            )
        )

        total = (
            await self.event_repository
            .count_by_artist_slug(
                slug
            )
        )

        # --------------------------------------------------
        # GigCrowd followers ONLY
        # --------------------------------------------------
        #
        # This value comes exclusively from the
        # artist_follows collection.
        #
        # Spotify/Songkick follower counts are never
        # used here.
        # --------------------------------------------------

        followers_count = (
            await self.artist_follow_repository
            .count_followers(slug)
        )

        return ArtistProfileResponse(

            id=artist.id,

            slug=artist.slug,

            name=artist.name,

            image=artist.image,

            genres=artist.genres,

            external_ids=artist.external_ids,

            followers_count=followers_count,

            popularity=artist.popularity,

            verified=artist.verified,

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

        artists = (
            await self.artist_repository.get_all(
                limit=limit,
                skip=skip,
            )
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