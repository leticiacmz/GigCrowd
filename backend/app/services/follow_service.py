from app.models.follow import FollowCreate

from app.repositories.follow_repository import FollowRepository
from app.repositories.user_repository import UserRepository

from app.database.connection import get_database



class FollowService:


    def __init__(self):

        db = get_database()

        self.follow_repository = FollowRepository(
            db
        )
        self.user_repository = UserRepository(
            db
        )



    async def follow_user(
        self,
        follower_id: str,
        follow_data: FollowCreate,
    ):


        following_id = follow_data.following_id


        if follower_id == following_id:

            raise ValueError(
                "Cannot follow yourself"
            )



        exists = await self.follow_repository.exists(
            follower_id=follower_id,
            following_id=following_id,
        )


        if exists:

            raise ValueError(
                "Already following this user"
            )



        follow = await self.follow_repository.create(
            follower_id=follower_id,
            following_id=following_id,
        )



        await self.user_repository.increment_following_count(
            follower_id
        )


        await self.user_repository.increment_followers_count(
            following_id
        )


        return follow




    async def unfollow_user(
        self,
        follower_id: str,
        following_id: str,
    ):


        deleted = await self.follow_repository.delete(
            follower_id=follower_id,
            following_id=following_id,
        )


        if not deleted:

            return False



        await self.user_repository.decrement_following_count(
            follower_id
        )


        await self.user_repository.decrement_followers_count(
            following_id
        )


        return True




    async def get_following(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ):


        return await self.follow_repository.get_following(
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


        return await self.follow_repository.get_followers(
            user_id=user_id,
            skip=skip,
            limit=limit,
        )



    async def is_following(
        self,
        follower_id: str,
        following_id: str,
    ):


        return await self.follow_repository.exists(
            follower_id=follower_id,
            following_id=following_id,
        )