from datetime import datetime, UTC
from typing import List

from app.repositories.base import BaseRepository


class FollowRepository(BaseRepository):

    def __init__(
        self,
        db,
    ):

        super().__init__(
            db,
            "follows"
        )


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


        follow = await self.collection.find_one(
            {
                "follower_id": follower_id,

                "following_id": following_id,
            }
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


        return follows