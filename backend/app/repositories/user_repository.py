from bson import ObjectId

from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):

    def __init__(
        self,
        db
    ):
        super().__init__(
            db,
            "users"
        )


    async def get_by_id(
        self,
        user_id: str
    ):

        try:
            object_id = ObjectId(user_id)

        except Exception:
            return None

        return await self.find_one(
            {
                "_id": object_id
            }
        )


    async def get_by_username(
        self,
        username: str
    ):

        return await self.find_one(
            {
                "username": username
            }
        )


    async def get_by_ids(
        self,
        user_ids: list[str]
    ) -> list[dict]:
        """Fetch several users with a single query.

        Identifiers may be stored as strings or ObjectIds, so both forms are
        matched at once instead of issuing a lookup per id.
        """

        wanted = {
            str(user_id)
            for user_id in user_ids
            if user_id
        }

        if not wanted:
            return []


        conditions: list[dict] = [
            {"_id": user_id}
            for user_id in wanted
        ]

        for user_id in sorted(wanted):

            try:
                conditions.append(
                    {"_id": ObjectId(user_id)}
                )

            except Exception:
                continue


        cursor = self.collection.find(
            {"$or": conditions}
        )

        return await cursor.to_list(
            length=len(wanted)
        )


    async def increment_following_count(
        self,
        user_id: str
    ):

        try:
            object_id = ObjectId(user_id)

        except Exception:
            return False

        result = await self.collection.update_one(
            {
                "_id": object_id
            },
            {
                "$inc": {
                    "following_count": 1
                }
            }
        )

        return result.modified_count > 0


    async def increment_followers_count(
        self,
        user_id: str
    ):

        try:
            object_id = ObjectId(user_id)

        except Exception:
            return False

        result = await self.collection.update_one(
            {
                "_id": object_id
            },
            {
                "$inc": {
                    "followers_count": 1
                }
            }
        )

        return result.modified_count > 0


    async def increment_followed_artists_count(
        self,
        user_id: str
    ):
        """Increment the count of artists this user follows"""

        try:
            object_id = ObjectId(user_id)

        except Exception:
            return False

        result = await self.collection.update_one(
            {
                "_id": object_id
            },
            {
                "$inc": {
                    "followed_artists_count": 1
                }
            }
        )

        return result.modified_count > 0


    async def decrement_following_count(
        self,
        user_id: str
    ):

        try:
            object_id = ObjectId(user_id)

        except Exception:
            return False

        result = await self.collection.update_one(
            {
                "_id": object_id
            },
            {
                "$inc": {
                    "following_count": -1
                }
            }
        )

        return result.modified_count > 0


    async def decrement_followers_count(
        self,
        user_id: str
    ):

        try:
            object_id = ObjectId(user_id)

        except Exception:
            return False

        result = await self.collection.update_one(
            {
                "_id": object_id
            },
            {
                "$inc": {
                    "followers_count": -1
                }
            }
        )

        return result.modified_count > 0


    async def decrement_followed_artists_count(
        self,
        user_id: str
    ):
        """Decrement the count of artists this user follows"""

        try:
            object_id = ObjectId(user_id)

        except Exception:
            return False

        result = await self.collection.update_one(
            {
                "_id": object_id
            },
            {
                "$inc": {
                    "followed_artists_count": -1
                }
            }
        )

        return result.modified_count > 0


    async def get_stats(
        self,
        user_id: str
    ) -> dict | None:

        user = await self.get_by_id(
            user_id
        )

        if not user:
            return None

        return {

            "username": user.get("username"),

            "followers_count": user.get(
                "followers_count",
                0
            ),

            "following_count": user.get(
                "following_count",
                0
            ),

            "bio": user.get("bio"),

            "avatar_url": user.get("avatar_url")
        }

    async def update_user(
        self,
        user_id: str,
        data: dict,
    ):

        try:
            object_id = ObjectId(user_id)

        except Exception:
            return None


        result = await self.collection.update_one(

            {
                "_id": object_id
            },

            {
                "$set": data
            }

        )


        if result.modified_count == 0:
            return await self.get_by_id(
                user_id
            )


        return await self.get_by_id(
            user_id
        )    