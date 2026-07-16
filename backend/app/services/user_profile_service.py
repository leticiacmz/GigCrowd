from app.repositories.user_repository import UserRepository


class UserProfileService:

    def __init__(
        self,
        user_repository: UserRepository,
    ):

        self.user_repository = user_repository


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