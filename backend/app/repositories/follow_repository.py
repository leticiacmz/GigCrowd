from typing import Optional, List
from datetime import datetime, UTC

from app.database.connection import get_database


class FollowRepository:
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

    def __init__(self):
        self.collection_name = "follows"


    async def create(
        self,
        follower_id: str,
        following_id: str,
    ) -> dict:
        """
        Create a follow relationship.
        """

        db = get_database()

        follow_document = {
            "follower_id": follower_id,
            "following_id": following_id,
            "created_at": datetime.now(UTC),
        }

        result = await db[self.collection_name].insert_one(
            follow_document
        )

        follow_document["_id"] = str(result.inserted_id)

        return follow_document



    async def delete(
        self,
        follower_id: str,
        following_id: str,
    ) -> bool:
        """
        Delete a follow relationship.
        """

        db = get_database()

        result = await db[self.collection_name].delete_one(
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

        db = get_database()

        follow = await db[self.collection_name].find_one(
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

        db = get_database()

        follows = await (
            db[self.collection_name]
            .find(
                {
                    "follower_id": user_id
                }
            )
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )


        following_ids = [
            follow["following_id"]
            for follow in follows
        ]


        if not following_ids:
            return []


        users = await (
            db.users
            .find(
                {
                    "_id": {
                        "$in": following_ids
                    }
                }
            )
            .to_list(length=limit)
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

        db = get_database()


        follows = await (
            db[self.collection_name]
            .find(
                {
                    "following_id": user_id
                }
            )
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )


        follower_ids = [
            follow["follower_id"]
            for follow in follows
        ]


        if not follower_ids:
            return []


        users = await (
            db.users
            .find(
                {
                    "_id": {
                        "$in": follower_ids
                    }
                }
            )
            .to_list(length=limit)
        )


        return users