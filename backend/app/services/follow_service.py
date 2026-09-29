from app.repositories.follow_repository import FollowRepository
from app.repositories.user_repository import UserRepository


class FollowService:


    def __init__(
        self,
        follow_repository: FollowRepository,
        user_repository: UserRepository,
    ):

        self.follow_repository = follow_repository

        self.user_repository = user_repository



    async def follow_user(
        self,
        follower_id: str,
        username: str,
    ):


        user = await self.user_repository.get_by_username(
            username
        )


        if not user:

            raise ValueError(
                "User not found"
            )


        following_id = str(
            user["_id"]
        )


        if follower_id == following_id:

            raise ValueError(
                "Cannot follow yourself"
            )



        exists = await self.follow_repository.exists(
            follower_id,
            following_id,
        )


        if exists:

            raise ValueError(
                "Already following this user"
            )



        result = await self.follow_repository.create(
            follower_id,
            following_id,
        )

        # Update follower/following counts
        await self.user_repository.increment_following_count(follower_id)
        await self.user_repository.increment_followers_count(following_id)

        return result



    async def unfollow_user(
        self,
        follower_id: str,
        username: str,
    ):


        user = await self.user_repository.get_by_username(
            username
        )


        if not user:

            raise ValueError(
                "User not found"
            )


        following_id = str(
            user["_id"]
        )



        deleted = await self.follow_repository.delete(
            follower_id,
            following_id,
        )

        # Update follower/following counts if deletion succeeded
        if deleted:
            await self.user_repository.decrement_following_count(follower_id)
            await self.user_repository.decrement_followers_count(following_id)


        return deleted