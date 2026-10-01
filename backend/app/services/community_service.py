"""
Artist-scoped community service.

All community operations are explicitly tied to an artist.
There is no global community concept.
"""
from fastapi import HTTPException, status

from app.repositories.artist_follow_repository import ArtistFollowRepository
from app.repositories.artist_repository import ArtistRepository


class CommunityService:
    """
    Service for handling artist-scoped community operations.

    Every operation requires an artist context. There is no
    abstract global community.
    """

    def __init__(
        self,
        artist_follow_repository: ArtistFollowRepository,
        artist_repository: ArtistRepository,
    ):

        self.artist_follow_repository = artist_follow_repository
        self.artist_repository = artist_repository

    async def verify_artist_exists(self, artist_slug: str):
        """Verify artist exists, raise 404 if not."""
        artist = await self.artist_repository.get_by_slug(artist_slug)
        if not artist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artist not found",
            )
        return artist

    async def check_follow_status(self, user_id: str, artist_slug: str) -> bool:
        """Check if user follows the artist."""
        return await self.artist_follow_repository.exists(user_id, artist_slug)

    async def require_follow_for_write(self, user_id: str, artist_slug: str):
        """
        Verify user follows the artist for write operations.

        Following the artist grants permission to participate in
        that artist's community. There is no separate membership.
        """
        following = await self.check_follow_status(user_id, artist_slug)
        if not following:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must follow this artist to participate in their community",
            )

    async def verify_post_belongs_to_artist(self, post_id: str, artist_slug: str, post_repo):
        """Verify a post belongs to the specified artist's community."""
        post = await post_repo.get_post_by_id(post_id)
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found",
            )
        if post.get("artist_slug") != artist_slug:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found in this artist's community",
            )
        return post
