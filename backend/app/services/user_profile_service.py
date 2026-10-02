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


    async def get_connections(
        self,
        username: str,
        direction: str = "followers",
        limit: int = 50,
    ) -> list[dict]:
        """List the people a user follows, or the people following them.

        Returns the same public shape for both directions so the UI can render
        one list component either way. Identifiers in the `follows` collection
        are stored as strings, so they are resolved in a single batched query
        rather than one lookup per relationship.
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


        return {
            "id": str(user["_id"]),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "bio": user.get("bio"),
            "avatar_url": user.get("avatar_url"),
            "location": user.get("location"),
            "followers_count": user.get(
                "followers_count",
                0,
            ),
            "following_count": user.get(
                "following_count",
                0,
            ),
            "created_at": user.get("created_at"),
        }



    async def update_profile(
        self,
        user_id: str,
        data: dict,
    ):

        allowed_fields = {
            "full_name",
            "bio",
            "location",
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


        return {
            "id": str(user["_id"]),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "bio": user.get("bio"),
            "avatar_url": user.get("avatar_url"),
            "location": user.get("location"),
            "followers_count": user.get(
                "followers_count",
                0,
            ),
            "following_count": user.get(
                "following_count",
                0,
            ),
            "created_at": user.get("created_at"),
        }