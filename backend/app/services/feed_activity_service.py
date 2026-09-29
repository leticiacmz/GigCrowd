from typing import Any, Optional, Sequence

from app.core.logger import get_logger
from app.domain.feed_activity import (
    ActivityObjectType,
    ActivityType,
    FeedActivity,
)
from app.repositories.feed_activity_repository import FeedActivityRepository
from app.repositories.follow_repository import FollowRepository
from app.repositories.user_repository import UserRepository
from app.schemas.feed_activity import (
    FeedActivityResponse,
    FeedActor,
    FeedPage,
)


logger = get_logger("feed_activity_service")


class FeedActivityService:
    """
    Produces and reads feed activities.

    Activities are stored once per action and fanned out on read, so any new
    social action only needs to call `record_activity` with its own type.
    """

    def __init__(
        self,
        repository: FeedActivityRepository,
        follow_repository: FollowRepository,
        user_repository: UserRepository,
    ):

        self.repository = repository

        self.follow_repository = follow_repository

        self.user_repository = user_repository

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    async def record_activity(
        self,
        actor_id: str,
        activity_type: ActivityType,
        object_type: ActivityObjectType,
        object_id: str,
        target_type: Optional[ActivityObjectType] = None,
        target_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict:

        activity = FeedActivity(
            actor_id=str(actor_id),
            activity_type=activity_type,
            object_type=object_type,
            object_id=str(object_id),
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            payload=payload or {},
        )

        return await self.repository.create(activity)

    async def record_user_follow(
        self,
        actor_id: str,
        followed_user_id: str,
        username: Optional[str] = None,
    ) -> dict:

        return await self.record_activity(
            actor_id=actor_id,
            activity_type=ActivityType.USER_FOLLOWED_USER,
            object_type=ActivityObjectType.USER,
            object_id=followed_user_id,
            payload={"username": username} if username else {},
        )

    async def record_artist_follow(
        self,
        actor_id: str,
        artist_slug: str,
        artist_name: Optional[str] = None,
    ) -> dict:

        return await self.record_activity(
            actor_id=actor_id,
            activity_type=ActivityType.USER_FOLLOWED_ARTIST,
            object_type=ActivityObjectType.ARTIST,
            object_id=artist_slug,
            payload={"artist_name": artist_name} if artist_name else {},
        )

    async def record_community_post(
        self,
        actor_id: str,
        post_id: str,
        artist_slug: str,
        content: Optional[str] = None,
    ) -> dict:

        payload: dict[str, Any] = {"artist_slug": artist_slug}

        if content:
            payload["preview"] = content[:280]

        return await self.record_activity(
            actor_id=actor_id,
            activity_type=ActivityType.COMMUNITY_POST_CREATED,
            object_type=ActivityObjectType.COMMUNITY_POST,
            object_id=post_id,
            target_type=ActivityObjectType.ARTIST,
            target_id=artist_slug,
            payload=payload,
        )

    async def record_event_attendance(
        self,
        actor_id: str,
        event_id: str,
        status: str,
        event_title: Optional[str] = None,
    ) -> dict:
        """Record attendance, replacing a previous status for the same event"""

        await self.remove_event_attendance(actor_id, event_id)

        payload: dict[str, Any] = {"status": status}

        if event_title:
            payload["event_title"] = event_title

        return await self.record_activity(
            actor_id=actor_id,
            activity_type=ActivityType.EVENT_ATTENDANCE,
            object_type=ActivityObjectType.EVENT,
            object_id=event_id,
            payload=payload,
        )

    async def remove_event_attendance(
        self,
        actor_id: str,
        event_id: str,
    ) -> bool:

        return await self.repository.delete_activity(
            actor_id=str(actor_id),
            activity_type=ActivityType.EVENT_ATTENDANCE,
            object_id=str(event_id),
        )

    async def record_review(
        self,
        actor_id: str,
        review_id: str,
        event_id: str,
        rating: Optional[int] = None,
    ) -> dict:
        """Record a review, replacing a previous review of the same event"""

        await self.remove_review(actor_id, review_id)

        payload: dict[str, Any] = {"event_id": str(event_id)}

        if rating is not None:
            payload["rating"] = rating

        return await self.record_activity(
            actor_id=actor_id,
            activity_type=ActivityType.REVIEW_CREATED,
            object_type=ActivityObjectType.REVIEW,
            object_id=review_id,
            target_type=ActivityObjectType.EVENT,
            target_id=event_id,
            payload=payload,
        )

    async def remove_review(
        self,
        actor_id: str,
        review_id: str,
    ) -> bool:

        return await self.repository.delete_activity(
            actor_id=str(actor_id),
            activity_type=ActivityType.REVIEW_CREATED,
            object_id=str(review_id),
        )

    async def remove_user_follow(
        self,
        actor_id: str,
        followed_user_id: str,
    ) -> bool:

        return await self.repository.delete_activity(
            actor_id=str(actor_id),
            activity_type=ActivityType.USER_FOLLOWED_USER,
            object_id=str(followed_user_id),
        )

    async def remove_artist_follow(
        self,
        actor_id: str,
        artist_slug: str,
    ) -> bool:

        return await self.repository.delete_activity(
            actor_id=str(actor_id),
            activity_type=ActivityType.USER_FOLLOWED_ARTIST,
            object_id=artist_slug,
        )

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    async def get_user_feed(
        self,
        user_id: str,
        limit: int = 20,
        skip: int = 0,
        activity_types: Optional[Sequence[ActivityType]] = None,
    ) -> FeedPage:
        """Chronological feed of the user's own and followed users' activities"""

        actor_ids = await self._feed_actor_ids(user_id)

        documents = await self.repository.get_feed_for_actors(
            actor_ids,
            limit=limit,
            skip=skip,
            activity_types=activity_types,
        )

        total = await self.repository.count_for_actors(
            actor_ids,
            activity_types=activity_types,
        )

        items = await self._to_responses(documents)

        has_more = skip + len(items) < total

        return FeedPage(
            items=items,
            limit=limit,
            skip=skip,
            total=total,
            has_more=has_more,
            next_skip=skip + limit if has_more else None,
        )

    async def get_actor_feed(
        self,
        actor_id: str,
        limit: int = 20,
        skip: int = 0,
    ) -> FeedPage:
        """Chronological feed of a single actor's activities"""

        documents = await self.repository.get_by_actor(
            str(actor_id),
            limit=limit,
            skip=skip,
        )

        total = await self.repository.count_for_actors(
            [str(actor_id)]
        )

        items = await self._to_responses(documents)

        has_more = skip + len(items) < total

        return FeedPage(
            items=items,
            limit=limit,
            skip=skip,
            total=total,
            has_more=has_more,
            next_skip=skip + limit if has_more else None,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _feed_actor_ids(
        self,
        user_id: str,
    ) -> list[str]:

        following_ids = await self.follow_repository.get_following_ids(
            str(user_id)
        )

        actor_ids = [str(user_id)]

        for following_id in following_ids:

            if following_id not in actor_ids:
                actor_ids.append(following_id)

        return actor_ids

    async def _to_responses(
        self,
        documents: list[dict],
    ) -> list[FeedActivityResponse]:

        actors = await self._load_actors(documents)

        responses: list[FeedActivityResponse] = []

        for document in documents:

            actor_id = str(document["actor_id"])

            responses.append(
                FeedActivityResponse(
                    id=str(document["_id"]),
                    actor=actors.get(
                        actor_id,
                        FeedActor(id=actor_id),
                    ),
                    activity_type=document["activity_type"],
                    object_type=document["object_type"],
                    object_id=document["object_id"],
                    target_type=document.get("target_type"),
                    target_id=document.get("target_id"),
                    payload=document.get("payload") or {},
                    created_at=document["created_at"],
                )
            )

        return responses

    async def _load_actors(
        self,
        documents: list[dict],
    ) -> dict[str, FeedActor]:

        actor_ids = {
            str(document["actor_id"])
            for document in documents
        }

        if not actor_ids:
            return {}

        users = await self.user_repository.get_by_ids(
            list(actor_ids)
        )

        return {
            str(user["_id"]): FeedActor(
                id=str(user["_id"]),
                username=user.get("username"),
                avatar_url=user.get("avatar_url"),
            )
            for user in users
        }
