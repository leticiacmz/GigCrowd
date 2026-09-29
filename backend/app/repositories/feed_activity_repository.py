from typing import Optional, Sequence

from app.domain.feed_activity import ActivityType, FeedActivity
from app.repositories.base import BaseRepository


class FeedActivityRepository(BaseRepository):

    def __init__(self, db):

        super().__init__(
            db,
            "feed_activities",
        )

    async def create(
        self,
        activity: FeedActivity,
    ) -> dict:
        """Persist an activity and return the stored document"""

        document = activity.model_dump(
            exclude={"id"},
            mode="json",
        )

        document["created_at"] = activity.created_at

        result = await self.insert_one(document)

        document["_id"] = str(result.inserted_id)

        return document

    async def get_feed_for_actors(
        self,
        actor_ids: Sequence[str],
        limit: int = 20,
        skip: int = 0,
        activity_types: Optional[Sequence[ActivityType]] = None,
    ) -> list[dict]:
        """
        Get activities produced by the given actors, most recent first.

        Ordering falls back to `_id` so activities created within the same
        instant keep a stable, deterministic order across pages.
        """

        if not actor_ids:
            return []

        query: dict = {
            "actor_id": {"$in": list(actor_ids)},
        }

        if activity_types:
            query["activity_type"] = {
                "$in": [
                    activity_type.value
                    for activity_type in activity_types
                ]
            }

        return await self.find_many(
            query,
            sort=[("created_at", -1), ("_id", -1)],
            skip=skip,
            limit=limit,
        )

    async def count_for_actors(
        self,
        actor_ids: Sequence[str],
        activity_types: Optional[Sequence[ActivityType]] = None,
    ) -> int:

        if not actor_ids:
            return 0

        query: dict = {
            "actor_id": {"$in": list(actor_ids)},
        }

        if activity_types:
            query["activity_type"] = {
                "$in": [
                    activity_type.value
                    for activity_type in activity_types
                ]
            }

        return await self.collection.count_documents(query)

    async def get_by_actor(
        self,
        actor_id: str,
        limit: int = 20,
        skip: int = 0,
    ) -> list[dict]:

        return await self.find_many(
            {"actor_id": actor_id},
            sort=[("created_at", -1), ("_id", -1)],
            skip=skip,
            limit=limit,
        )

    async def delete_activity(
        self,
        actor_id: str,
        activity_type: ActivityType,
        object_id: str,
    ) -> bool:
        """Remove an activity whose originating action was undone"""

        result = await self.collection.delete_one(
            {
                "actor_id": actor_id,
                "activity_type": activity_type.value,
                "object_id": object_id,
            }
        )

        return result.deleted_count > 0

    async def ensure_indexes(self) -> None:

        await self.collection.create_index(
            [("actor_id", 1), ("created_at", -1)]
        )

        await self.collection.create_index(
            [("created_at", -1)]
        )
