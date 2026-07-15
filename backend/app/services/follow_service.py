from app.models.follow import FollowCreate
from app.repositories.follow_repository import FollowRepository
from app.database.connection import get_database


class FollowService:
    """
    Service responsible for follow business rules.

    Responsibilities:
    - Prevent self follow
    - Prevent duplicated follows
    - Update follower/following counters
    - Delegate persistence to FollowRepository
    """

    def __init__(self):
        self.repository = FollowRepository()

    async def follow_user(
        self,
        follower_id: str,
        follow_data: FollowCreate,
    ):
        db = get_database()

        # Cannot follow yourself
        if follower_id == follow_data.following_id:
            raise ValueError("Cannot follow yourself")

        # Already following?
        already_following = await self.repository.exists(
            follower_id=follower_id,
            following_id=follow_data.following_id,
        )

        if already_following:
            raise ValueError("Already following this user")

        # Create follow relationship
        follow = await self.repository.create(
            follower_id=follower_id,
            following_id=follow_data.following_id,
        )

        # Update counters
        await db.users.update_one(
            {"_id": follower_id},
            {
                "$inc": {
                    "following_count": 1
                }
            },
        )

        await db.users.update_one(
            {"_id": follow_data.following_id},
            {
                "$inc": {
                    "followers_count": 1
                }
            },
        )

        return follow

    async def unfollow_user(
        self,
        follower_id: str,
        following_id: str,
    ) -> bool:
        db = get_database()

        deleted = await self.repository.delete(
            follower_id=follower_id,
            following_id=following_id,
        )

        if not deleted:
            return False

        await db.users.update_one(
            {"_id": follower_id},
            {
                "$inc": {
                    "following_count": -1
                }
            },
        )

        await db.users.update_one(
            {"_id": following_id},
            {
                "$inc": {
                    "followers_count": -1
                }
            },
        )

        return True

    async def get_following(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ):
        return await self.repository.get_following(
            user_id=user_id,
            skip=skip,
            limit=limit,
        )

    async def get_followers(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ):
        return await self.repository.get_followers(
            user_id=user_id,
            skip=skip,
            limit=limit,
        )

    async def is_following(
        self,
        follower_id: str,
        following_id: str,
    ) -> bool:
        return await self.repository.exists(
            follower_id=follower_id,
            following_id=following_id,
        )