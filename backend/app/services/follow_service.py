from app.models.follow import FollowCreate


class FollowService:
    """
    Service responsible for follow business rules.

    Responsibilities:
    - Prevent self follow
    - Prevent duplicated follows
    - Update follower/following counters
    - Delegate persistence to repositories
    """

    def __init__(
        self,
        follow_repository,
        user_repository,
    ):

        self.follow_repository = follow_repository
        self.user_repository = user_repository


    async def follow_user(
        self,
        follower_id: str,
        follow_data: FollowCreate,
    ):

        # Cannot follow yourself
        if follower_id == follow_data.following_id:
            raise ValueError(
                "Cannot follow yourself"
            )


        # Check duplicated follow
        already_following = await (
            self.follow_repository.exists(
                follower_id=follower_id,
                following_id=follow_data.following_id,
            )
        )


        if already_following:
            raise ValueError(
                "Already following this user"
            )


        # Create relationship
        follow = await (
            self.follow_repository.create(
                follower_id=follower_id,
                following_id=follow_data.following_id,
            )
        )


        # Update counters
        await (
            self.user_repository.increment_following_count(
                follower_id
            )
        )


        await (
            self.user_repository.increment_followers_count(
                follow_data.following_id
            )
        )


        return follow



    async def unfollow_user(
        self,
        follower_id: str,
        following_id: str,
    ) -> bool:


        deleted = await (
            self.follow_repository.delete(
                follower_id=follower_id,
                following_id=following_id,
            )
        )


        if not deleted:
            return False



        await (
            self.user_repository.decrement_following_count(
                follower_id
            )
        )


        await (
            self.user_repository.decrement_followers_count(
                following_id
            )
        )


        return True



    async def get_following(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ):

        return await (
            self.follow_repository.get_following(
                user_id=user_id,
                skip=skip,
                limit=limit,
            )
        )



    async def get_followers(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ):

        return await (
            self.follow_repository.get_followers(
                user_id=user_id,
                skip=skip,
                limit=limit,
            )
        )



    async def is_following(
        self,
        follower_id: str,
        following_id: str,
    ) -> bool:

        return await (
            self.follow_repository.exists(
                follower_id=follower_id,
                following_id=following_id,
            )
        )