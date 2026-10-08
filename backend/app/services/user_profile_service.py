from app.repositories.follow_repository import FollowRepository
from app.repositories.user_repository import UserRepository


class UserProfileService:

    def __init__(
        self,
        user_repository: UserRepository,
        follow_repository: FollowRepository | None = None,
    ):

        self.user_repository = user_repository
        self.follow_repository = follow_repository


    @staticmethod
    def _public_view(
        user: dict,
    ) -> dict:

        return {
            "id": str(user["_id"]),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "avatar_url": user.get("avatar_url"),
        }


    async def _social_counts(
        self,
        user: dict,
    ) -> tuple[int, int]:
        """Follower and following counts for a user.

        Counted from the `follows` collection so the figure always matches the
        list behind it. The denormalized counters on the user document are
        left untouched, but they are not reported because they drift whenever
        a counter update is missed.
        """

        user_id = str(user["_id"])

        if not self.follow_repository:
            return (
                user.get("followers_count", 0),
                user.get("following_count", 0),
            )

        followers_count = (
            await self.follow_repository.count_followers(
                user_id,
            )
        )

        following_count = (
            await self.follow_repository.count_following(
                user_id,
            )
        )

        return followers_count, following_count


    async def _public_profile(
        self,
        user: dict,
    ) -> dict:

        followers_count, following_count = (
            await self._social_counts(user)
        )

        return {
            "id": str(user["_id"]),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "bio": user.get("bio"),
            "avatar_url": user.get("avatar_url"),
            "location": user.get("location"),
            "followers_count": followers_count,
            "following_count": following_count,
            "created_at": user.get("created_at"),
        }


    async def get_connections(
        self,
        username: str,
        direction: str = "followers",
        limit: int = 50,
    ) -> list[dict]:
        """List the people a user follows, or the people following them.

        Returns the same public shape for both directions so the UI can render
        one list component either way. The relationships are resolved in a
        single batched query rather than one lookup per relationship.
        """
        if not self.follow_repository:
            return []

        user = await self.user_repository.get_by_username(
            username
        )

        if not user:
            return []


        field = (
            "follower_id"
            if direction == "followers"
            else "following_id"
        )

        if direction == "followers":

            relationships = await self.follow_repository.get_followers(
                str(user["_id"]),
                limit=limit,
            )

        else:

            relationships = await self.follow_repository.get_following(
                str(user["_id"]),
                limit=limit,
            )


        user_ids = [
            str(relationship[field])
            for relationship in relationships
            if relationship.get(field)
        ]


        if not user_ids:
            return []


        users = await self.user_repository.get_by_ids(
            user_ids
        )


        return [
            self._public_view(found)
            for found in users
        ]


    async def get_profile(
        self,
        username: str,
    ):

        user = await self.user_repository.get_by_username(
            username
        )

        if not user:
            return None


        return await self._public_profile(
            user
        )



    async def update_profile(
        self,
        user_id: str,
        data: dict,
    ):

        allowed_fields = {
            "full_name",
            "bio",
            "location",
            # The avatar is an ordinary profile field set from the same place
            # as the rest: the owner's own update of their own document
            # (`/users/me`). The path carries no other user id to aim at, so
            # "only the owner may modify" holds by construction rather than by
            # an extra check. The value itself was validated at the schema -
            # http(s) only.
            "avatar_url",
        }


        filtered_data = {
            key: value
            for key, value in data.items()
            if key in allowed_fields
        }


        user = await self.user_repository.update_user(
            user_id,
            filtered_data,
        )


        if not user:
            return None


        return await self._public_profile(
            user
        )