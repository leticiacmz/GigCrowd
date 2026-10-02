from datetime import datetime, UTC
from typing import List

from app.repositories.base import BaseRepository
from app.utils.ids import id_matches


class FollowRepository(BaseRepository):

    def __init__(
        self,
        db,
    ):

        super().__init__(
            db,
            "follows"
        )


    @staticmethod
    def _pair_query(
        follower_id: str,
        following_id: str,
    ) -> dict:
        """Match a follow pair regardless of how the ids were stored.

        Older rows keep the identifiers as strings while newer ones use
        ObjectId, so both representations have to match or an existing
        relationship looks absent.
        """

        return {
            **id_matches("follower_id", follower_id),
            **id_matches("following_id", following_id),
        }


    async def create(
        self,
        follower_id: str,
        following_id: str,
    ):

        document = {

            "follower_id": follower_id,

            "following_id": following_id,

            "created_at": datetime.now(
                UTC
            ),
        }


        result = await self.collection.insert_one(
            document
        )


        document["_id"] = str(
            result.inserted_id
        )


        return document



    async def delete(
        self,
        follower_id: str,
        following_id: str,
    ) -> bool:


        result = await self.collection.delete_one(
            self._pair_query(
                follower_id,
                following_id,
            )
        )


        return result.deleted_count > 0



    async def exists(
        self,
        follower_id: str,
        following_id: str,
    ) -> bool:


        follow = await self.collection.find_one(
            self._pair_query(
                follower_id,
                following_id,
            )
        )


        return follow is not None



    async def get_followers(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:


        follows = await (
            self.collection
            .find(
                id_matches(
                    "following_id",
                    user_id,
                )
            )
            .skip(skip)
            .limit(limit)
            .to_list(
                length=limit
            )
        )


        return follows



    async def get_following(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:


        follows = await (
            self.collection
            .find(
                id_matches(
                    "follower_id",
                    user_id,
                )
            )
            .skip(skip)
            .limit(limit)
            .to_list(
                length=limit
            )
        )


        return follows

    async def count_followers(
        self,
        user_id: str,
    ) -> int:
        """Count how many users follow this user"""

        return await self.collection.count_documents(
            id_matches(
                "following_id",
                user_id,
            )
        )

    async def count_following(
        self,
        user_id: str,
    ) -> int:
        """Count how many users this user follows"""

        return await self.collection.count_documents(
            id_matches(
                "follower_id",
                user_id,
            )
        )