from typing import List
from datetime import datetime, UTC

from app.repositories.base import BaseRepository


class FollowRepository(BaseRepository):
    """
    Repository responsible for follow relationship persistence.

    Responsibilities:
    - Create follow relationships
    - Remove follow relationships
    - Search followers/following
    - Check follow existence

    This layer communicates only with MongoDB.
    Business rules belong to FollowService.
    """

    def __init__(
        self,
        db
    ):

        super().__init__(
            db,
            "follows"
        )



    async def create(
        self,
        follower_id: str,
        following_id: str,
    ) -> dict:
        """
        Create a follow relationship.
        """

        follow_document = {

            "follower_id": follower_id,

            "following_id": following_id,

            "created_at": datetime.now(UTC),

        }


        result = await self.insert_one(
            follow_document
        )


        follow_document["_id"] = str(
            result.inserted_id
        )


        return follow_document




    async def delete(
        self,
        follower_id: str,
        following_id: str,
    ) -> bool:
        """
        Delete a follow relationship.
        """


        result = await self.collection.delete_one(
            {
                "follower_id": follower_id,

                "following_id": following_id,
            }
        )


        return result.deleted_count > 0





    async def exists(
        self,
        follower_id: str,
        following_id: str,
    ) -> bool:
        """
        Check if a follow relationship exists.
        """


        follow = await self.find_one(
            {
                "follower_id": follower_id,

                "following_id": following_id,
            }
        )


        return follow is not None





    async def get_following(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        """
        Get users followed by a user.
        """


        follows = await (
            self.collection
            .find(
                {
                    "follower_id": user_id
                }
            )
            .skip(skip)
            .limit(limit)
            .to_list(
                length=limit
            )
        )


        following_ids = [
            follow["following_id"]
            for follow in follows
        ]


        if not following_ids:

            return []



        users = await (
            self.collection.database.users
            .find(
                {
                    "_id":
                    {
                        "$in": following_ids
                    }
                }
            )
            .to_list(
                length=limit
            )
        )


        return users






    async def get_followers(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        """
        Get users following a user.
        """


        follows = await (
            self.collection
            .find(
                {
                    "following_id": user_id
                }
            )
            .skip(skip)
            .limit(limit)
            .to_list(
                length=limit
            )
        )


        follower_ids = [
            follow["follower_id"]
            for follow in follows
        ]


        if not follower_ids:

            return []



        users = await (
            self.collection.database.users
            .find(
                {
                    "_id":
                    {
                        "$in": follower_ids
                    }
                }
            )
            .to_list(
                length=limit
            )
        )


        return users