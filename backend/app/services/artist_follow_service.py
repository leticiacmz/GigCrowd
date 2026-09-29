from typing import Optional

from fastapi import HTTPException

from app.repositories.artist_repository import (
    ArtistRepository,
)

from app.repositories.artist_follow_repository import (
    ArtistFollowRepository,
)

from app.services.feed_activity_service import (
    FeedActivityService,
)


class ArtistFollowService:

    def __init__(
        self,
        repository: ArtistFollowRepository,
        artist_repository: ArtistRepository,
        feed_activity_service: Optional[FeedActivityService] = None,
    ):

        self.repository = repository

        self.artist_repository = artist_repository

        self.feed_activity_service = feed_activity_service

    async def follow(
        self,
        user_id: str,
        artist_slug: str,
    ):

        artist = (
            await self.artist_repository.get_by_slug(
                artist_slug
            )
        )

        if not artist:

            raise HTTPException(
                status_code=404,
                detail="Artist not found.",
            )

        exists = await self.repository.exists(
            user_id,
            artist_slug,
        )

        if not exists:

            await self.repository.create_follow(
                user_id,
                artist_slug,
            )

            if self.feed_activity_service:

                await self.feed_activity_service.record_artist_follow(
                    actor_id=user_id,
                    artist_slug=artist_slug,
                    artist_name=artist.get("name"),
                )

        return {
            "following": True,
        }

    async def unfollow(
        self,
        user_id: str,
        artist_slug: str,
    ):

        await self.repository.delete_follow(
            user_id,
            artist_slug,
        )

        if self.feed_activity_service:

            await self.feed_activity_service.remove_artist_follow(
                actor_id=user_id,
                artist_slug=artist_slug,
            )

        return {
            "following": False,
        }

    async def status(
        self,
        user_id: str,
        artist_slug: str,
    ):

        following = await self.repository.exists(
            user_id,
            artist_slug,
        )

        return {
            "following": following,
        }