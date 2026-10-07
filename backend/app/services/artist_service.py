from fastapi import HTTPException

from app.repositories.artist_repository import (
    ArtistRepository,
)

from app.repositories.event_repository import (
    EventRepository,
)

from app.repositories.artist_follow_repository import (
    ArtistFollowRepository,
)

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
        artist_follow_repository: ArtistFollowRepository,
    ):
        """A reader. It deliberately holds no synchronization service.

        Keeping that dependency out of the constructor is the point rather than a
        tidy-up: a read path that cannot see `SynchronizationService` cannot grow
        a write side effect later without someone noticing they have to add the
        dependency back on purpose.
        """

        self.artist_repository = artist_repository

        self.event_repository = event_repository

        self.artist_follow_repository = (
            artist_follow_repository
        )

    async def get_artist_profile(
        self,
        slug: str,
    ) -> ArtistProfileResponse:

        # --------------------------------------------------
        # READ ONLY
        # --------------------------------------------------
        #
        # This method used to call `synchronize_artist`, so opening an artist
        # page scraped Songkick, inserted events and wrote `last_synced_at`.
        # A GET that writes is not a slow read, it is a side effect wearing a
        # read's clothes: it made the catalogue depend on who happened to look
        # at a page, spent outbound requests nobody asked for, and left imported
        # events with no `created_at` because the import path predates it.
        #
        # Synchronization now belongs to `ArtistSyncJob`, on the scheduler's
        # clock, where it is bounded, observable and attributable.
        #
        # Songkick is still the canonical provider; that is a question of which
        # source to trust, not of when to ask it.
        # --------------------------------------------------

        artist = await self.artist_repository.get_by_slug(
            slug
        )

        if not artist:

            raise HTTPException(
                status_code=404,
                detail="Artist not found.",
            )

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